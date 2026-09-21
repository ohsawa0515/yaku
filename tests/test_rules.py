import re

from yaku.classify import is_passthrough
from yaku.masking import Masker


def order_of(rules):
    return {rule.name: rule.order for rule in rules}


def test_bracket_is_evaluated_first(mask_rules):
    orders = order_of(mask_rules)
    assert orders["BRACKET"] == min(orders.values())


def test_cfgkey_is_evaluated_before_ident(mask_rules):
    orders = order_of(mask_rules)
    assert orders["CFGKEY"] < orders["IDENT"]


def test_compare_is_enabled(mask_rules):
    assert next(r for r in mask_rules if r.name == "COMPARE").enabled


def test_version_is_disabled(mask_rules):
    assert not next(r for r in mask_rules if r.name == "VERSION").enabled


def test_bracket_contents_are_masked_as_one_value(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask('aws_instance.web will be created [id=A|B|"PUBLIC"]')
    assert '[id=A|B|"PUBLIC"]' in values
    assert "PUBLIC" not in masked


def test_config_key_survives_as_one_value(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask("zstd:frame-per-file is supported.")
    assert values == ["zstd:frame-per-file"]


def test_comparison_operator_is_masked(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    masked, values = masker.mask("The program exits >0 if an error occurs.")
    assert ">0" in values


def test_shipped_rules_round_trip(mask_rules, japanese):
    masker = Masker(rules=mask_rules, target=japanese)
    for line in [
        "Use -cftuvSUX with --format ustar to write archives.",
        "Checkout 'origin/main' before you continue.",
        "See tar(1) and environ(7) for details.",
    ]:
        masked, values = masker.mask(line)
        assert masker.unmask(masked, values) == line


def test_progress_rule_ignores_prose(passthrough):
    assert not is_passthrough(
        "Note: Reading the archive is slower than writing it.", passthrough
    )
    assert not is_passthrough(
        "Warning: Creating a sparse file may fail on some systems.", passthrough
    )


def test_progress_rule_matches_a_resource_address(passthrough):
    assert is_passthrough("aws_instance.web: Refreshing state...", passthrough)
    assert is_passthrough("module.vpc.aws_subnet.private: Creating...", passthrough)
