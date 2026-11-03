"""Replacing identifiers with placeholders and putting them back.

The point is not to withhold text from the model but to show it well-formed prose.
Fragments the model never saw during training make it hallucinate or drop clauses,
and a missing placeholder is the only reliable signal that a clause went missing.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import partial

from yaku.types import MaskRule, TargetProfile

_CLOSING = ".,;:"
_WORD = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class _Adjacency:
    """Where the previous match of the current rule ended."""

    end: int = -1
    index: int | None = None


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

        # Text that already looks like a placeholder would collide with the
        # ones issued below, so it is carried through as a value itself.
        def keep_literal(m: re.Match[str]) -> str:
            values.append(m.group(0))
            return self.target.placeholder(len(values))

        def replace(m: re.Match[str], encloses: bool, adjacent: _Adjacency) -> str:
            span = m.group(0)
            holds_placeholder = self.target.placeholder_pattern.search(span) is not None
            # A span holding a placeholder was produced by an earlier rule.
            # Masking it again would bury one number inside another, so only
            # rules that enclose their contents take it over, as original text.
            if holds_placeholder and not encloses:
                return span
            # A placeholder glued to a letter or digit ("T1hostname") is
            # indistinguishable from one the decoder damaged, so the loss
            # check could not be trusted. Leave such spans in place.
            if _glued(m.string, m.start(), m.end()):
                return span
            if holds_placeholder:
                span = self.unmask(span, values)
            # Punctuation that ends a sentence or clause belongs to the
            # sentence, not to the path or URL before it. Masking it would
            # hide the boundary from the sentence splitter.
            tail = ""
            if len(span) > 1 and span[-1] in _CLOSING and _at_break(m.string, m.end()):
                span, tail = span[:-1], span[-1]
            # Two placeholders that touch would read as one unknown token, so
            # touching matches of one rule become a single value.
            if adjacent.end == m.start() and adjacent.index is not None:
                values[adjacent.index] += span
                placeholder = ""
            else:
                values.append(span)
                adjacent.index = len(values) - 1
                placeholder = self.target.placeholder(len(values))
            adjacent.end = m.end() if not tail else -1
            return placeholder + tail

        masked = self.target.placeholder_pattern.sub(keep_literal, text)
        for rule in self._active:
            adjacent = _Adjacency()
            masked = rule.pattern.sub(
                partial(replace, encloses=rule.encloses, adjacent=adjacent), masked
            )
        return self._compact(masked, values)

    def _compact(self, masked: str, values: list[str]) -> tuple[str, list[str]]:
        """Renumber placeholders in order of appearance, dropping absorbed ones."""
        kept: list[str] = []

        def renumber(m: re.Match[str]) -> str:
            kept.append(values[int(m.group(1)) - 1])
            return self.target.placeholder(len(kept))

        return self.target.placeholder_pattern.sub(renumber, masked), kept

    def unmask(self, text: str, values: list[str]) -> str:
        """Put the values back in a single pass.

        Substituting one placeholder at a time would also rewrite
        placeholder-like text inside a value that was just restored.
        """

        def restore(m: re.Match[str]) -> str:
            index = int(m.group(1))
            return values[index - 1] if 1 <= index <= len(values) else m.group(0)

        return self.target.placeholder_pattern.sub(restore, text)

    def reordered(self, source: str, text: str) -> bool:
        """Whether a sentence that opens with a placeholder lost that opening.

        Swapped placeholders keep every count intact while changing which
        value the sentence is about ("T1 will replace T2" read as T2 replacing
        T1), so the loss checks cannot see them. Only the subject position is
        checked: other reorderings are ordinary Japanese word order.
        """
        found = self.target.placeholder_pattern.findall(source)
        if len(set(found)) < 2:
            return False
        first = self.target.placeholder_pattern.search(source)
        if first is None or source[: first.start()].strip():
            return False
        order = [n for n in self.target.placeholder_pattern.findall(text) if n in set(found)]
        return bool(order) and order[0] != found[0]

    def lost(self, text: str, count: int) -> int:
        """Placeholders that did not survive as standalone tokens.

        A placeholder vanishes when the clause around it was not translated,
        which no other check detects. A substring test is not enough: a
        decoder that emits "T1stdout" has kept the characters and lost the
        value, so only a whole-token match counts as restored.
        """
        intact = {int(n) for n in self.target.placeholder_pattern.findall(text)}
        return sum(1 for i in range(1, count + 1) if i not in intact)

    def residue(self, text: str, count: int, source: str = "") -> int:
        """Placeholder-like text that cannot be restored.

        Counts numbers that were never issued, repeats of one that was, and
        damaged forms such as a lower-cased or word-fused placeholder. Words
        that were already in the source, such as "ext4", are not damage.
        """
        known = {
            w
            for w in _WORD.findall(source)
            if self.target.placeholder_loose.search(w)
            and not self.target.placeholder_pattern.fullmatch(w)
        }
        if known:
            text = _WORD.sub(lambda m: " " if m[0] in known else m[0], text)
        intact = Counter(int(n) for n in self.target.placeholder_pattern.findall(text))
        if count == 0:
            # Nothing was issued, so any standalone placeholder is invented.
            # The loose form is not used: it matches inside ordinary words.
            return sum(intact.values())
        every = Counter(int(n) for n in self.target.placeholder_loose.findall(text))
        extra = 0
        for number, times in every.items():
            if not 1 <= number <= count:
                extra += times
            else:
                extra += times - min(intact[number], 1)
        return extra
