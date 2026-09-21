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
