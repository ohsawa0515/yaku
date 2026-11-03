"""Detecting translations that dropped text or ran away.

A sequence model cannot be stopped from skipping a clause, so each result is
checked afterwards and the caller decides what to show.
"""

from __future__ import annotations

import re

from yaku.masking import Masker
from yaku.types import OK, TargetProfile, Verdict

# Four or more characters repeated at least four times. Shorter units match
# ordinary writing; a real decoding loop repeats far longer than this.
_REPETITION = re.compile(r"(.{4,20}?)\1{3,}")


def judge(
    source: str,
    translated: str,
    placeholders: int | None,
    masker: Masker,
    target: TargetProfile,
) -> Verdict:
    """Decide whether one translated segment can be trusted.

    Three independent signals, cheapest first. A lost placeholder is proof
    that a clause went missing; the length ratio catches drops that happened
    to take no placeholder with them.

    ``placeholders`` is how many were issued for this text, or None when the
    text is a fragment whose placeholders cannot be counted.
    """
    if not translated.strip():
        return Verdict(False, "empty output")

    if placeholders is not None:
        lost = masker.lost(translated, placeholders)
        if lost:
            return Verdict(False, f"placeholder lost ({lost}/{placeholders})")

        extra = masker.residue(translated, placeholders, source)
        if extra:
            return Verdict(False, f"placeholder residue ({extra})")

    if masker.reordered(source, translated):
        return Verdict(False, "placeholder order changed")

    ratio = len(translated) / max(len(source), 1)
    if ratio < target.min_ratio:
        return Verdict(False, f"too short (ratio {ratio:.2f})")
    if ratio > target.max_ratio:
        return Verdict(False, f"too long (ratio {ratio:.2f})")

    if _REPETITION.search(translated):
        return Verdict(False, "repetition loop")

    return OK
