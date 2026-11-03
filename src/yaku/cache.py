"""A translation cache keyed on the exact masked text.

Masking already folds identifiers into placeholders, so repeated sentences
about different resources share an entry. Literal numbers are deliberately
not folded: the stored value is a translation of one specific sentence, and
serving it for "4 to add" when it was produced for "1 to add" would print
the wrong number. Every failure here is swallowed: a missing cache must
never stop a translation.
"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
from pathlib import Path
from types import TracebackType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entry (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def model_fingerprint(model_dir: Path) -> str:
    """Identify an installed model by location, size and modification time.

    Replacing a model in place changes the file even when its path does not.
    """
    try:
        stat = (model_dir / "model.bin").stat()
    except OSError:
        return str(model_dir)
    return f"{model_dir.resolve()}@{stat.st_size}:{stat.st_mtime_ns}"


class Cache:
    """Key-value store backed by SQLite, or a no-op when it cannot open.

    The namespace covers everything that changes what a translation looks
    like: model, decoding width and the active rule set. A stale entry from a
    different configuration would otherwise be served as if it were current.
    """

    def __init__(self, path: Path | None, namespace: str) -> None:
        self.namespace = namespace
        self._conn: sqlite3.Connection | None = None
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path))
            self._conn.execute(_SCHEMA)
            self._conn.commit()
        except (sqlite3.Error, OSError):
            self._conn = None

    @property
    def enabled(self) -> bool:
        return self._conn is not None

    def _key(self, text: str) -> str:
        raw = f"{self.namespace}\0{text}".encode()
        return hashlib.sha256(raw).hexdigest()[:32]

    def get(self, text: str) -> str | None:
        if self._conn is None:
            return None
        try:
            row = self._conn.execute(
                "SELECT value FROM entry WHERE key = ?", (self._key(text),)
            ).fetchone()
        except sqlite3.Error:
            return None
        return row[0] if row else None

    def put(self, text: str, value: str) -> None:
        if self._conn is None:
            return
        with contextlib.suppress(sqlite3.Error):
            self._conn.execute(
                "INSERT OR REPLACE INTO entry VALUES (?, ?)",
                (self._key(text), value),
            )

    def commit(self) -> None:
        if self._conn is None:
            return
        with contextlib.suppress(sqlite3.Error):
            self._conn.commit()

    def close(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.commit()
            self._conn.close()
        except sqlite3.Error:
            pass
        finally:
            self._conn = None

    def __enter__(self) -> Cache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
