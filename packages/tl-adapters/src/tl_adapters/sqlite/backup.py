"""Online snapshot of a SQLite ledger with SQLite's backup API (brief 24.3, dev database layer).

STUB (P0-I7-T02): ``backup_database`` raises ``NotImplementedError``. Remove this paragraph when
done.

A snapshot is a single self-contained file (rollback journal mode, no ``-wal`` or ``-shm``
sidecar) that can be copied away and opened as a ledger. Taking one does not block writers: the
backup API reads a consistent view while the ledger keeps accepting events. The snapshot is the
database layer only; the ledger archive (``tl archive seal``) is the database-independent layer.
"""

from __future__ import annotations

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


def backup_database(source: str | Path, dest: str | Path) -> BackupResult:
    """Copy the ledger at ``source`` to a new file ``dest`` with the online backup API."""
    raise NotImplementedError
