#!/usr/bin/env python3
"""Measure wrap_ratio over sample files to choose the join threshold.

    uv run tools/measure_wrap.py samples/*.txt

Prints, per file, the share of translatable lines that do not end in sentence
punctuation. Wrapped prose scores high because one sentence spans several
lines; record-per-line output scores low.
"""

from __future__ import annotations

import sys
from pathlib import Path

from yaku.cache import Cache
from yaku.loader import load_mask_rules, load_passthrough, load_source, load_target
from yaku.masking import Masker
from yaku.pipeline import WRAP_THRESHOLD, Pipeline


class NoEngine:
    def translate(self, texts: list[str]) -> list[str]:
        return [""] * len(texts)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2

    source = load_source("en")
    target = load_target("ja")
    masker = Masker(rules=load_mask_rules(), target=target)
    passthrough = load_passthrough()

    print(f"threshold {WRAP_THRESHOLD}\n")
    print(f"{'file':28} {'lines':>7} {'transl':>7} {'ratio':>7}  join")
    for name in argv:
        path = Path(name)
        raw = path.read_text(errors="replace").splitlines()
        pipeline = Pipeline(
            engine=NoEngine(),
            masker=masker,
            source=source,
            target=target,
            passthrough=passthrough,
            cache=Cache(None, "measure"),
        )
        translatable = sum(1 for line in raw if pipeline._classify(line)[3])
        ratio = pipeline.wrap_ratio(raw)
        join = "yes" if ratio >= WRAP_THRESHOLD else "no"
        print(f"{path.name:28} {len(raw):7} {translatable:7} {ratio:7.2f}  {join}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
