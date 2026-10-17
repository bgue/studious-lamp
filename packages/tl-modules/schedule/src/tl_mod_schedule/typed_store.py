"""Writing and clearing the typed rows of a snapshot (the ``sched_*`` tables, ADR-0015).

The rows come from ``tl_xer.typed`` (a checked ``Snapshot``); each table is written with
multi-row ``INSERT ... VALUES`` statements sized to stay under the parameter limits of both
databases (the Postgres driver costs about half a millisecond a statement, so one statement for a
few hundred rows is the difference between seconds and minutes). The SQL is dialect-neutral. A
snapshot's rows are written once, by the build, in the transaction that appends ``Built``; they are
never updated.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import Connection, text
from tl_xer.typed import TABLE_COLUMNS, Snapshot

from tl_mod_schedule.names import TYPED_TABLES

#: Bound parameters per statement: under SQLite's 32 766 and far under Postgres's 65 535.
MAX_PARAMETERS = 12_000


def row_id(snapshot_id: str, seq: int) -> str:
    """``<snapshot id>:<seq>``, the key of a typed row."""
    return f"{snapshot_id}:{seq}"


def _insert(
    conn: Connection, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]
) -> None:
    per_statement = max(1, MAX_PARAMETERS // len(columns))
    head = f"INSERT INTO {table} ({', '.join(columns)}) VALUES "
    for start in range(0, len(rows), per_statement):
        part = rows[start : start + per_statement]
        params: dict[str, Any] = {}
        groups: list[str] = []
        for n, values in enumerate(part):
            names = []
            for c, value in enumerate(values):
                name = f"p{n}_{c}"
                params[name] = value
                names.append(f":{name}")
            groups.append("(" + ", ".join(names) + ")")
        conn.execute(text(head + ", ".join(groups)), params)


def write_snapshot(conn: Connection, scope: str, snapshot_id: str, snapshot: Snapshot) -> None:
    """Insert every typed row of ``snapshot``. The rows of ``snapshot_id`` must not exist yet."""
    for key, table in TYPED_TABLES.items():
        columns = ("row_id", "scope", "snapshot_id", *TABLE_COLUMNS[key])
        rows = [
            (row_id(snapshot_id, cast(int, cells[-1])), scope, snapshot_id, *cells)
            for cells in snapshot.tables[key]
        ]
        _insert(conn, table, columns, rows)


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
