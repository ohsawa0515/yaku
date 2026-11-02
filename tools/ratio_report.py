#!/usr/bin/env python3
"""Score min_ratio candidates against hand-labelled segments.

    uv run tools/ratio_report.py labelled.jsonl

Input is the output of tools/ratio_samples.py with a "label" field added
("complete" or "dropped") and, when the segments were sampled per ratio band,
a "weight" field equal to band size / sampled count. Estimates are weighted
so that a sampled band counts as much as it would have unsampled.

Precision is the share of flagged segments that really dropped text; recall
is the share of dropped segments that get flagged. Recall only covers drops
inside the sampled band, so it is an upper bound.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    records = [json.loads(line) for line in Path(argv[0]).read_text().splitlines()]

    def weight(r: dict) -> float:
        return r.get("weight", 1.0)

    dropped = [r for r in records if r["label"] == "dropped"]
    total_dropped = sum(map(weight, dropped))
    caught_by_placeholder = sum(
        weight(r) for r in dropped if r.get("placeholders_ok") is False
    )

    print(f"labelled segments {len(records)}, dropped {len(dropped)}")
    print(
        f"dropped segments already caught by a lost placeholder: "
        f"{caught_by_placeholder / max(total_dropped, 1e-9):.0%}\n"
    )
    print(f"{'min_ratio':>9} {'flagged':>8} {'precision':>10} {'recall':>7} {'f1':>5}")
    for step in range(20, 51, 1):
        threshold = step / 100
        flagged = [r for r in records if r["ratio"] < threshold]
        flagged_w = sum(map(weight, flagged))
        true_w = sum(weight(r) for r in flagged if r["label"] == "dropped")
        precision = true_w / flagged_w if flagged_w else 0.0
        recall = true_w / total_dropped if total_dropped else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        print(
            f"{threshold:9.2f} {flagged_w:8.0f} {precision:10.0%} {recall:7.0%} {f1:5.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
