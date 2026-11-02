#!/usr/bin/env python3
"""Measure translation quality over sample files.

    uv run tools/eval_translate.py samples/*.txt
    uv run tools/eval_translate.py --mask-off CONST samples/man-tar.txt

Reports, per file:

  tokens        total source tokens, bare and after masking. This is what
                masking is paid for: fewer tokens per request means more of
                each sentence fits before the decoder starts dropping text.
  fertility     tokens per source character. Roughly constant under masking,
                because masking shortens the text as well; a rise means a
                rule is splitting words into fragments.
  restore fail  share of translated lines whose placeholders cannot all be
                put back. This is the signal that a clause went missing.
  flagged       share of translated lines the quality gate rejected, with a
                breakdown by reason. Comparable between rule sets, but NOT
                between masking on and off: without placeholders the gate
                loses its only detector of a dropped clause, so turning
                masking off lowers this number while lowering quality.

Changing a model, a placeholder format or a mask rule should be followed by
a run of this over the same files, and the numbers compared.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from yaku import paths
from yaku.cache import Cache
from yaku.engines import CT2Engine, EngineError
from yaku.loader import load_mask_rules, load_passthrough, load_source, load_target
from yaku.masking import Masker
from yaku.pipeline import Pipeline
from yaku.types import MaskRule


def _apply_switches(rules: list[MaskRule], enable: set[str], disable: set[str]) -> list[MaskRule]:
    out = []
    for rule in rules:
        enabled = rule.enabled
        if rule.name in enable:
            enabled = True
        if rule.name in disable:
            enabled = False
        out.append(
            MaskRule(
                name=rule.name,
                pattern=rule.pattern,
                order=rule.order,
                enabled=enabled,
            )
        )
    return out


def _names(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--lang", default="ja")
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--beam", type=int, default=5)
    parser.add_argument("--mask-off", default="")
    parser.add_argument("--mask-on", default="")
    args = parser.parse_args()

    source = load_source("en")
    target = load_target(args.lang)
    rules = _apply_switches(load_mask_rules(), _names(args.mask_on), _names(args.mask_off))
    masker = Masker(rules=rules, target=target)
    passthrough = load_passthrough()

    model_dir = args.model or paths.model_dir(target.model_name)
    try:
        engine = CT2Engine.load(model_dir, beam=args.beam)
    except EngineError as exc:
        print(f"eval: {exc}", file=sys.stderr)
        return 2

    active = [rule.name for rule in rules if rule.enabled]
    print(f"model    {model_dir}")
    print(f"beam     {args.beam}")
    print(f"rules    {len(active)} active: {','.join(active)}\n")

    for path in args.files:
        raw = path.read_text(errors="replace").splitlines()
        pipeline = Pipeline(
            engine=engine,
            masker=masker,
            source=source,
            target=target,
            passthrough=passthrough,
            cache=Cache(None, "eval"),
        )
        lines = pipeline.prepare(raw)
        pipeline.run(lines)

        bare_chars = bare_tokens = mask_chars = mask_tokens = 0
        failures = 0
        reasons: Counter[str] = Counter()
        translated = 0

        for line in lines:
            if not line.translatable:
                continue
            translated += 1
            bare_chars += len(line.body)
            bare_tokens += len(engine.source_sp.encode(line.body, out_type=str))
            mask_chars += len(line.masked)
            mask_tokens += len(engine.source_sp.encode(line.masked, out_type=str))

            if line.result is not None:
                lost = masker.lost(line.result, len(line.values))
                extra = masker.residue(line.result, len(line.values))
                if lost or extra:
                    failures += 1
            if not line.verdict.ok:
                # Keep the reason, drop the numbers inside it.
                reasons[line.verdict.reason.split(" (")[0]] += 1

        flagged = sum(reasons.values())
        print(f"{path.name}")
        print(f"  translated lines   {translated}")
        saved = 1 - mask_tokens / max(bare_tokens, 1)
        print(f"  tokens             bare {bare_tokens}  masked {mask_tokens}  ({saved:.1%} fewer)")
        print(
            f"  fertility          bare {bare_tokens / max(bare_chars, 1):.3f}"
            f"  masked {mask_tokens / max(mask_chars, 1):.3f} tok/char"
        )
        print(f"  restore failures   {failures} ({failures / max(translated, 1):.1%})")
        print(f"  flagged            {flagged} ({flagged / max(translated, 1):.1%})")
        for reason, count in reasons.most_common():
            print(f"      {reason:24} {count}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
