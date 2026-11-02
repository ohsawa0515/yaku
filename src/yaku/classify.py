"""Deciding what to do with each line: pass it through, or translate it."""

from __future__ import annotations

import re
from collections.abc import Sequence

from yaku.types import SourceProfile, TargetProfile

# A shell prompt makes the rest of the line a command whatever it contains.
PROMPT = re.compile(r"^\s*[$#>]\s+\S")

COMMAND_NAME = re.compile(
    r"^\s*(?:tar|cd|cat|ls|cp|mv|rm|git|docker|kubectl|aws|terraform"
    r"|curl|wget|echo|find|grep|sed|awk|make|npm|pip|uv|python|ruby|go"
    r"|sudo|export|systemctl|journalctl)\b"
)

# A command name alone is not enough. Documentation says things like
# "tar creates and manipulates archives", which is prose, not a command.
ARGUMENT = re.compile(
    r"(?:^|\s)(?:[-@]\S"  # -c, --create, @archive
    r"|\S+=\S*"  # key=value
    r"|\S*/\S+"  # path/to
    r"|\S+\.\w{1,5}(?=\s|$)"  # archive.tar
    r"|[|(){}])"
)

SYMBOL = re.compile(r"[|=\[\]{}<>/\\]")
SYMBOL_DENSITY = 0.12


def is_passthrough(body: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(p.search(body) for p in patterns)


def looks_like_command(body: str) -> bool:
    if PROMPT.match(body):
        return True
    # A trailing backslash continues a shell command onto the next line.
    if body.rstrip().endswith("\\"):
        return True

    name = COMMAND_NAME.match(body)
    if name is not None and ARGUMENT.search(body[name.end() :]):
        return True

    if body.count("|") >= 2 or body.count("=") >= 2:
        return True

    return len(SYMBOL.findall(body)) / max(len(body), 1) > SYMBOL_DENSITY


def is_translatable(body: str, source: SourceProfile, target: TargetProfile) -> bool:
    if not body.strip():
        return False

    if len(source.letter.findall(body)) / max(len(body), 1) < source.min_alpha_ratio:
        return False

    if len(source.word.findall(body)) < source.min_words:
        return False

    return target.already_translated.search(body[:200]) is None
