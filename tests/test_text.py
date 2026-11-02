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
    for text in ["Use a tool, e.g. tar or cpio, for this.",
                 "Names, sizes, etc. are listed below.",
                 "See the manual, cf. section two."]:
        assert split_sentences(text, english) == [text]


def test_list_numbers_and_ellipses_do_not_end_a_lowercase_sentence(english):
    for text in ["1. have a wonderful idea",
                 "3. by listing files as arguments to the commit command",
                 "ssh-keygen -L file ... ssh-keygen -A",
                 "the shell and pshell commands (! and #)"]:
        assert split_sentences(text, english) == [text], text
