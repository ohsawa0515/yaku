"""Pure text transformations that do not care what a line means."""

from __future__ import annotations

import re
import unicodedata

from yaku.types import SourceProfile

# OSC sequences (BEL- or ST-terminated, such as hyperlinks), CSI sequences,
# and the shorter two-character escapes. OSC comes first: its introducer
# is also a valid two-character escape.
ANSI = re.compile(r"\x1B(?:\][^\x07\x1B]*(?:\x07|\x1B\\)|[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

_INDENT = re.compile(r"^(\s*)(.*?)(\s*)$", re.DOTALL)

# What a log adds in front of every line: a timestamp, as CI systems print,
# then the vertical rule that frames a terraform diagnostic when colour is
# on ("13:17:22  │ Error: ..."). Both are layout, like indentation. Only a
# rule right at the start of the line is a frame; an indented one is part of
# the content, such as the expression values inside a diagnostic.
_GUTTER = re.compile(
    r"^(?:(?:\d{4}-\d{2}-\d{2}[T ])?\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?\s+)?"
    r"(?:[│┃] ?)?"
)


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


# Only colour and style sequences describe a state that can be replayed;
# erase and cursor controls would act a second time.
_SGR = re.compile(r"\x1B\[[0-9;:]*m")


def _display_width(ch: str) -> int:
    # Not just combining(): many marks (variation selectors, ZWJ, enclosing
    # marks) have combining class 0 but still take no column.
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def _resolve_line(line: str) -> str:
    if "\x08" not in line:
        return line
    # One entry per display column. None marks the second column of a wide
    # glyph. Escape sequences take no column, so they are kept beside the
    # column they were written at and survive an overwrite.
    cells: list[str | None] = []
    escapes: dict[int, str] = {}
    col = 0
    pos = 0
    seen: list[str] = []
    while pos < len(line):
        m = ANSI.match(line, pos)
        if m is not None:
            escapes[col] = escapes.get(col, "") + m.group(0)
            if _SGR.fullmatch(m.group(0)):
                seen.append(m.group(0))
            pos = m.end()
            continue
        ch = line[pos]
        pos += 1
        if ch == "\x08":
            col = max(0, col - 1)
            continue
        width = _display_width(ch)
        if width == 0:
            base = min(col, len(cells)) - 1
            while base > 0 and cells[base] is None:
                base -= 1
            if base >= 0 and cells[base] is not None:
                cells[base] += ch  # type: ignore[operator]
            continue
        cells.extend(" " for _ in range(col + width - len(cells)))
        for c in range(col, col + width):
            _clear_glyph(cells, c)
        cells[col : col + width] = [ch] + [None] * (width - 1)
        col += width
    out: list[str] = []
    for c in range(max(len(cells), max(escapes, default=-1) + 1)):
        out.append(escapes.get(c, ""))
        if c < len(cells) and cells[c] is not None:
            out.append(cells[c])  # type: ignore[arg-type]
    # Backspacing can place an escape before ones written earlier. When the
    # order changed, replay the whole sequence so the rendition in effect at
    # the end of the line is the one the input ended with.
    result = "".join(out)
    if [e for e in ANSI.findall(result) if _SGR.fullmatch(e)] != seen:
        result += "".join(seen)
    return result


def _clear_glyph(cells: list[str | None], col: int) -> None:
    """Blank every column of the glyph covering ``col``."""
    start = col - 1 if cells[col] is None else col
    cells[start] = " "
    for c in range(start + 1, len(cells)):
        if cells[c] is not None:
            break
        cells[c] = " "


def strip_overstrike(text: str) -> str:
    """Resolve backspace overstrikes the way ``col -b`` does.

    man writes bold as "N\\bN" and underline as "_\\bx". A backspace only moves
    the cursor, so the text is replayed per line by display column and the
    last character written to a column wins. Wide characters occupy two
    columns, which is why a plain "drop the character before the backspace"
    rule is not enough.
    """
    if "\x08" not in text:
        return text
    return "\n".join(_resolve_line(line) for line in text.split("\n"))


def split_indent(text: str) -> tuple[str, str, str]:
    """Split a line into leading whitespace, content and trailing whitespace."""
    m = _INDENT.match(text)
    if m is None:  # unreachable: the pattern accepts any string
        return "", text, ""
    return m.group(1), m.group(2), m.group(3)


def split_gutter(text: str) -> tuple[str, str]:
    """Split a log timestamp and a framing rule off the start of a line."""
    m = _GUTTER.match(text)
    if m is None or not m.group(0):
        return "", text
    return m.group(0), text[m.end() :]


def split_sentences(text: str, source: SourceProfile) -> list[str]:
    """Split masked text into translation units.

    Joining repairs lines that were wrapped for display, but a decoder starts
    dropping whole clauses once the input grows, so the joined text has to be
    cut back down.
    """

    parts = [p.strip() for p in source.sentence_split.split(text) if p.strip()]
    out: list[str] = []
    for part in parts:
        for clause in _split_lead_in(part, source):
            out.extend(_cut(clause, source.max_segment_chars))
    return out or [text]


def _split_lead_in(text: str, source: SourceProfile) -> list[str]:
    """Separate long lead-ins ending in a colon from what follows them."""
    if source.clause_split is None:
        return [text]
    listed = source.clause_list.search(text) if source.clause_list else None
    separator = listed.group(0)[0] if listed else None
    out: list[str] = []
    start = previous = 0
    for m in source.clause_split.finditer(text):
        if m.group(0)[0] == separator:
            continue
        # Words are counted from the previous candidate, not the previous
        # split, so that "do_one(); do_two();" never adds up to a clause.
        clause = text[previous : m.start()]
        previous = m.end()
        if len(source.word.findall(clause)) >= source.clause_min_words:
            out.append(text[start : m.start() + 1].strip())
            start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
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
