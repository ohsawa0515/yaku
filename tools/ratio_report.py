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

With --band and --flag-at, it also prints the drop rate per ratio band with a
95% Wilson interval. Small bands are noisy, so the rates are first made
non-increasing in the ratio (pool adjacent violators, weighted by band size):
a shorter translation is never assumed less likely to have dropped text.
The implied threshold is the top of the last band whose smoothed rate is at
least --flag-at. That rate follows from the relative cost of the two errors:
flag when

    P(dropped) * cost_of_a_miss  >=  P(complete) * cost_of_a_false_flag

so a miss that costs three times a false flag gives --flag-at 0.25.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - spread), min(1.0, centre + spread)


def pool_adjacent_violators(rates: list[float], sizes: list[int]) -> list[float]:
    """Closest non-increasing sequence to rates, weighted by sizes."""
    blocks = [[r * n, n, 1] for r, n in zip(rates, sizes, strict=True)]  # hits, size, members
    merged: list[list[float]] = []
    for block in blocks:
        merged.append(block)
        while len(merged) > 1 and (merged[-2][0] / merged[-2][1] < merged[-1][0] / merged[-1][1]):
            hits, size, members = merged.pop()
            merged[-1][0] += hits
            merged[-1][1] += size
            merged[-1][2] += members
    out: list[float] = []
    for hits, size, members in merged:
        out.extend([hits / size] * int(members))
    return out


def band_table(records: list[dict], width: float, flag_at: float) -> None:
    bands: dict[int, list[dict]] = {}
    for r in records:
        bands.setdefault(int(r["ratio"] / width + 1e-9), []).append(r)
    keys = sorted(bands)
    hits = [sum(1 for r in bands[k] if r["label"] == "dropped") for k in keys]
    sizes = [len(bands[k]) for k in keys]
    smooth = pool_adjacent_violators([h / n for h, n in zip(hits, sizes, strict=True)], sizes)

    print(
        f"\n{'band':>11} {'labelled':>8} {'dropped':>7} {'rate':>5}"
        f"  {'95% interval':>12} {'smoothed':>8}"
    )
    threshold = None
    for key, h, n, rate in zip(keys, hits, sizes, smooth, strict=True):
        low, high = wilson(h, n)
        hi_edge = (key + 1) * width
        mark = "  flag" if rate >= flag_at else ""
        if rate >= flag_at:
            threshold = hi_edge
        print(
            f"{key * width:5.2f}-{hi_edge:4.2f} {n:8} {h:7} {h / n:5.0%}"
            f"  {low:4.0%}-{high:4.0%}   {rate:8.0%}{mark}"
        )
    if threshold is None:
        print(f"\nno band reaches {flag_at:.0%}: the ratio check should flag nothing")
    else:
        print(f"\nimplied min_ratio at {flag_at:.0%}: {threshold:.2f}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("labelled", type=Path)
    parser.add_argument("--band", type=float, default=0.0, help="band width, e.g. 0.05")
    parser.add_argument("--flag-at", type=float, default=0.25)
    args = parser.parse_args(argv)
    records = [json.loads(line) for line in args.labelled.read_text().splitlines()]
    records = [r for r in records if r.get("label") in ("complete", "dropped")]

    def weight(r: dict) -> float:
        return r.get("weight", 1.0)

    dropped = [r for r in records if r["label"] == "dropped"]
    total_dropped = sum(map(weight, dropped))
    caught_by_placeholder = sum(weight(r) for r in dropped if r.get("placeholders_ok") is False)

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
        print(f"{threshold:9.2f} {flagged_w:8.0f} {precision:10.0%} {recall:7.0%} {f1:5.2f}")
    if args.band:
        band_table(records, args.band, args.flag_at)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
