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
        "A variable named \"unknown\" was assigned on the command line, but the root",
        "module does not declare a variable of that name. To use this value, add a",
        "\"variable\" block to the configuration.",
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
        "  on main.tf line 15, in resource \"local_file\" \"a\":",
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
