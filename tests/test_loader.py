import re

import pytest

from yaku.loader import (
    RuleError,
    load_mask_rules,
    load_passthrough,
    load_source,
    load_target,
)


def write(tmp_path, relative, body):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_rules_are_sorted_by_order_not_by_file(tmp_path):
    write(tmp_path, "syntax/b.toml", "[[rule]]\nname='LATE'\norder=90\npattern='b'\n")
    write(tmp_path, "syntax/a.toml", "[[rule]]\nname='EARLY'\norder=10\npattern='a'\n")
    names = [r.name for r in load_mask_rules([tmp_path])]
    assert names == ["EARLY", "LATE"]


def test_a_later_directory_replaces_a_rule_by_name(tmp_path):
    base = tmp_path / "base"
    over = tmp_path / "over"
    write(base, "syntax/x.toml", "[[rule]]\nname='FLAG'\norder=10\npattern='a'\n")
    write(over, "syntax/x.toml", "[[rule]]\nname='FLAG'\norder=10\npattern='z'\n")
    rules = load_mask_rules([base, over])
    assert len(rules) == 1
    assert rules[0].pattern.pattern == "z"


def test_duplicate_orders_are_rejected(tmp_path):
    write(
        tmp_path,
        "syntax/x.toml",
        "[[rule]]\nname='A'\norder=10\npattern='a'\n"
        "[[rule]]\nname='B'\norder=10\npattern='b'\n",
    )
    with pytest.raises(RuleError, match="duplicate order 10"):
        load_mask_rules([tmp_path])


def test_a_bad_pattern_names_the_rule(tmp_path):
    write(tmp_path, "syntax/x.toml", "[[rule]]\nname='BAD'\norder=10\npattern='([a'\n")
    with pytest.raises(RuleError, match="BAD"):
        load_mask_rules([tmp_path])


def test_a_missing_key_names_the_file(tmp_path):
    write(tmp_path, "syntax/x.toml", "[[rule]]\nname='NOORDER'\npattern='a'\n")
    with pytest.raises(RuleError, match="missing key"):
        load_mask_rules([tmp_path])


def test_a_missing_profile_is_reported(tmp_path):
    with pytest.raises(RuleError, match="no target profile"):
        load_target("xx", [tmp_path])


def test_a_later_directory_overrides_one_profile_value(tmp_path):
    base = tmp_path / "base"
    over = tmp_path / "over"
    write(
        base,
        "target/ja.toml",
        'lang="ja"\nmodel_name="m"\nmin_ratio=0.35\nmax_ratio=2.5\n'
        "already_translated='a'\nquote_chars=\"'\"\n"
        "placeholder_fmt=\"T%d\"\nplaceholder_pattern='T(\\d+)'\n",
    )
    write(over, "target/ja.toml", "min_ratio=0.30\n")
    profile = load_target("ja", [base, over])
    assert profile.min_ratio == 0.30
    assert profile.max_ratio == 2.5


def test_passthrough_patterns_are_compiled(tmp_path):
    write(tmp_path, "syntax/x.toml", "[[passthrough]]\nname='blank'\npattern='^$'\n")
    patterns = load_passthrough([tmp_path])
    assert [p.pattern for p in patterns] == ["^$"]
