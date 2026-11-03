"""Command line entry point."""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from pathlib import Path

from yaku import __version__, paths
from yaku.cache import Cache, model_fingerprint
from yaku.loader import RuleError, load_mask_rules, load_passthrough, load_source, load_target
from yaku.masking import Masker
from yaku.pipeline import Pipeline
from yaku.text import strip_overstrike

SOURCE_LANG = "en"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yaku",
        description="Translate the prose in command output, leave the rest verbatim.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  terraform plan 2>&1 | yaku\n"
            "  man tar | yaku\n"
            "  yaku --dry-run < output.txt\n"
            "\n"
            "first use:\n"
            "  yaku setup --lang ja   download and convert the model\n"
        ),
    )
    parser.add_argument("--lang", default="ja", help="target language (default: ja)")
    parser.add_argument(
        "--model", type=Path, default=None, help="model directory (default: resolved from --lang)"
    )
    parser.add_argument("--beam", type=int, default=5, help="beam width (default: 5)")
    parser.add_argument(
        "--length-penalty",
        type=float,
        default=1.5,
        help="above 1 favours complete translations over short ones (default: 1.5)",
    )
    parser.add_argument(
        "--fallback",
        default="both",
        choices=["both", "original", "mark"],
        help="what to emit for a line that fails the quality gate (default: both)",
    )
    parser.add_argument("--mask-off", default="", help="comma-separated mask rules to disable")
    parser.add_argument("--mask-on", default="", help="comma-separated mask rules to enable")

    joining = parser.add_mutually_exclusive_group()
    joining.add_argument(
        "--join",
        dest="join",
        action="store_true",
        default=None,
        help="join wrapped lines before translating (default: decided from the input)",
    )
    joining.add_argument(
        "--no-join", dest="join", action="store_false", help="never join wrapped lines"
    )

    parser.add_argument("--width", type=int, default=0, help="wrap width, 0 to disable")
    parser.add_argument("--rules-dir", type=Path, default=None, help="extra rule directory")
    parser.add_argument("--no-cache", action="store_true", help="do not read or write the cache")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument(
        "--dry-run", action="store_true", help="show the classification and masking only"
    )
    parser.add_argument(
        "--show-paths", action="store_true", help="print resolved locations and exit"
    )
    parser.add_argument(
        "--show-reason",
        action="store_true",
        help="append the quality gate reason to each flagged line",
    )
    parser.add_argument("--stats", action="store_true", help="write a summary to stderr")
    parser.add_argument("--version", action="version", version=f"yaku {__version__}")
    return parser


def show_paths() -> None:
    print(f"models   {paths.models_dir()}")
    print(f"cache    {paths.cache_path()}")
    print(f"config   {paths.config_dir()}")
    for index, directory in enumerate(paths.rule_dirs()):
        label = "rules" if index == 0 else "     "
        print(f"{label}    {directory}")


def _names(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["setup"]:
        return _setup(argv[1:])
    args = build_parser().parse_args(argv)

    if args.show_paths:
        show_paths()
        return 0

    try:
        rule_dirs = paths.rule_dirs(args.rules_dir)
        rules = load_mask_rules(rule_dirs)
        passthrough = load_passthrough(rule_dirs)
        source = load_source(SOURCE_LANG, rule_dirs)
        target = load_target(args.lang, rule_dirs)
    except RuleError as exc:
        print(f"yaku: {exc}", file=sys.stderr)
        return 2

    enable, disable = _names(args.mask_on), _names(args.mask_off)
    known = {rule.name for rule in rules}
    for name in (enable | disable) - known:
        print(f"yaku: no such mask rule: {name}", file=sys.stderr)
        return 2
    rules = [
        rule
        if rule.name not in enable | disable
        else dataclasses.replace(rule, enabled=rule.name in enable)
        for rule in rules
    ]

    masker = Masker(rules=rules, target=target)
    raw_lines = strip_overstrike(sys.stdin.read()).splitlines()

    if args.dry_run:
        return _dry_run(raw_lines, masker, source, target, passthrough, args)

    model_dir = args.model or paths.model_dir(target.model_name)
    try:
        from yaku.engines import CT2Engine, EngineError

        engine = CT2Engine.load(
            model_dir,
            beam=args.beam,
            length_penalty=args.length_penalty,
            device=args.device,
            compute_type=args.compute_type,
            threads=args.threads,
        )
    except EngineError as exc:
        print(f"yaku: {exc}", file=sys.stderr)
        print(f"yaku: run 'yaku setup --lang {args.lang}' or pass --model", file=sys.stderr)
        return 2

    active = ",".join(sorted(rule.name for rule in rules if rule.enabled))
    model_id = f"{target.model_name}:{model_fingerprint(model_dir)}"
    namespace = f"{model_id}:{args.beam}:{args.length_penalty}:{active}"
    cache_path = None if args.no_cache else paths.cache_path()

    with Cache(cache_path, namespace) as cache:
        pipeline = Pipeline(
            engine=engine,
            masker=masker,
            source=source,
            target=target,
            passthrough=passthrough,
            cache=cache,
            fallback=args.fallback,
            join=args.join,
            width=args.width,
            show_reason=args.show_reason,
        )
        lines = pipeline.prepare(raw_lines)
        pipeline.run(lines)
        for line in lines:
            for text in pipeline.render(line):
                print(text)

    if args.stats:
        s = pipeline.stats
        print(
            f"yaku: {s.lines} lines, {s.translated} translated, "
            f"{s.flagged} flagged ({s.flagged_share:.1%}), "
            f"{s.cached} cached, {s.requested} requested, "
            f"join={s.joined} wrap_ratio={s.wrap_ratio:.2f}",
            file=sys.stderr,
        )
    return 0


def _setup(argv: list[str]) -> int:
    from yaku import setup

    def target(lang: str):
        return load_target(lang, paths.rule_dirs())

    try:
        return setup.main(argv, target)
    except RuleError as exc:
        print(f"yaku: {exc}", file=sys.stderr)
        return 2


def _dry_run(raw_lines, masker, source, target, passthrough, args) -> int:
    """Show how each line was classified without loading a model."""

    class NoEngine:
        def translate(self, texts: list[str]) -> list[str]:
            return [""] * len(texts)

    pipeline = Pipeline(
        engine=NoEngine(),
        masker=masker,
        source=source,
        target=target,
        passthrough=passthrough,
        cache=Cache(None, "dry-run"),
        join=args.join,
    )
    for line in pipeline.prepare(raw_lines):
        if line.translatable:
            for segment in line.segments:
                print(f"T  {segment}")
        else:
            print(f"-  {line.body}")

    if args.stats:
        s = pipeline.stats
        print(
            f"yaku: {s.lines} lines, join={s.joined} wrap_ratio={s.wrap_ratio:.2f}",
            file=sys.stderr,
        )
    return 0


def run() -> None:
    try:
        sys.exit(main())
    except BrokenPipeError:
        os._exit(0)  # a downstream head or less closed the pipe
    except KeyboardInterrupt:
        sys.exit(130)
