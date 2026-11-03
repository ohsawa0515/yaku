import pytest

from yaku.masking import Masker
from yaku.quality import judge


@pytest.fixture
def masker(mask_rules, japanese):
    return Masker(rules=mask_rules, target=japanese)


def test_good_translation_passes(masker, japanese):
    verdict = judge("Create a new archive.", "新しいアーカイブを作成します。", 0, masker, japanese)
    assert verdict.ok


def test_empty_output_fails(masker, japanese):
    verdict = judge("Create a new archive.", "   ", 0, masker, japanese)
    assert not verdict.ok
    assert verdict.reason == "empty output"


def test_lost_placeholder_fails(masker, japanese):
    verdict = judge("T1 will be created", "作成されます", 1, masker, japanese)
    assert not verdict.ok
    assert "placeholder lost" in verdict.reason


def test_duplicated_placeholder_fails(masker, japanese):
    verdict = judge("T1 will be created", "T1 と T1 が作成されます", 1, masker, japanese)
    assert not verdict.ok
    assert "placeholder residue" in verdict.reason


def test_invented_placeholder_fails(masker, japanese):
    verdict = judge("T1 will be created", "T1 と T5 が作成されます", 1, masker, japanese)
    assert not verdict.ok
    assert "placeholder residue" in verdict.reason


def test_too_short_fails(masker, japanese):
    source = "Create a new archive from the given files and directories."
    verdict = judge(source, "作成", 0, masker, japanese)
    assert not verdict.ok
    assert "too short" in verdict.reason


def test_too_long_fails(masker, japanese):
    verdict = judge("tar", "非常に長い訳文がここに続きます。さらに続きます。", 0, masker, japanese)
    assert not verdict.ok
    assert "too long" in verdict.reason


def test_repetition_loop_fails(masker, japanese):
    source = "Create a new archive from the given files."
    verdict = judge(
        source, "アーカイブアーカイブアーカイブアーカイブアーカイブ", 0, masker, japanese
    )
    assert not verdict.ok
    assert verdict.reason == "repetition loop"


def test_ratio_bounds_come_from_the_target_profile(japanese):
    assert japanese.min_ratio == 0.35
    assert japanese.max_ratio == 2.5


def test_invented_placeholder_is_caught_when_none_were_issued(masker, japanese):
    verdict = judge("Create a new archive.", "T1 が作成されます。", 0, masker, japanese)
    assert not verdict.ok


def test_placeholders_are_not_checked_for_uncounted_fragments(masker, japanese):
    verdict = judge("Create a new archive.", "T1 が作成されます。", None, masker, japanese)
    assert verdict.ok


def test_swapped_placeholders_fail(masker, japanese):
    verdict = judge("T1 will replace T2", "T2 が T1 に置き換わります", 2, masker, japanese)
    assert not verdict.ok
    assert "order" in verdict.reason


def test_reordering_after_the_subject_is_ordinary_word_order(masker, japanese):
    verdict = judge(
        "See T1 in T2 for details", "詳細は T2 の T1 を参照してください", 2, masker, japanese
    )
    assert verdict.ok


def test_placeholders_in_source_order_pass(masker, japanese):
    verdict = judge(
        "T1 will replace T2 in the pool", "T1 は T2 を置き換えます", 2, masker, japanese
    )
    assert verdict.ok
