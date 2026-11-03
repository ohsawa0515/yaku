from yaku.text import split_indent, split_sentences, strip_ansi


def test_strip_ansi_removes_colour_codes():
    assert strip_ansi("\x1b[31mError\x1b[0m") == "Error"


def test_strip_ansi_leaves_plain_text_alone():
    assert strip_ansi("no escapes here") == "no escapes here"


def test_split_indent_separates_surrounding_whitespace():
    assert split_indent("    body text   ") == ("    ", "body text", "   ")


def test_split_indent_handles_a_blank_line():
    assert split_indent("   ") == ("   ", "", "")


def test_split_sentences_breaks_at_sentence_boundaries(english):
    text = "Create a new archive. The long option is --create."
    assert split_sentences(text, english) == [
        "Create a new archive.",
        "The long option is --create.",
    ]


def test_split_sentences_keeps_abbreviations_intact(english):
    text = "See i.e. Section 2. Then stop."
    assert split_sentences(text, english) == ["See i.e. Section 2.", "Then stop."]


def test_split_sentences_keeps_initials_intact(english):
    text = "Compare A. B. Smith with others. Next."
    assert split_sentences(text, english) == [
        "Compare A. B. Smith with others.",
        "Next.",
    ]


def test_split_sentences_cuts_at_a_comma_when_too_long(english):
    text = "a" * 200 + ", " + "b" * 100
    assert split_sentences(text, english) == ["a" * 200 + ",", "b" * 100]


def test_split_sentences_never_returns_an_empty_list(english):
    assert split_sentences("", english) == [""]


def test_long_lead_in_is_split_off(english):
    text = "Keyboard-interactive authentication works as follows: The server sends a prompt."
    assert split_sentences(text, english) == [
        "Keyboard-interactive authentication works as follows:",
        "The server sends a prompt.",
    ]


def test_short_label_stays_with_its_value(english):
    for text in [
        "Plan: 4 to add, 0 to change, 0 to destroy.",
        "Error: Invalid value for variable",
        "Recommended: Less than 432000 seconds.",
    ]:
        assert split_sentences(text, english) == [text]


def test_colon_without_space_is_not_a_split_point(english):
    text = "This was checked by the validation rule at main.tf:8,3-13."
    assert split_sentences(text, english) == [text]


def test_semicolon_between_clauses_is_split(english):
    text = "This variable only affects clones and fetches; it is not yet used for pushes."
    assert split_sentences(text, english) == [
        "This variable only affects clones and fetches;",
        "it is not yet used for pushes.",
    ]


def test_semicolon_list_is_not_split(english):
    text = (
        "The escape character followed by a dot closes the connection; followed by "
        "control-Z suspends it; and followed by itself sends the escape character once."
    )
    assert split_sentences(text, english) == [text]


def test_semicolons_in_code_are_not_split(english):
    for text in ["do_one(); do_two(); do_three()", "; Don't trust file modes"]:
        assert split_sentences(text, english) == [text]


def test_colon_still_splits_inside_a_semicolon_list(english):
    text = "It works in three steps as follows: read the file; parse it; and print it."
    assert split_sentences(text, english) == [
        "It works in three steps as follows:",
        "read the file; parse it; and print it.",
    ]


def test_split_gutter_takes_the_frame_only():
    from yaku.text import split_gutter

    assert split_gutter("│ Error: x") == ("│ ", "Error: x")
    assert split_gutter("│   15:   content") == ("│ ", "  15:   content")
    assert split_gutter("plain line") == ("", "plain line")


def test_an_indented_rule_is_not_a_frame():
    from yaku.text import split_gutter

    assert split_gutter('    │ var.env is "qa"') == ("", '    │ var.env is "qa"')


def test_semicolon_before_or_is_split(english):
    text = "Set it to skipping to converge faster; or set it to noop to send nothing."
    assert split_sentences(text, english) == [
        "Set it to skipping to converge faster;",
        "or set it to noop to send nothing.",
    ]


def test_sentence_starting_lowercase_is_split(english):
    text = "It manages keys for T2. ssh-keygen can create keys for protocol version 2."
    assert split_sentences(text, english) == [
        "It manages keys for T2.",
        "ssh-keygen can create keys for protocol version 2.",
    ]


def test_acronym_ends_a_sentence(english):
    text = "Entries end with NUL instead of LF. If no format is given, it is implied."
    assert len(split_sentences(text, english)) == 2


def test_abbreviation_before_lowercase_is_not_split(english):
    for text in [
        "Use a tool, e.g. tar or cpio, for this.",
        "Names, sizes, etc. are listed below.",
        "See the manual, cf. section two.",
    ]:
        assert split_sentences(text, english) == [text]


