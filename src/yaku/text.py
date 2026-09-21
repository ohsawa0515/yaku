"""Pure text transformations that do not care what a line means."""

from __future__ import annotations

import re

from yaku.types import SourceProfile

# CSI sequences plus the shorter two-character escapes.
ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

_INDENT = re.compile(r"^(\s*)(.*?)(\s*)$", re.DOTALL)


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def split_indent(text: str) -> tuple[str, str, str]:
    """Split a line into leading whitespace, content and trailing whitespace."""
    m = _INDENT.match(text)
    if m is None:  # unreachable: the pattern accepts any string
        return "", text, ""
    return m.group(1), m.group(2), m.group(3)


def split_sentences(text: str, source: SourceProfile) -> list[str]:
    """Split masked text into translation units.

    Joining repairs lines that were wrapped for display, but a decoder starts
    dropping whole clauses once the input grows, so the joined text has to be
    cut back down.
    """

    parts = [p.strip() for p in source.sentence_split.split(text) if p.strip()]
    out: list[str] = []
    for part in parts:
        out.extend(_cut(part, source.max_segment_chars))
    return out or [text]


def _cut(text: str, limit: int) -> list[str]:
    """Break one over-long sentence at the last comma, then the last space."""

    out: list[str] = []
    while len(text) > limit:
        head = text[:limit]
        cut = max((m.end() for m in re.finditer(r"[,;]\s+", head)), default=-1)
        if cut <= 0:
            cut = head.rfind(" ")
        if cut <= 0:
            cut = limit
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out
