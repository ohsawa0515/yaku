import re

import pytest

from yaku.types import SourceProfile, TargetProfile


@pytest.fixture
def english() -> SourceProfile:
    return SourceProfile(
        lang="en",
        letter=re.compile(r"[A-Za-z]"),
        word=re.compile(r"[A-Za-z]{2,}"),
        min_alpha_ratio=0.45,
        min_words=3,
        sentence_end=re.compile(r"[.:;!?]\s*$"),
        sentence_split=re.compile(
            r"(?<![A-Z]\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\betc\.)"
            r"(?<=[.!?])\s{1,3}(?=[A-Z(])"
        ),
        max_segment_chars=220,
    )


@pytest.fixture
def japanese() -> TargetProfile:
    return TargetProfile(
        lang="ja",
        model_name="fugumt-en-ja",
        min_ratio=0.35,
        max_ratio=2.5,
        # ひらがな 3040-309F・カタカナ 30A0-30FF・CJK 統合漢字 4E00-9FFF
        already_translated=re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]"),
        quote_chars="\"'`",
        placeholder_fmt="T%d",
        placeholder_pattern=re.compile(r"\bT(\d{1,3})\b", re.IGNORECASE),
    )