def test_list_numbers_and_ellipses_do_not_end_a_lowercase_sentence(english):
    for text in [
        "1. have a wonderful idea",
        "3. by listing files as arguments to the commit command",
        "ssh-keygen -L file ... ssh-keygen -A",
        "the shell and pshell commands (! and #)",
    ]:
        assert split_sentences(text, english) == [text], text


def test_split_gutter_takes_a_log_timestamp_and_the_frame():
    from yaku.text import split_gutter

    assert split_gutter("13:17:22  │ Error: x") == ("13:17:22  │ ", "Error: x")
    assert split_gutter("13:17:22  aws_s3_bucket.a: Creating...") == (
        "13:17:22  ",
        "aws_s3_bucket.a: Creating...",
    )
    assert split_gutter("2026-02-12T10:49:20.591-0600 [ERROR] vertex") == (
        "2026-02-12T10:49:20.591-0600 ",
        "[ERROR] vertex",
    )


def test_a_number_that_is_not_a_time_is_not_a_prefix():
    from yaku.text import split_gutter

    assert split_gutter("15:   content = x") == ("", "15:   content = x")


def test_osc_hyperlink_is_removed_with_its_payload():
    from yaku.text import strip_ansi

    link = "\x1b]8;;https://example.com\x1b\\docs\x1b]8;;\x1b\\"
    assert strip_ansi(link) == "docs"
    assert strip_ansi("\x1b]8;;https://example.com\x07docs\x1b]8;;\x07") == "docs"


def test_overstrike_bold_and_underline_are_removed():
    from yaku.text import strip_overstrike

    assert strip_overstrike("N\bNA\bAM\bME\bE") == "NAME"
    assert strip_overstrike("_\bb_\bu_\bn_\bd") == "bund"


def test_overstrike_matches_col_b_on_man_output():
    import shutil
    import subprocess

    import pytest

    from yaku.text import strip_overstrike

    if shutil.which("col") is None:
        pytest.skip("col not available")
    raw = "N\bNA\bAM\bME\bE\n     t\bta\bar\br \x5f\x08b\x5f\x08u\n"
    expected = subprocess.run(["col", "-bx"], input=raw, capture_output=True, text=True).stdout
    assert strip_overstrike(raw).split() == expected.split()


def test_overstrike_consecutive_backspaces_overwrite_by_column():
    from yaku.text import strip_overstrike

    assert strip_overstrike("AB\b\bCD") == "CD"


def test_overstrike_wide_character_covers_two_columns():
    from yaku.text import strip_overstrike

    assert strip_overstrike("__\b\b字") == "字"
    assert strip_overstrike("字\b\b__") == "__"


def test_overstrike_trailing_backspace_deletes_nothing():
    from yaku.text import strip_overstrike

    assert strip_overstrike("abc\b") == "abc"
    assert strip_overstrike("abc\b\n\bdef") == "abc\ndef"


def test_overstrike_overwriting_half_a_wide_glyph_clears_it():
    from yaku.text import strip_overstrike

    assert strip_overstrike("字\bA") == " A"
    assert strip_overstrike("字\b\bA") == "A "


def test_overstrike_ignores_escape_sequences_when_counting_columns():
    from yaku.text import strip_ansi, strip_overstrike

    out = strip_overstrike("\x1b[31m_\x1b[0m\bX")
    assert strip_ansi(out) == "X"
    assert out == "\x1b[31mX\x1b[0m"


def test_overstrike_keeps_combining_marks_after_wide_glyphs():
    from yaku.text import strip_overstrike

    kana = "が"
    assert strip_overstrike(kana + "\nN\bN") == kana + "\nN"
    assert strip_overstrike(kana + "\bX") == " X"
    assert strip_overstrike("x́\bx") == "x"


def test_overstrike_zero_width_marks_do_not_take_a_column():
    from yaku.text import strip_overstrike

    for mark in ("\u200b", "\ufe0f", "\u20dd"):
        assert strip_overstrike(f"x{mark}\bx") == "x"


def test_overstrike_final_escape_stays_last():
    from yaku.text import strip_ansi, strip_overstrike

    # Colour is switched on after the reset, so it must still be on at the end.
    out = strip_overstrike("ab\x1b[0m\b\b\x1b[31mX")
    assert strip_ansi(out) == "Xb"
    assert out.endswith("\x1b[31m")
    # A reset written last must stay last.
    assert strip_overstrike("\x1b[31mab\x1b[0m\b\bX").endswith("\x1b[0m")
