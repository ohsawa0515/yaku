import subprocess
from pathlib import Path

import pytest

from yaku.setup import REQUIRED_FILES, SetupError, converter_command, install, is_installed


def fake_converter(produce=REQUIRED_FILES, returncode=0):
    calls = []

    def run(command, env=None, check=False):
        calls.append((command, env))
        output = Path(command[command.index("--output_dir") + 1])
        output.mkdir(parents=True)
        for name in produce:
            (output / name).write_text("x")
        return subprocess.CompletedProcess(command, returncode)

    run.calls = calls
    return run


def quiet(_message):
    pass


def test_command_pins_the_revision_and_copies_the_tokenisers(japanese):
    command = converter_command("uv", japanese, Path("/out"))
    assert command[command.index("--revision") + 1] == japanese.model_revision
    assert command[command.index("--quantization") + 1] == "int8"
    copied = command[command.index("--copy_files") + 1 : command.index("--copy_files") + 3]
    assert copied == ["source.spm", "target.spm"]


def test_command_never_installs_sacremoses(japanese):
    assert not any("sacremoses" in part for part in converter_command("uv", japanese, Path("/o")))


def test_install_converts_into_place(tmp_path, japanese):
    run = fake_converter()
    model_dir = tmp_path / "models" / "fugumt-en-ja"
    assert install(japanese, model_dir, uv="uv", run=run, log=quiet) == model_dir
    assert is_installed(model_dir)
    assert len(run.calls) == 1


def test_installed_model_is_not_converted_again(tmp_path, japanese):
    model_dir = tmp_path / "fugumt-en-ja"
    model_dir.mkdir()
    for name in REQUIRED_FILES:
        (model_dir / name).write_text("x")
    run = fake_converter()
    install(japanese, model_dir, uv="uv", run=run, log=quiet)
    assert run.calls == []


def test_force_replaces_an_existing_model(tmp_path, japanese):
    model_dir = tmp_path / "fugumt-en-ja"
    model_dir.mkdir()
    for name in REQUIRED_FILES:
        (model_dir / name).write_text("old")
    install(japanese, model_dir, force=True, uv="uv", run=fake_converter(), log=quiet)
    assert (model_dir / "model.bin").read_text() == "x"


def test_failed_conversion_leaves_nothing_behind(tmp_path, japanese):
    model_dir = tmp_path / "fugumt-en-ja"
    with pytest.raises(SetupError):
        install(japanese, model_dir, uv="uv", run=fake_converter(returncode=1), log=quiet)
    assert not model_dir.exists()
    assert list(tmp_path.iterdir()) == []


def test_incomplete_conversion_is_rejected(tmp_path, japanese):
    model_dir = tmp_path / "fugumt-en-ja"
    with pytest.raises(SetupError, match="source.spm"):
        install(japanese, model_dir, uv="uv", run=fake_converter(produce=["model.bin", "target.spm"]), log=quiet)
    assert not model_dir.exists()


def test_checkpoint_download_stays_out_of_the_user_cache(tmp_path, japanese):
    run = fake_converter()
    install(japanese, tmp_path / "m", uv="uv", run=run, log=quiet)
    _, env = run.calls[0]
    assert Path(env["HF_HOME"]).is_relative_to(tmp_path)


def test_missing_uv_is_reported(tmp_path, japanese, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(SetupError, match="uv is required"):
        install(japanese, tmp_path / "m", run=fake_converter(), log=quiet)
