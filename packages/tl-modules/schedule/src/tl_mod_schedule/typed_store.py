"""Writing and clearing the typed rows of a snapshot (the ``sched_*`` tables, ADR-0015).

The rows come from ``tl_xer.typed`` (a checked ``Snapshot``); each table is written with one
compiled ``INSERT`` executed with many sets of parameters (``executemany``) on SQLite, and with the
rows as one JSON text on Postgres (see ``_insert``). A snapshot's rows are written once, by the
build, in the transaction that appends ``Built``; they are never updated.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import Connection, column, insert, text
from sqlalchemy import table as sql_table
from tl_xer.typed import COLUMN_KINDS, TABLE_COLUMNS, Snapshot

from tl_mod_schedule.names import TYPED_TABLES

#: Rows sent to the driver in one call on SQLite (``executemany``), and in one statement on
#: Postgres (one JSON text).
CHUNK_ROWS = 5000
POSTGRES_CHUNK_ROWS = 20_000

#: How a column of each kind (``tl_xer.typed.COLUMN_KINDS``) is read out of the JSON on Postgres.
_CASTS = {
    "s": "{}",
    "S": "{}",
    "f": "({})::float8",
    "F": "({})::float8",
    "b": "({})::boolean",
    "i": "({})::integer",
}
#: The three columns every typed row starts with, all text.
_LEAD_KINDS = "sss"


def row_id(snapshot_id: str, seq: int) -> str:
    """``<snapshot id>:<seq>``, the key of a typed row."""
    return f"{snapshot_id}:{seq}"


def _insert(
    conn: Connection,
    name: str,
    columns: Sequence[str],
    kinds: str,
    rows: Sequence[Sequence[Any]],
) -> None:
    """Insert ``rows``; the cost is the database's, not the library's.

    Building a ``text()`` statement with thousands of bound parameters cost more than writing the
    rows (ADR-0015 section 4: 70 per cent of a settle at the limits), and the pure-Python Postgres
    driver sends one round trip per row of an ``executemany`` (535 s at the limits). So:

    * **Postgres**: one statement per chunk, one bound parameter: the rows as JSON text, read by
      ``json_array_elements`` and cast column by column. The text is bound, never spliced into the
      SQL; the table and column names are constants of this module.
    * **SQLite**: one compiled ``INSERT`` executed with a list of parameter sets (``executemany``
      is a loop inside the C driver).
    """
    if not rows:
        return
    if conn.dialect.name == "postgresql":
        select = ", ".join(
            _CASTS[kind].format(f"r.value->>{i}") for i, kind in enumerate(_LEAD_KINDS + kinds)
        )
        statement = text(
            f"INSERT INTO {name} ({', '.join(columns)}) SELECT {select} "
            "FROM json_array_elements(CAST(:data AS json)) AS r(value)"
        )
        for start in range(0, len(rows), POSTGRES_CHUNK_ROWS):
            part = rows[start : start + POSTGRES_CHUNK_ROWS]
            data = json.dumps(part, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            conn.execute(statement, {"data": data})
        return
    compiled = insert(sql_table(name, *(column(c) for c in columns)))
    for start in range(0, len(rows), CHUNK_ROWS):
        part = rows[start : start + CHUNK_ROWS]
        conn.execute(compiled, [dict(zip(columns, values, strict=True)) for values in part])


def write_snapshot(conn: Connection, scope: str, snapshot_id: str, snapshot: Snapshot) -> None:
    """Insert every typed row of ``snapshot``. The rows of ``snapshot_id`` must not exist yet."""
    for key, table in TYPED_TABLES.items():
        columns = ("row_id", "scope", "snapshot_id", *TABLE_COLUMNS[key])
        rows = [
            (row_id(snapshot_id, cast(int, cells[-1])), scope, snapshot_id, *cells)
            for cells in snapshot.tables[key]
        ]
        _insert(conn, table, columns, COLUMN_KINDS[key], rows)


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
