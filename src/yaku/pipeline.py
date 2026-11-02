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
from yaku.text import split_indent, split_sentences, strip_ansi
from yaku.types import OK, Engine, Line, SourceProfile, TargetProfile, Verdict

# Share of translatable lines that do not end in sentence punctuation, above
# which the input is treated as wrapped prose rather than one record per line.
WRAP_THRESHOLD = 0.35

# A continuation fragment is short by nature. Anything longer is a line of its
# own that simply lacks final punctuation.
MAX_FRAGMENT = 60

# Without a bound, a run of unpunctuated lines would be joined into a single
# request long enough for the decoder to drop clauses from it.
MAX_JOINED_LINES = 12

_SPACES = re.compile(r"\s{2,}")


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
            _, body, _, ok = self._classify(raw)
            if not ok:
                continue
            total += 1
            if not self.source.sentence_end.search(body):
                unfinished += 1
        return unfinished / total if total else 0.0

    # -- classification ---------------------------------------------------

    def _classify(self, raw: str) -> tuple[str, str, str, bool]:
        indent, body, trailing = split_indent(strip_ansi(raw))
        translatable = (
            not is_passthrough(body, self.passthrough)
            and not looks_like_command(body)
            and is_translatable(body, self.source, self.target)
        )
        return indent, body, trailing, translatable

    def _is_fragment(self, body: str, pending: list[tuple[str, str, str]]) -> bool:
        """Whether a rejected line continues the sentence above it.

        A wrapped sentence can end in a fragment of one or two words, which
        is too short to look like prose on its own and would otherwise be
        emitted untranslated in the middle of a translated paragraph.
        """
        return (
            bool(pending)
            and bool(body.strip())
            and len(body) <= MAX_FRAGMENT
            and not self.source.sentence_end.search(pending[-1][2])
            and not is_passthrough(body, self.passthrough)
            and not looks_like_command(body)
            and bool(self.source.letter.search(body))
        )

    def prepare(self, raw_lines: Sequence[str]) -> list[Line]:
        if self.join is None:
            ratio = self.wrap_ratio(raw_lines)
            self.stats.wrap_ratio = ratio
            self.join = ratio >= WRAP_THRESHOLD
        self.stats.joined = self.join

        out: list[Line] = []
        pending: list[tuple[str, str, str]] = []

        def flush() -> None:
            if not pending:
                return
            body = _SPACES.sub(" ", " ".join(p[2] for p in pending)).strip()
            line = Line(
                raws=[p[0] for p in pending],
                indent=pending[0][1],
                body=body,
                translatable=True,
            )
            self._attach(line, body)
            out.append(line)
            pending.clear()

        for raw in raw_lines:
            indent, body, trailing, translatable = self._classify(raw)

            if self.join and not translatable and self._is_fragment(body, pending):
                pending.append((raw, indent, body))
                continue

            if not translatable:
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

            if not self.join:
                line = Line(
                    raws=[raw],
                    indent=indent,
                    body=body,
                    trailing=trailing,
                    translatable=True,
                )
                self._attach(line, body)
                out.append(line)
                continue

            # A continuation line is often indented more deeply than the line
            # that starts the sentence, so indentation only ends a paragraph
            # once the previous line also finished a sentence.
            if pending:
                finished = bool(self.source.sentence_end.search(pending[-1][2]))
                if (finished and pending[0][1] != indent) or len(
                    pending
                ) >= MAX_JOINED_LINES:
                    flush()
            pending.append((raw, indent, body))

        flush()
        self.stats.lines = len(out)
        return out

    def _attach(self, line: Line, body: str) -> None:
        line.masked, line.values = self.masker.mask(body)
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
                hit = self.cache.get(self.masker.template(segment))
                if hit is not None:
                    line.segment_results[index] = hit
                    self.stats.cached += 1
                else:
                    pending.append((line, index, segment))

        if pending:
            self.stats.requested = len(pending)
            outputs = self.engine.translate([p[2] for p in pending])
            for (line, index, segment), output in zip(pending, outputs):
                line.segment_results[index] = output
                self.cache.put(self.masker.template(segment), output)
            self.cache.commit()

        for line in lines:
            if not line.translatable:
                continue
            line.result = "".join(line.segment_results)
            line.verdict = self._verdict(line)
            if not line.verdict.ok:
                self.stats.flagged += 1

    def _verdict(self, line: Line) -> Verdict:
        """Judge each segment, then the restored line as a whole.

        Segments are checked separately because a clause dropped from one of
        them leaves the concatenated length plausible.
        """
        for segment, result in zip(line.segments, line.segment_results):
            verdict = judge(segment, result, 0, self.masker, self.target)
            if not verdict.ok:
                return verdict
        if line.result is None:
            return OK
        return judge(
            line.masked, line.result, len(line.values), self.masker, self.target
        )

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
            return self._wrap(restored, line.indent)
        return [f"{line.indent}{restored}{line.trailing}"]

    def _wrap(self, text: str, indent: str) -> list[str]:
        if self.width <= 0:
            return [f"{indent}{text}"]
        room = max(self.width - len(indent), 20)
        out: list[str] = []
        current = ""
        for char in text:
            current += char
            # Japanese has no spaces to break on, so lines end after a
            # character that may not begin one.
            if len(current) >= room and char in "、。」）":
                out.append(indent + current)
                current = ""
        if current:
            out.append(indent + current)
        return out or [indent + text]
