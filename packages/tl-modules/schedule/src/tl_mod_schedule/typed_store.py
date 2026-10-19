"""Writing and clearing the typed rows of a snapshot (the ``sched_*`` tables, ADR-0015).

The rows come from ``tl_xer.typed`` (a checked ``Snapshot``); each table is written by
``tl_adapters.bulk.bulk_insert``, which knows the fast shape on each database (ADR-0015 section 4).
A snapshot's rows are written once, by the build, in the transaction that appends ``Built``; they
are never updated.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import Connection, text
from tl_adapters.bulk import bulk_insert
from tl_xer.typed import COLUMN_KINDS, TABLE_COLUMNS, Snapshot

from tl_mod_schedule.names import TYPED_TABLES

#: The three columns every typed row starts with, all text.
_LEAD_KINDS = "sss"


def row_id(snapshot_id: str, seq: int) -> str:
    """``<snapshot id>:<seq>``, the key of a typed row."""
    return f"{snapshot_id}:{seq}"


def write_snapshot(conn: Connection, scope: str, snapshot_id: str, snapshot: Snapshot) -> None:
    """Insert every typed row of ``snapshot``. The rows of ``snapshot_id`` must not exist yet."""
    for key, table in TYPED_TABLES.items():
        columns = ("row_id", "scope", "snapshot_id", *TABLE_COLUMNS[key])
        rows = [
            (row_id(snapshot_id, cast(int, cells[-1])), scope, snapshot_id, *cells)
            for cells in snapshot.tables[key]
        ]
        bulk_insert(conn, table, columns, _LEAD_KINDS + COLUMN_KINDS[key], rows)


def clear_snapshot(conn: Connection, snapshot_id: str) -> None:
    """Delete every typed row of a snapshot (``reconcile`` writes them again)."""
    for table in TYPED_TABLES.values():
        conn.execute(text(f"DELETE FROM {table} WHERE snapshot_id = :id"), {"id": snapshot_id})


def count_rows(conn: Connection, snapshot_id: str) -> dict[str, int]:
    """Rows per typed table, keyed like ``Snapshot.tables``."""
    return {
        key: int(
            conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE snapshot_id = :id"), {"id": snapshot_id}
            ).scalar_one()
        )
        for key, table in TYPED_TABLES.items()
    }
