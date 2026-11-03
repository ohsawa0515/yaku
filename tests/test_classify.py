import re

from yaku.classify import is_passthrough, is_translatable, looks_like_command


def test_prompt_line_is_a_command():
    assert looks_like_command("$ tar -cf archive.tar src/")


def test_command_with_arguments_is_a_command():
    assert looks_like_command("tar -cf archive.tar src/")


def test_prose_starting_with_a_command_name_is_not_a_command():
    assert not looks_like_command("tar creates and manipulates archives.")


def test_prose_mentioning_a_command_name_is_not_a_command():
    assert not looks_like_command("git stores every version of every file.")


def test_pipeline_is_a_command():
    assert looks_like_command("cat f | grep x | wc -l")


def test_passthrough_matches_any_pattern():
    patterns = [re.compile(r"^\s*$"), re.compile(r"^#")]
    assert is_passthrough("", patterns)
    assert is_passthrough("# comment", patterns)
    assert not is_passthrough("real content", patterns)


def test_english_prose_is_translatable(english, japanese):
    assert is_translatable("Create a new archive from the given files.", english, japanese)


def test_short_fragment_is_not_translatable(english, japanese):
    assert not is_translatable("archives.", english, japanese)


def test_symbol_heavy_line_is_not_translatable(english, japanese):
    assert not is_translatable("a=1 b=2 c=3 [x] {y}", english, japanese)


def test_line_containing_japanese_is_not_translatable(english, japanese):
    assert not is_translatable("This line has 日本語 in it already", english, japanese)


def test_shell_line_continuation_is_a_command():
    assert looks_like_command("aws ec2 describe-instances \\")


def test_sentence_starting_with_a_manual_reference_is_prose():
    assert not looks_like_command("tar(1) describes the supported archive formats.")


def test_prose_with_a_flag_is_not_a_command():
    assert not looks_like_command("tar supports --create to create an archive.")


def test_command_with_flags_is_still_a_command():
    assert looks_like_command("tar --create --file archive.tar src/")
