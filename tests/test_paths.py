from pathlib import Path

from yaku import paths


def test_models_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("YAKU_MODELS_DIR", str(tmp_path))
    assert paths.models_dir() == tmp_path


def test_models_default_to_the_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("YAKU_MODELS_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert paths.models_dir() == tmp_path / "share" / "yaku" / "models"


def test_a_models_directory_in_the_working_directory_is_ignored(tmp_path, monkeypatch):
    """A repository the user is browsing must not be able to supply a model."""
    monkeypatch.delenv("YAKU_MODELS_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    (tmp_path / "models" / "fugumt-en-ja").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert paths.models_dir() == tmp_path / "share" / "yaku" / "models"


def test_cache_honours_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("YAKU_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert paths.cache_path() == tmp_path / "yaku" / "cache.sqlite3"


def test_bundled_rules_have_lowest_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("YAKU_RULES_DIR", str(tmp_path))
    dirs = paths.rule_dirs(override=Path("/tmp/explicit"))
    assert dirs[0] == paths.bundled_rules_dir()
    assert dirs[-1] == Path("/tmp/explicit")
