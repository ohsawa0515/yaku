"""Reading rule files into the typed objects the pipeline uses."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from yaku import paths
from yaku.types import MaskRule, SourceProfile, TargetProfile


class RuleError(Exception):
    """A rule file is missing, malformed, or holds a bad regular expression."""


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise RuleError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuleError(f"invalid TOML in {path}: {exc}") from exc


def _compile(pattern: str, where: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise RuleError(f"invalid pattern in {where}: {pattern!r}: {exc}") from exc


def _syntax_files(dirs: Sequence[Path]) -> list[Path]:
    """Every syntax file, lowest precedence directory first."""
    return [p for d in dirs for p in sorted((d / "syntax").glob("*.toml"))]


def load_mask_rules(dirs: Sequence[Path] | None = None) -> list[MaskRule]:
    """Mask rules from every syntax file, sorted by order.

    A later directory replaces a rule of the same name, which lets a user adjust one pattern without copying the whole shipped set.
    """
    by_name: dict[str, MaskRule] = {}
    for path in _syntax_files(paths.rule_dirs() if dirs is None else dirs):
        for entry in _read(path).get("rule", []):
            try:
                name, order = entry["name"], entry["order"]
                pattern = entry["pattern"]
            except KeyError as exc:
                raise RuleError(f"{path}: rule is missing key {exc}") from exc
            by_name[name] = MaskRule(
                name=name,
                pattern=_compile(pattern, f"{path}:{name}"),
                order=order,
                enabled=entry.get("enabled", True),
            )
    rules = sorted(by_name.values(), key=lambda rule: rule.order)
    _reject_duplicate_orders(rules)
    return rules


def _reject_duplicate_orders(rules: Sequence[MaskRule]) -> None:
    """Two rules sharing an order would be applied in an arbitrary sequence."""
    seen: dict[int, str] = {}
    for rule in rules:
        if rule.order in seen:
            raise RuleError(
                f"duplicate order {rule.order}: {seen[rule.order]} and {rule.name}"
            )
        seen[rule.order] = rule.name


def load_passthrough(dirs: Sequence[Path] | None = None) -> list[re.Pattern[str]]:
    """Patterns for lines that are emitted unchanged.

    These have no order: a line is passed through if any pattern matches.
    """
    by_name: dict[str, re.Pattern[str]] = {}
    for path in _syntax_files(paths.rule_dirs() if dirs is None else dirs):
        for entry in _read(path).get("passthrough", []):
            try:
                name, pattern = entry["name"], entry["pattern"]
            except KeyError as exc:
                raise RuleError(f"{path}: passthrough is missing key {exc}") from exc
            by_name[name] = _compile(pattern, f"{path}:{name}")
    return list(by_name.values())


def _profile(kind: str, lang: str, dirs: Sequence[Path]) -> dict[str, Any]:
    """Merge one language file across the rule directories."""
    merged: dict[str, Any] = {}
    for directory in dirs:
        path = directory / kind / f"{lang}.toml"
        if path.is_file():
            merged.update(_read(path))
    if not merged:
        raise RuleError(f"no {kind} profile for language {lang!r}")
    return merged


def load_source(lang: str, dirs: Sequence[Path] | None = None) -> SourceProfile:
    data = _profile("source", lang, paths.rule_dirs() if dirs is None else dirs)
    where = f"source/{lang}.toml"
    try:
        return SourceProfile(
            lang=data["lang"],
            letter=_compile(data["letter"], where),
            word=_compile(data["word"], where),
            min_alpha_ratio=data["min_alpha_ratio"],
            min_words=data["min_words"],
            sentence_end=_compile(data["sentence_end"], where),
            sentence_split=_compile(data["sentence_split"], where),
            max_segment_chars=data["max_segment_chars"],
            clause_split=_compile(data["clause_split"], where)
            if "clause_split" in data
            else None,
            clause_min_words=data.get("clause_min_words", 0),
            clause_list=_compile(data["clause_list"], where)
            if "clause_list" in data
            else None,
        )
    except KeyError as exc:
        raise RuleError(f"{where} is missing key {exc}") from exc


def load_target(lang: str, dirs: Sequence[Path] | None = None) -> TargetProfile:
    data = _profile("target", lang, paths.rule_dirs() if dirs is None else dirs)
    where = f"target/{lang}.toml"
    try:
        return TargetProfile(
            lang=data["lang"],
            model_name=data["model_name"],
            min_ratio=data["min_ratio"],
            max_ratio=data["max_ratio"],
            already_translated=_compile(data["already_translated"], where),
            quote_chars=data["quote_chars"],
            placeholder_fmt=data["placeholder_fmt"],
            placeholder_pattern=_compile(data["placeholder_pattern"], where),
            placeholder_loose=_compile(data["placeholder_loose"], where),
            model_repo=data.get("model_repo", ""),
            model_revision=data.get("model_revision", ""),
            model_license=data.get("model_license", ""),
        )
    except KeyError as exc:
        raise RuleError(f"{where} is missing key {exc}") from exc
