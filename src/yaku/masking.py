"""Replacing identifiers with placeholders and putting them back.

The point is not to withhold text from the model but to show it well-formed prose.
Fragments the model never saw during training make it hallucinate or drop clauses,
and a missing placeholder is the only reliable signal that a clause went missing.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from yaku.types import MaskRule, TargetProfile

# Literal numbers vary between otherwise identical lines. Placeholder numbers
# do not: they say which value goes back where.
_NUMBER = re.compile(r"(?<![A-Za-z])\d+")


@dataclass
class Masker:
    """Applies mask rules in a fixed order and restores the values afterwards."""

    rules: list[MaskRule]
    target: TargetProfile
    _active: list[MaskRule] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._active = sorted(
            (rule for rule in self.rules if rule.enabled), key=lambda r: r.order
        )

    def mask(self, text: str) -> tuple[str, list[str]]:
        """Replace identifiers with placeholders, in rule order."""
        values: list[str] = []

        def replace(m: re.Match[str]) -> str:
            span = m.group(0)
            # A span holding a placeholder was produced by an earlier rule.
            # Masking it again would bury one number inside another.
            if self.target.placeholder_pattern.search(span):
                return span
            values.append(span)
            return self.target.placeholder(len(values))

        masked = text
        for rule in self._active:
            masked = rule.pattern.sub(replace, masked)
        return masked, values

    def unmask(self, text: str, values: list[str]) -> str:
        """Put the values back.

        Descending order matters: replacing T1 first would also rewrite the leading characters of T11.
        """

        restored = text
        for index in range(len(values), 0, -1):
            restored = restored.replace(
                self.target.placeholder(index), values[index - 1]
            )
        return restored

    def lost(self, text: str, count: int) -> int:
        """Placeholders that did not survive as standalone tokens.

        A placeholder vanishes when the clause around it was not translated,
        which no other check detects. A substring test is not enough: a
        decoder that emits "T1stdout" has kept the characters and lost the
        value, so only a whole-token match counts as restored.
        """
        intact = {n for n in self.target.placeholder_pattern.findall(text)}
        return sum(1 for i in range(1, count + 1) if str(i) not in intact)

    def residue(self, text: str, count: int) -> int:
        """Placeholder-like text that cannot be restored.

        Counts numbers that were never issued, repeats of one that was, and
        damaged forms such as a lower-cased or word-fused placeholder.
        """
        intact = Counter(self.target.placeholder_pattern.findall(text))
        every = Counter(self.target.placeholder_loose.findall(text))
        extra = 0
        for number, times in every.items():
            if not 1 <= int(number) <= count:
                extra += times
            else:
                extra += times - min(intact[number], 1)
        return extra

    def template(self, masked: str) -> str:
        """Cache key for a masked line.

        Log output repeats the same sentence with different numbers, so collapsing literal numbers raises the hit rate.
        The lookbehind spares placeholder numbers, which decide which value is restored where.
        """
        return _NUMBER.sub("#", masked)
