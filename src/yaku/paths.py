"""Where models, cache and user configuration live.

Every filesystem location is resolved here. Spreading this logic across
modules is what makes a tool behave differently in a checkout and once
installed, with no single place to look.
"""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

APP = "yaku"


def _base(env: str, fallback: str) -> Path:
    raw = os.environ.get(env)
    return Path(raw).expanduser() if raw else Path.home() / fallback


def data_dir() -> Path:
    return _base("XDG_DATA_HOME", ".local/share") / APP


def cache_dir() -> Path:
    return _base("XDG_CACHE_HOME", ".cache") / APP


def config_dir() -> Path:
    return _base("XDG_CONFIG_HOME", ".config") / APP


def models_dir() -> Path:
    """Model root.

    A models directory in the working directory wins over the user data
    directory, so a checkout can be tested without touching installed state.
    """
    env = os.environ.get("YAKU_MODELS_DIR")
    if env:
        return Path(env).expanduser()
    local = Path.cwd() / "models"
    if local.is_dir():
        return local
    return data_dir() / "models"


def model_dir(name: str) -> Path:
    return models_dir() / name


def cache_path() -> Path:
    env = os.environ.get("YAKU_CACHE_DIR")
    base = Path(env).expanduser() if env else cache_dir()
    return base / "cache.sqlite3"


def bundled_rules_dir() -> Path:
    """Rules shipped inside the wheel.

    Both uv and pipx install unpacked, so a real filesystem path exists.
    """
    return Path(str(files(APP) / "rules"))


def rule_dirs(override: Path | None = None) -> list[Path]:
    """Rule directories, lowest precedence first.

    Bundled rules are always read. Later directories add to them or replace
    individual rules by name, which keeps the shipped set read-only.
    """
    dirs = [bundled_rules_dir()]
    env = os.environ.get("YAKU_RULES_DIR")
    user = Path(env).expanduser() if env else config_dir() / "rules"
    if user.is_dir():
        dirs.append(user)
    if override is not None:
        dirs.append(override)
    return dirs
