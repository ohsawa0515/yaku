import pytest

from yaku.cache import Cache
from yaku.masking import Masker
from yaku.pipeline import Pipeline


class EchoEngine:
    """Returns its input, so tests see exactly what was sent."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def translate(self, texts):
        self.calls.append(list(texts))
        return list(texts)


@pytest.fixture
def make(mask_rules, passthrough, english, japanese):
    def build(join=None):
        return Pipeline(
            engine=EchoEngine(),
            masker=Masker(rules=mask_rules, target=japanese),
            source=english,
            target=japanese,
            passthrough=passthrough,
            cache=Cache(None, "test"),
            join=join,
        )

    return build


def bodies(lines):
    return [line.body for line in lines if line.translatable]


def test_manual_page_is_joined(make):
    raw = [
        "     tar creates and manipulates streaming archive files.  This",
        "     implementation can extract from tar, pax, cpio, zip, jar, ar, xar,",
        "     rpm, 7-zip, and ISO 9660 cdrom images and can create tar, pax,",
        "     cpio, ar, zip, 7-zip, and shar archives.",
    ]
    pipeline = make()
    lines = pipeline.prepare(raw)
    assert pipeline.stats.joined
    assert len(bodies(lines)) == 1


def test_record_per_line_output_is_not_joined(make):
    raw = [
        "Terraform will perform the following actions:",
        "  # local_file.config will be created",
        "Plan: 4 to add, 0 to change, 0 to destroy.",
        "Changes to Outputs:",
    ]
    pipeline = make()
    pipeline.prepare(raw)
    assert not pipeline.stats.joined


def test_wrapped_paragraph_is_joined_inside_unjoined_input(make):
    raw = [
        "Error: Value for undeclared variable",
        "",
        'A variable named "unknown" was assigned on the command line, but the root',
        "module does not declare a variable of that name. To use this value, add a",
        '"variable" block to the configuration.',
    ]
    pipeline = make(join=False)
    lines = pipeline.prepare(raw)
    assert bodies(lines)[-1].startswith("A variable named")
    assert bodies(lines)[-1].endswith("block to the configuration.")


def test_short_unfinished_lines_stay_separate(make):
    raw = [
        "Waiting for the database to accept connections on the primary node",
        "Starting the application server",
        "Listening on all interfaces for incoming requests",
    ]
    pipeline = make(join=False)
    assert len(bodies(pipeline.prepare(raw))) == 3


def test_a_capitalised_line_starts_a_new_record(make):
    raw = [
        "Terraform used the selected providers to generate the following execution",
        "Resource actions are indicated with the following symbols:",
    ]
    pipeline = make(join=False)
    assert len(bodies(pipeline.prepare(raw))) == 2


def test_terraform_source_excerpt_is_not_translated(make):
    raw = [
        "Error: Reference to undeclared local value",
        "",
        '  on main.tf line 15, in resource "local_file" "a":',
        "  15:   content  = local.missing_value",
    ]
    pipeline = make(join=True)
    lines = pipeline.prepare(raw)
    excerpt = [line for line in lines if "15:" in line.body]
    assert excerpt and not excerpt[0].translatable


def test_cache_answers_a_repeated_segment(make, tmp_path):
    pipeline = make(join=False)
    pipeline.cache = Cache(tmp_path / "c.sqlite3", "test")
    raw = ["The archive was created successfully on disk."] * 3
    lines = pipeline.prepare(raw)
    pipeline.run(lines)
    assert pipeline.engine.calls == [["The archive was created successfully on disk."] * 3]

    second = make(join=False)
    second.cache = pipeline.cache
    second.run(second.prepare(raw))
    assert second.engine.calls == []
    assert second.stats.cached == 3


def test_identifiers_survive_the_round_trip(make):
    pipeline = make(join=False)
    raw = ["The resource aws_instance.web_server_01 will be created with --force."]
    lines = pipeline.prepare(raw)
    pipeline.run(lines)
    assert pipeline.render(lines[0]) == raw


def test_cache_never_serves_a_different_number(make, tmp_path):
    """A cached translation is of one exact sentence. Reusing it for a
    sentence that differs only in a number would print the wrong number."""
    cache = Cache(tmp_path / "c.sqlite3", "test")
    first = make(join=False)
    first.cache = cache
    first.run(first.prepare(["Plan: 1 to add, 0 to change, 0 to destroy."]))

    second = make(join=False)
    second.cache = cache
    lines = second.prepare(["Plan: 4 to add, 0 to change, 0 to destroy."])
    second.run(lines)
    assert second.engine.calls, "must translate, not reuse the cached entry"
    assert second.render(lines[0]) == ["Plan: 4 to add, 0 to change, 0 to destroy."]


def test_framed_diagnostic_is_translated_inside_the_frame(make):
    raw = [
        "\x1b[31m╷\x1b[0m",
        "\x1b[31m│\x1b[0m \x1b[1mError: Reference to undeclared local value\x1b[0m",
        '\x1b[31m│\x1b[0m   on main.tf line 15, in resource "local_file" "a":',
        "\x1b[31m│\x1b[0m   15:   content  = local.missing_value",
        '\x1b[31m│\x1b[0m     \x1b[90m│\x1b[0m var.env is "qa"',
        '\x1b[31m│\x1b[0m A local value with the name "missing_value" has not been declared.',
        "\x1b[31m╵\x1b[0m",
    ]
    pipeline = make(join=False)
    lines = pipeline.prepare(raw)
    translated = [line.body for line in lines if line.translatable]
    assert "Error: Reference to undeclared local value" in translated
    assert any(body.startswith("A local value with the name") for body in translated)
    assert not any("15:" in body or "var.env is" in body for body in translated)
    pipeline.run(lines)
    last = [line for line in lines if line.translatable][-1]
    assert pipeline.render(last)[0].startswith("│ ")


def test_log_records_are_never_joined(make):
    raw = [
        "2023-02-08 08:51:32,665 - MainThread - awscli.clidriver - DEBUG - Exception caught in main()",
        "2024-06-12 00:57:03,451 - MainThread - botocore.credentials - INFO - Found credentials in shared credentials file",
        "2024-06-12 00:57:03,452 - MainThread - botocore.credentials - INFO - Looking for credentials in the environment",
    ]
    lines = make(join=True).prepare(raw)
    assert not lines[0].translatable
    assert [len(line.raws) for line in lines] == [1, 1, 1]


def test_traceback_body_is_not_translated(make):
    raw = [
        "Traceback (most recent call last):",
        '  File "/usr/lib/python3/awscli/clidriver.py", line 460, in main',
        "    return command_table[parsed_args.command](remaining, parsed_args)",
        "    raise error_class(parsed_response, operation_name)",
        "botocore.errorfactory.InvalidRequestException: An error occurred when calling the operation.",
    ]
    lines = make(join=False).prepare(raw)
    translated = [line.body for line in lines if line.translatable]
    assert translated == [raw[-1]]


def test_spacing_inside_quotes_is_preserved(make):
    lines = make().prepare(['Set the message to "hello  world" before starting.'])
    line = next(line for line in lines if line.translatable)
    assert line.values == ['"hello  world"']


def test_line_that_is_already_translated_is_not_absorbed(make):
    raw = [
        "The configuration file is read when the program starts and",
        "This line has 日本語 in it already",
    ]
    lines = make(join=True).prepare(raw)
    assert [line.translatable for line in lines] == [True, False]


def test_log_records_without_timestamps_are_not_joined(make):
    raw = [
        "[INFO] Starting the service using the default configuration",
        "[INFO] Waiting for the service to accept incoming connections",
    ]
    lines = make(join=True).prepare(raw)
    assert len(bodies(lines)) == 2


def test_adjacent_placeholders_in_segments_stay_apart():
    from yaku.pipeline import _join_segments

    assert _join_segments(["作成 T1", "T2 を削除"]) == "作成 T1 T2 を削除"
    assert _join_segments(["作成します。", "削除します。"]) == "作成します。削除します。"


def test_changing_timestamps_start_new_records(make):
    raw = [
        "13:17:22 Waiting for the database to accept connections",
        "13:17:23 Connection was refused by the server",
    ]
    lines = make(join=True).prepare(raw)
    assert len(bodies(lines)) == 2


def test_width_breaks_text_without_punctuation(make):
    pipeline = make()
    pipeline.width = 20
    out = pipeline._wrap("あ" * 80 + "。", "")
    assert max(len(line) for line in out) <= 21
    assert all(not line.startswith("。") for line in out)


def test_width_does_not_cut_inside_an_identifier(make):
    pipeline = make()
    pipeline.width = 20
    out = pipeline._wrap("作成: " + "a" * 30 + " を確認", "")
    assert any("a" * 30 in line for line in out)
