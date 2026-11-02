#!/usr/bin/env python3
"""Measure how a model's vocabulary tokenises placeholder formats.

    uv run tools/check_placeholders.py [--model DIR]

A placeholder is paid for on every masked span, so the format matters. Run
this after changing models and put the winner in rules/target/<lang>.toml.
Standalone cost is the token count on its own; in-sentence cost is the extra
tokens one placeholder adds to a carrier sentence, which is what is actually
charged.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sentencepiece as spm

from yaku import paths
from yaku.loader import load_target

CANDIDATES = ["T%d", "X%02d", "{T%d}", "__T%d__", "[T%d]", "@%d", "P%d"]

CARRIER = "The {ph} option is required and {ph2} will be created."


def tokeniser(model_dir: Path) -> spm.SentencePieceProcessor:
    path = model_dir / "source.spm"
    if not path.is_file():
        candidates = sorted(model_dir.glob("*.spm"))
        if not candidates:
            raise SystemExit(f"no .spm in {model_dir}")
        path = candidates[0]
    return spm.SentencePieceProcessor(str(path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--lang", default="ja")
    args = parser.parse_args()

    model_dir = args.model or paths.model_dir(load_target(args.lang).model_name)
    sp = tokeniser(model_dir)

    bare = len(sp.encode(CARRIER.format(ph="", ph2=""), out_type=str))

    print(f"model {model_dir}")
    print(f"carrier without placeholders: {bare} tokens\n")
    print(f"{'format':10} {'standalone':>11} {'per placeholder':>16}  pieces")
    for fmt in CANDIDATES:
        standalone = sp.encode(fmt % 1, out_type=str)
        filled = CARRIER.format(ph=fmt % 1, ph2=fmt % 2)
        total = len(sp.encode(filled, out_type=str))
        per = (total - bare) / 2
        print(
            f"{fmt:10} {len(standalone):11} {per:16.1f}  {standalone}"
        )

    print("\nround trip through the tokeniser:")
    for fmt in CANDIDATES:
        text = CARRIER.format(ph=fmt % 1, ph2=fmt % 2)
        back = sp.decode(sp.encode(text, out_type=str))
        status = "ok" if back == text else "CHANGED"
        print(f"  {fmt:10} {status}")
        if back != text:
            print(f"             {back}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
