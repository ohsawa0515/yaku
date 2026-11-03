#!/usr/bin/env python3
"""Dump translated segments in a length-ratio band for labelling.

    uv run tools/ratio_samples.py --low 0.15 --high 0.50 samples/*.txt > segments.jsonl

Each output line is one segment: the masked source, the raw translation, the
translated/source character ratio and whether placeholders survived. Add a
"label" field ("complete" or "dropped") by hand and pass the file to
tools/ratio_report.py to see how well each min_ratio separates the two.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yaku import paths
from yaku.cache import Cache
from yaku.engines import CT2Engine
from yaku.loader import load_mask_rules, load_passthrough, load_source, load_target
from yaku.masking import Masker
from yaku.pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--low", type=float, default=0.15)
    parser.add_argument("--high", type=float, default=0.50)
    parser.add_argument("--lang", default="ja")
    args = parser.parse_args()

    source, target = load_source("en"), load_target(args.lang)
    masker = Masker(rules=load_mask_rules(), target=target)
    engine = CT2Engine.load(paths.model_dir(target.model_name))

    seen: set[str] = set()
    for path in args.files:
        pipeline = Pipeline(
            engine=engine,
            masker=masker,
            source=source,
            target=target,
            passthrough=load_passthrough(),
            cache=Cache(paths.cache_path(), f"{target.model_name}:ratio"),
        )
        lines = pipeline.prepare(path.read_text(errors="replace").splitlines())
        pipeline.run(lines)
        for line in lines:
            if not line.translatable:
                continue
            for segment, result in zip(line.segments, line.segment_results, strict=True):
                if segment in seen:
                    continue
                seen.add(segment)
                ratio = len(result) / max(len(segment), 1)
                if not args.low <= ratio < args.high:
                    continue
                expected = set(target.placeholder_pattern.findall(segment))
                record = {
                    "file": path.name,
                    "ratio": round(ratio, 3),
                    "source": segment,
                    "translation": result,
                    "placeholders_ok": (
                        expected <= set(target.placeholder_pattern.findall(result))
                        if expected
                        else None
                    ),
                }
                print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
