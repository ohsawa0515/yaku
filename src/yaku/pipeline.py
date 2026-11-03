"""Turning a block of command output into translated lines.

The whole input is read before anything is translated. That allows one
analysis pass over it, which is how the shape of the input is determined
instead of being declared on the command line.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from yaku.cache import Cache
from yaku.classify import is_passthrough, is_translatable, looks_like_command
from yaku.masking import Masker
from yaku.quality import judge
from yaku.text import split_gutter, split_indent, split_sentences, strip_ansi
from yaku.types import OK, Engine, Line, SourceProfile, TargetProfile, Verdict

# Share of translatable lines that do not end in sentence punctuation, above
# which the input is treated as wrapped prose rather than one record per line.
# Measured at 0.61-0.77 for manual pages, command help and pasted articles,
# and 0.00-0.29 for terraform plan and kubectl table output.
WRAP_THRESHOLD = 0.45

# A continuation fragment is short by nature. Anything longer is a line of its
# own that simply lacks final punctuation.
MAX_FRAGMENT = 60

# Without a bound, a run of unpunctuated lines would be joined into a single
# request long enough for the decoder to drop clauses from it.
MAX_JOINED_LINES = 12

# A line at least this share of the widest line was filled to the wrap
# column. Only consulted when the input as a whole is not joined.
WRAPPED_LINE_SHARE = 0.85

_SPACES = re.compile(r"\s{2,}")

# Characters that may not begin a line of Japanese text.
_NO_LINE_START = "、。，．・：；？！」』）】〕〉》ー,.:;?!)]}"

# A log record after its timestamp: "- MainThread - botocore - DEBUG - ...",
# "[ERROR] vertex ...". Each record stands alone and is never joined.
_LOG_LEVEL = re.compile(r"^\[?(?:TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\]?[\s:]")
_LOG_DASH = re.compile(r"^-\s")

# Inside a Python traceback every indented line is a frame or source code.
_TRACEBACK = re.compile(r"^\s*Traceback \(most recent call last\):\s*$")


def _join_segments(results: Sequence[str]) -> str:
    """Concatenate translated segments, keeping ASCII words apart.

    Japanese needs no separator, but a segment ending in a placeholder next to
    one that starts with another would otherwise fuse into one token.
    """
    out = ""
    for result in results:
        head = result[:1]
        if out and out[-1].isascii() and out[-1].isalnum() and head.isascii() and head.isalnum():
            out += " "
        out += result
    return out


@dataclass(frozen=True)
class _Pending:
    raw: str
    plain: str
    indent: str
    body: str
    trailing: str


@dataclass
class Stats:
    lines: int = 0
    translated: int = 0
    flagged: int = 0
    cached: int = 0
    requested: int = 0
    joined: bool = False
    wrap_ratio: float = 0.0

    @property
    def flagged_share(self) -> float:
        return self.flagged / max(self.translated, 1)


@dataclass
class Pipeline:
    engine: Engine
    masker: Masker
    source: SourceProfile
    target: TargetProfile
    passthrough: Sequence[re.Pattern[str]]
    cache: Cache
    fallback: str = "both"
    join: bool | None = None
    width: int = 0
    show_reason: bool = False
    stats: Stats = field(default_factory=Stats)

    # -- analysis ---------------------------------------------------------

    def wrap_ratio(self, raw_lines: Sequence[str]) -> float:
        """Share of translatable lines that do not end a sentence.

        Manual pages wrap one sentence over several lines, so most of their
        lines end mid-sentence. Log output completes a record per line.
        """
        total = unfinished = 0
        for raw in raw_lines:
            _, body, _, ok, _ = self._classify(raw)
            if not ok:
                continue
            total += 1
            if not self.source.sentence_end.search(body):
                unfinished += 1
        return unfinished / total if total else 0.0

    # -- classification ---------------------------------------------------

    def _classify(self, raw: str) -> tuple[str, str, str, bool, str]:
        """Return indent, body, trailing whitespace, translatability, and the
        line as the rules see it: without colour and without a frame."""
        gutter, plain = split_gutter(strip_ansi(raw))
        indent, body, trailing = split_indent(plain)
        # Passthrough rules see the indentation: it is often the only thing
        # that tells a table row or a source excerpt from a sentence.
        translatable = (
            not is_passthrough(plain, self.passthrough)
            and not looks_like_command(body)
            and is_translatable(body, self.source, self.target)
        )
        return gutter + indent, body, trailing, translatable, plain

    def _is_fragment(self, line: str, body: str, pending: list[_Pending]) -> bool:
        """Whether a rejected line continues the sentence above it.

        A wrapped sentence can end in a fragment of one or two words, which
        is too short to look like prose on its own and would otherwise be
        emitted untranslated in the middle of a translated paragraph.
        """
        return (
            bool(pending)
            and bool(body.strip())
            and len(body) <= MAX_FRAGMENT
            and not self.source.sentence_end.search(pending[-1].body)
            and not is_passthrough(line, self.passthrough)
            and not looks_like_command(body)
            and self.target.already_translated.search(body) is None
            and bool(self.source.letter.search(body))
        )

    def _wraps_into(self, previous: _Pending, body: str, width: int) -> bool:
        """Whether a line is visibly the continuation of the one above.

        Used when the input as a whole is not joined. Output that is mostly
        one record per line still contains wrapped paragraphs, such as the
        explanation under a terraform error. A line filled almost to the
        wrap column, left unfinished, and followed by a line that does not
        start a new sentence was wrapped, not ended.
        """
        return (
            width > 0
            and not self.source.sentence_end.search(previous.body)
            and len(previous.plain.rstrip()) >= WRAPPED_LINE_SHARE * width
            and bool(body)
            and not body[0].isupper()
        )

    def _wrap_width(self, raw_lines: Sequence[str]) -> int:
        """Estimate the column the input was wrapped at."""
        return max(
            (len(strip_ansi(raw).rstrip()) for raw in raw_lines if self._classify(raw)[3]),
            default=0,
        )

    def prepare(self, raw_lines: Sequence[str]) -> list[Line]:
        if self.join is None:
            ratio = self.wrap_ratio(raw_lines)
            self.stats.wrap_ratio = ratio
            self.join = ratio >= WRAP_THRESHOLD
        self.stats.joined = self.join
        width = 0 if self.join else self._wrap_width(raw_lines)

        out: list[Line] = []
        pending: list[_Pending] = []

        def flush() -> None:
            if not pending:
                return
            body = " ".join(p.body.strip() for p in pending)
            line = Line(
                raws=[p.raw for p in pending],
                indent=pending[0].indent,
                body=body,
                trailing=pending[0].trailing if len(pending) == 1 else "",
                translatable=True,
            )
            self._attach(line, body)
            out.append(line)
            pending.clear()

        in_traceback = False
        for raw in raw_lines:
            indent, body, trailing, translatable, plain = self._classify(raw)
            if _TRACEBACK.match(plain):
                flush()
                in_traceback, translatable = True, False
            elif in_traceback and plain[:1].isspace():
                translatable = False
            else:
                in_traceback = False
            # A digit in the prefix means a timestamp was split off the line.
            # Lines of a traceback are records too: none of them continues
            # the sentence above.
            record = (
                in_traceback
                or bool(_LOG_LEVEL.match(body))
                or (any(c.isdigit() for c in indent) and bool(_LOG_DASH.match(body)))
            )
            # A timestamp that differs from the one above starts a new record
            # even when the line carries no log level.
            if pending and any(c.isdigit() for c in indent) and indent != pending[-1].indent:
                record = True
            if record:
                flush()
            current = _Pending(raw, plain, indent, body, trailing)
            wraps = bool(pending) and not record and self._wraps_into(pending[-1], body, width)

            if not translatable:
                if not record and (self.join or wraps) and self._is_fragment(plain, body, pending):
                    pending.append(current)
                    continue
                flush()
                out.append(
                    Line(
                        raws=[raw],
                        indent=indent,
                        body=body,
                        trailing=trailing,
                        translatable=False,
                    )
                )
                continue

            if record:
                pass
            elif pending:
                if len(pending) >= MAX_JOINED_LINES:
                    flush()
                elif self.join:
                    # A continuation line is often indented more deeply than
                    # the line that starts the sentence, so indentation only
                    # ends a paragraph once the previous line also finished.
                    finished = bool(self.source.sentence_end.search(pending[-1].body))
                    if finished and pending[0].indent != indent:
                        flush()
                elif not wraps:
                    flush()
            pending.append(current)

        flush()
        self.stats.lines = len(out)
        return out

    def _attach(self, line: Line, body: str) -> None:
        masked, line.values = self.masker.mask(body)
        # Runs of spaces are collapsed after masking so that protected
        # values keep their original spacing.
        line.masked = _SPACES.sub(" ", masked).strip()
        line.segments = split_sentences(line.masked, self.source)

    # -- translation ------------------------------------------------------

    def run(self, lines: Sequence[Line]) -> None:
        pending: list[tuple[Line, int, str]] = []
        for line in lines:
            if not line.translatable:
                continue
            self.stats.translated += 1
            line.segment_results = [""] * len(line.segments)
            for index, segment in enumerate(line.segments):
                hit = self.cache.get(segment)
                if hit is not None:
                    line.segment_results[index] = hit
                    self.stats.cached += 1
                else:
                    pending.append((line, index, segment))

        if pending:
            self.stats.requested = len(pending)
            outputs = self.engine.translate([p[2] for p in pending])
            for (line, index, segment), output in zip(pending, outputs, strict=True):
                line.segment_results[index] = output
                self.cache.put(segment, output)
            self.cache.commit()

        for line in lines:
            if not line.translatable:
                continue
            line.result = _join_segments(line.segment_results)
            line.verdict = self._verdict(line)
            if not line.verdict.ok:
                self.stats.flagged += 1

    def _verdict(self, line: Line) -> Verdict:
        """Judge each segment, then the restored line as a whole.

        Segments are checked separately because a clause dropped from one of
        them leaves the concatenated length plausible.
        """
        for segment, result in zip(line.segments, line.segment_results, strict=True):
            verdict = judge(segment, result, None, self.masker, self.target)
            if not verdict.ok:
                return verdict
        if line.result is None:
            return OK
        return judge(line.masked, line.result, len(line.values), self.masker, self.target)

    # -- output -----------------------------------------------------------

    def render(self, line: Line) -> list[str]:
        if not line.translatable or line.result is None:
            return line.raws

        restored = self.masker.unmask(line.result, line.values)

        if not line.verdict.ok:
            note = f"  # {line.verdict.reason}" if self.show_reason else ""
            if self.fallback == "original":
                return line.raws
            if self.fallback == "mark":
                return [f"{line.indent}* {restored}{note}"]
            return [*line.raws, f"{line.indent}  -> {restored}{note}"]

        if len(line.raws) > 1 or self.width > 0:
            return self._wrap(self._units(line.result, line.values), line.indent)
        return [f"{line.indent}{restored}{line.trailing}"]

    def _units(self, result: str, values: list[str]) -> list[str]:
        """Split a translation into characters and whole protected values."""
        units: list[str] = []
        position = 0
        for m in self.target.placeholder_pattern.finditer(result):
            units.extend(result[position : m.start()])
            index = int(m.group(1))
            units.append(values[index - 1] if 1 <= index <= len(values) else m.group(0))
            position = m.end()
        units.extend(result[position:])
        return units

    def _wrap(self, units: Sequence[str], indent: str) -> list[str]:
        """Wrap units to the requested width; a unit is never split."""
        if self.width <= 0:
            return [indent + "".join(units)]
        room = max(self.width - len(indent), 20)
        out: list[str] = []
        current = ""
        for index, unit in enumerate(units):
            current += unit
            if len(current) < room:
                continue
            char = unit[-1]
            following = units[index + 1][:1] if index + 1 < len(units) else ""
            # Never cut inside an ASCII word (a restored identifier) and never
            # start a line with a character that may not begin one.
            inside_word = (
                char.isascii()
                and not char.isspace()
                and following.isascii()
                and not following.isspace()
            )
            if following and (inside_word or following in _NO_LINE_START):
                continue
            out.append(indent + current)
            current = ""
        if current:
            out.append(indent + current)
        return out or [indent + "".join(units)]
