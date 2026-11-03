"""Fetching and converting a translation model.

The model is not redistributed. It is downloaded from its upstream at a
pinned revision and converted on the user's machine. The converter needs
torch, which yaku itself must not depend on, so the conversion runs in a
throwaway environment created by uv.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from yaku.types import TargetProfile

# sacremoses is deliberately absent: its normalisation disagrees with
# reading the .spm files directly, which is what yaku does at runtime.
CONVERTER_DEPS = ("transformers<6", "torch", "ctranslate2>=4.0", "sentencepiece")

REQUIRED_FILES = ("model.bin", "source.spm", "target.spm")

Runner = Callable[..., subprocess.CompletedProcess]


class SetupError(Exception):
    """The model could not be fetched or converted."""


def is_installed(model_dir: Path) -> bool:
    return all((model_dir / name).is_file() for name in REQUIRED_FILES)


def converter_command(uv: str, target: TargetProfile, output_dir: Path) -> list[str]:
    command = [uv, "run", "--no-project", "--isolated", "--python", "3.12"]
    for dep in CONVERTER_DEPS:
        command += ["--with", dep]
    command += [
        "--",
        "ct2-transformers-converter",
        "--model",
        target.model_repo,
        "--output_dir",
        str(output_dir),
        "--quantization",
        "int8",
        "--copy_files",
        "source.spm",
        "target.spm",
    ]
    if target.model_revision:
        command += ["--revision", target.model_revision]
    return command


def _log(message: str) -> None:
    print(f"yaku: {message}", file=sys.stderr)


def install(
    target: TargetProfile,
    model_dir: Path,
    *,
    force: bool = False,
    uv: str | None = None,
    run: Runner = subprocess.run,
    log: Callable[[str], None] = _log,
) -> Path:
    """Make sure a converted model exists at model_dir and return the path.

    Conversion happens in a temporary directory next to the destination and
    is moved into place only once every required file is present, so a
    failure never leaves a half-written model behind.
    """
    if is_installed(model_dir) and not force:
        log(f"already installed: {model_dir}")
        return model_dir
    if not target.model_repo:
        raise SetupError(f"profile {target.lang!r} names no model_repo to fetch")

    uv = uv or shutil.which("uv")
    if uv is None:
        raise SetupError("uv is required to convert the model: https://docs.astral.sh/uv/")

    model_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=model_dir.parent, prefix=f".{model_dir.name}-") as scratch:
        work = Path(scratch)
        output = work / model_dir.name
        # Keep the ~300 MB PyTorch checkpoint out of the user's Hugging Face
        # cache; it is only needed for the duration of the conversion.
        env = {
            **os.environ,
            "HF_HOME": str(work / "hf"),
            # transformers recommends installing sacremoses, which is exactly
            # what must not be done here; do not let users act on it.
            "PYTHONWARNINGS": "ignore::UserWarning:transformers.models.marian.tokenization_marian",
        }

        log(f"converting {target.model_repo} ({target.model_license or 'see upstream'})")
        log("the first run downloads torch and the checkpoint; this takes a few minutes")
        result = run(converter_command(uv, target, output), env=env, check=False)
        if result.returncode != 0:
            raise SetupError(f"conversion failed with exit status {result.returncode}")

        missing = [name for name in REQUIRED_FILES if not (output / name).is_file()]
        if missing:
            raise SetupError(f"conversion produced no {', '.join(missing)}")

        if model_dir.exists():
            model_dir.rename(work / "previous")
        output.rename(model_dir)
    return model_dir


def main(argv: Sequence[str], load_target: Callable[[str], TargetProfile]) -> int:
    import argparse

    from yaku import paths

    parser = argparse.ArgumentParser(
        prog="yaku setup",
        description="Download and convert the model for a target language.",
    )
    parser.add_argument("--lang", default="ja", help="target language (default: ja)")
    parser.add_argument(
        "--force", action="store_true", help="convert again even if a model is present"
    )
    args = parser.parse_args(argv)

    target = load_target(args.lang)
    try:
        model_dir = install(target, paths.model_dir(target.model_name), force=args.force)
    except SetupError as exc:
        _log(str(exc))
        return 2
    print(model_dir)
    return 0
