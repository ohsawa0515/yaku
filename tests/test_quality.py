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
    verdict = judge(source, "アーカイブアーカイブアーカイブアーカイブアーカイブ", 0, masker, japanese)
    assert not verdict.ok
    assert verdict.reason == "repetition loop"


def test_ratio_bounds_come_from_the_target_profile(japanese):
    assert japanese.min_ratio == 0.35
    assert japanese.max_ratio == 2.5
