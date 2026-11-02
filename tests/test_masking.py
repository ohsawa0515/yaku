import re

import pytest

from yaku.masking import Masker
from yaku.types import MaskRule


def rule(name: str, pattern: str, order: int, enabled: bool = True) -> MaskRule:
    return MaskRule(
        name=name, pattern=re.compile(pattern), order=order, enabled=enabled
    )


@pytest.fixture
def masker(japanese):
    rules = [
        rule("BRACKET", r"\[[^\[\]\n]{4,300}\]", 10),
        rule("FLAG", r"(?<![\w\-])--?[a-zA-Z][\w\-]*", 20),
        rule("QUOTED", r"[\"'`][^\"'`\n]{1,60}[\"'`]", 30),
        rule("OFF", r"never-matched", 40, enabled=False),
    ]
    return Masker(rules=rules, target=japanese)


def test_mask_replaces_and_records_values(masker):
    masked, values = masker.mask("use --create with 'origin/main'")
    assert masked == "use T1 with T2"
    assert values == ["--create", "'origin/main'"]


def test_mask_and_unmask_round_trip(masker):
    original = "use --create with 'origin/main'"
    masked, values = masker.mask(original)
    assert masker.unmask(masked, values) == original


def test_disabled_rules_are_skipped(masker):
    masked, values = masker.mask("never-matched stays")
    assert masked == "never-matched stays"
    assert values == []


def test_rules_run_in_order_not_in_list_order(japanese):
    # LATE is listed first but has the higher order, so EARLY consumes the text.
    rules = [
        rule("LATE", r"world", 90),
        rule("EARLY", r"hello world", 10),
    ]
    masked, values = Masker(rules=rules, target=japanese).mask("hello world")
    assert masked == "T1"
    assert values == ["hello world"]


def test_a_masked_span_is_not_masked_again(japanese):
    rules = [
        rule("BRACKET", r"\[[^\[\]\n]{4,300}\]", 10),
        rule("QUOTED", r"[\"'`][^\"'`\n]{1,60}[\"'`]", 30),
    ]
    masked, values = Masker(rules=rules, target=japanese).mask('[id="STG"."PUBLIC"]')
    assert masked == "T1"
    assert values == ['[id="STG"."PUBLIC"]']


def test_unmask_replaces_in_descending_order(masker):
    values = [f"value{i}" for i in range(1, 13)]
    assert masker.unmask("T1 T11 T12", values) == "value1 value11 value12"


def test_lost_counts_missing_placeholders(masker):
    assert masker.lost("T1 と T3 があります", 3) == 1
    assert masker.lost("T1 T2 T3", 3) == 0


def test_residue_counts_duplicates(masker):
    assert masker.residue("T1 と T1", 2) == 1


def test_residue_counts_lowercased_copies(masker):
    assert masker.residue("T1 と t1", 2) == 1


def test_residue_counts_numbers_never_issued(masker):
    assert masker.residue("T1 と T9", 2) == 1


def test_template_collapses_literal_numbers(masker):
    assert masker.template("pod T1 has 5 restarts") == "pod T1 has # restarts"


def test_template_keeps_placeholder_numbers_distinct(masker):
    assert masker.template("pod T1 restarted") != masker.template("pod T2 restarted")


def test_word_fused_placeholder_counts_as_lost(mask_rules, japanese):
    """A decoder that emits "T1stdout" kept the characters and lost the value."""
    masker = Masker(rules=mask_rules, target=japanese)
    assert masker.lost("T1stdout.t1 アーカイブの内容", 1) == 1


def test_lower_cased_placeholder_counts_as_lost(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    assert masker.lost("t1 が作成されます", 1) == 1


def test_word_fused_placeholder_counts_as_residue(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    assert masker.residue("T1stdout.t1 アーカイブの内容", 1) == 2


def test_intact_placeholder_is_neither_lost_nor_residue(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    assert masker.lost("T1 が作成されます", 1) == 0
    assert masker.residue("T1 が作成されます", 1) == 0


def test_placeholder_between_japanese_characters_survives(mask_rules, japanese):
    """Python treats Japanese characters as word characters, so a word
    boundary around a placeholder would never match in a Japanese result."""
    masker = Masker(rules=mask_rules, target=japanese)
    assert masker.lost("詳細はT1を参照。", 1) == 0
    assert masker.residue("詳細はT1を参照。", 1) == 0


def test_several_placeholders_in_japanese_text_survive(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    assert masker.lost("T1、T2、またはT3モードでは", 3) == 0
