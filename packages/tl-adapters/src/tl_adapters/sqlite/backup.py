"""Online snapshot of a SQLite ledger with SQLite's backup API (brief 24.3, dev database layer).

A snapshot is a single self-contained file (rollback journal mode, no ``-wal`` or ``-shm``
sidecar) that can be copied away and opened as a ledger. Taking one does not block writers: the
backup API reads a consistent view while the ledger keeps accepting events. The snapshot is the
database layer only; the ledger archive (``tl archive seal``) is the database-independent layer.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class BackupError(Exception):
    """A snapshot could not be taken; nothing was left at the destination."""


@dataclass(frozen=True)
class BackupResult:
    source: Path
    dest: Path
    bytes: int  # size of the snapshot file
    sha256: str  # hex SHA-256 of the snapshot file
    head_seq: int  # highest events.seq in the snapshot (0 when the events table is empty or absent)
    seconds: float  # wall time of the whole call


def _head_seq(conn: sqlite3.Connection) -> int:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events'"
    ).fetchone()
    if table is None:
        return 0
    row = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
    return int(row[0])


def _copy_into(src: Path, tmp: Path) -> int:
    """Copy ``src`` into the empty file ``tmp``; return the snapshot's head seq."""
    reader = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    writer: sqlite3.Connection | None = None
    try:
        writer = sqlite3.connect(tmp)
        reader.backup(writer)
        check = writer.execute("PRAGMA integrity_check").fetchone()
        if check is None or str(check[0]) != "ok":
            raise BackupError("the snapshot failed SQLite's integrity check")
        writer.execute("PRAGMA journal_mode=DELETE").fetchone()
        return _head_seq(writer)
    finally:
        if writer is not None:
            writer.close()
        reader.close()


def backup_database(source: str | Path, dest: str | Path) -> BackupResult:
    """Copy the ledger at ``source`` to a new file ``dest`` with the online backup API."""
    started = time.perf_counter()
    src = Path(source)
    dst = Path(dest)
    if not src.is_file():
        raise BackupError(f"source database not found: {src}")
    if os.path.lexists(dst):
        raise BackupError(f"destination exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.tmp-")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        try:
            head_seq = _copy_into(src, tmp)
        except sqlite3.Error as error:
            raise BackupError(f"could not snapshot {src}: {error}") from error

        digest = hashlib.sha256()
        with open(tmp, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
            os.fsync(handle.fileno())
        size = tmp.stat().st_size
        os.chmod(tmp, 0o444)
        try:
            os.link(tmp, dst)
        except FileExistsError as error:
            raise BackupError(f"destination exists: {dst}") from error
        except OSError as error:
            raise BackupError(
                f"filesystem does not support hard links; choose another destination ({error})"
            ) from error
    finally:
        tmp.unlink(missing_ok=True)

    return BackupResult(
        source=src,
        dest=dst,
        bytes=size,
        sha256=digest.hexdigest(),
        head_seq=head_seq,
        seconds=time.perf_counter() - started,
    )
