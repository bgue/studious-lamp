"""Writing many rows of one table quickly, on each database (ADR-0015 section 4).

A snapshot of a P6 schedule can have hundreds of thousands of typed rows. Building one ``INSERT``
with a bound parameter for every cell costs more than writing the rows, and the pure-Python
Postgres driver makes one round trip per row of an ``executemany`` (535 s at the largest legal
snapshot). So the shape differs by database, and this is the one place that knows it:

* **Postgres**: one statement per chunk with a single bound parameter, the rows as JSON text, read
  by ``json_array_elements`` and cast column by column (25 s at the same size). The text is bound,
  never spliced into the SQL; the table and column names are the caller's constants.
* **SQLite**: one compiled ``INSERT`` executed with a list of parameter sets (``executemany`` is a
  loop inside the C driver).

``kinds`` has one letter per column (``s``/``S`` text, ``f``/``F`` float, ``b`` boolean, ``i``
integer); an upper-case letter is the same type as the lower-case one (a column that may be NULL
in the caller's terms). Values are the Python values, ``None`` for NULL.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, column, insert, text
from sqlalchemy import table as sql_table
from sqlalchemy.sql.expression import ColumnClause

#: Rows sent to the driver in one call on SQLite, and in one statement on Postgres.
SQLITE_CHUNK_ROWS = 5000
POSTGRES_CHUNK_ROWS = 20_000

#: How a column of each kind is read out of the JSON on Postgres.
_CASTS = {
    "s": "{}",
    "S": "{}",
    "f": "({})::float8",
    "F": "({})::float8",
    "b": "({})::boolean",
    "i": "({})::integer",
}


def bulk_insert(
    conn: Connection,
    name: str,
    columns: Sequence[str],
    kinds: str,
    rows: Sequence[Sequence[Any]],
) -> None:
    """Insert ``rows`` into ``name`` (``columns``, one ``kinds`` letter each), in chunks."""
    if len(columns) != len(kinds):
        raise ValueError("one kind letter per column")
    if not rows:
        return
    if conn.dialect.name == "postgresql":
        select = ", ".join(_CASTS[kind].format(f"r.value->>{i}") for i, kind in enumerate(kinds))
        statement = text(
            f"INSERT INTO {name} ({', '.join(columns)}) SELECT {select} "
            "FROM json_array_elements(CAST(:data AS json)) AS r(value)"
        )
        for start in range(0, len(rows), POSTGRES_CHUNK_ROWS):
            part = rows[start : start + POSTGRES_CHUNK_ROWS]
            data = json.dumps(part, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            conn.execute(statement, {"data": data})
        return
    named: list[ColumnClause[Any]] = [column(c) for c in columns]
    compiled = insert(sql_table(name, *named))
    for start in range(0, len(rows), SQLITE_CHUNK_ROWS):
        part = rows[start : start + SQLITE_CHUNK_ROWS]
        conn.execute(compiled, [dict(zip(columns, values, strict=True)) for values in part])
