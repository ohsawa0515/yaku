"""Data contracts shared by every stage of the pipeline.

Nothing here imports a translation backend, so these types stay usable in tests that never load a model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class MaskRule:
    """One identifier-protection rule.

    ``order`` is explicit rather than implied by file position: rules live in
    several files that are all loaded together, and an earlier rule consuming
    a span changes what the later ones can still match.
    """

    name: str
    pattern: re.Pattern[str]
    order: int
    enabled: bool = True


@dataclass(frozen=True)
class SourceProfile:
    """Everything that depends on the language being translated from."""

    lang: str
    letter: re.Pattern[str]
    word: re.Pattern[str]
    min_alpha_ratio: float
    min_words: int
    sentence_end: re.Pattern[str]
    sentence_split: re.Pattern[str]
    max_segment_chars: int


@dataclass(frozen=True)
class TargetProfile:
    """Everything that depends on the language being translated to.

    The ratio bounds compare translated length against source length and are
    measured per language. ``placeholder_fmt`` is measured per model: a format
    that tokenises poorly costs accuracy on every masked span.
    """

    lang: str
    model_name: str
    min_ratio: float
    max_ratio: float
    already_translated: re.Pattern[str]
    quote_chars: str
    placeholder_fmt: str
    placeholder_pattern: re.Pattern[str]
    placeholder_loose: re.Pattern[str]
    # Where `yaku setup` fetches the model from. Optional, so that a profile
    # pointing at a locally converted model needs no upstream.
    model_repo: str = ""
    model_revision: str = ""
    model_license: str = ""

    def placeholder(self, index: int) -> str:
        return self.placeholder_fmt % index


@dataclass(frozen=True)
class Verdict:
    """Outcome of the quality gate for one line."""

    ok: bool
    reason: str = ""


OK = Verdict(True)


@dataclass
class Line:
    """One logical line, which may span several physical input lines."""

    # input
    raws: list[str] = field(default_factory=list)
    indent: str = ""
    body: str = ""
    trailing: str = ""
    translatable: bool = False

    # processing
    masked: str = ""
    values: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    segment_results: list[str] = field(default_factory=list)

    # output
    result: str | None = None
    verdict: Verdict = OK


class Engine(Protocol):
    """Inference backend.

    Decoding options are fixed when the engine is built, so callers never
    depend on the parameters of any one backend.
    """

    def translate(self, texts: list[str]) -> list[str]: ...
