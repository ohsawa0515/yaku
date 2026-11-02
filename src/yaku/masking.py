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

_CLOSING = ".,;:"


def _at_break(text: str, end: int) -> bool:
    return end == len(text) or text[end].isspace()


def _glued(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return (before.isascii() and before.isalnum()) or (after.isascii() and after.isalnum())


@dataclass
class Masker:
    """Applies mask rules in a fixed order and restores the values afterwards."""

    rules: list[MaskRule]
    target: TargetProfile
    _active: list[MaskRule] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._active = sorted((rule for rule in self.rules if rule.enabled), key=lambda r: r.order)

    def mask(self, text: str) -> tuple[str, list[str]]:
        """Replace identifiers with placeholders, in rule order."""
        values: list[str] = []

        def replace(m: re.Match[str]) -> str:
            span = m.group(0)
            # A span holding a placeholder was produced by an earlier rule.
            # Masking it again would bury one number inside another.
            if self.target.placeholder_pattern.search(span):
                return span
            # A placeholder glued to a letter or digit ("T1hostname") is
            # indistinguishable from one the decoder damaged, so the loss
            # check could not be trusted. Leave such spans in place.
            if _glued(m.string, m.start(), m.end()):
                return span
            # Punctuation that ends a sentence or clause belongs to the
            # sentence, not to the path or URL before it. Masking it would
            # hide the boundary from the sentence splitter.
            tail = ""
            if len(span) > 1 and span[-1] in _CLOSING and _at_break(m.string, m.end()):
                span, tail = span[:-1], span[-1]
            values.append(span)
            return self.target.placeholder(len(values)) + tail

        masked = text
        for rule in self._active:
            masked = rule.pattern.sub(replace, masked)
        return masked, values

    def unmask(self, text: str, values: list[str]) -> str:
        """Put the values back.

        Descending order matters: replacing T1 first would also rewrite the
        leading characters of T11.
        """

        restored = text
        for index in range(len(values), 0, -1):
            restored = restored.replace(self.target.placeholder(index), values[index - 1])
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
