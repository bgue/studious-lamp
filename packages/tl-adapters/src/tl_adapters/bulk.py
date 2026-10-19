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

Table and column names must be letters, digits and underscores (and are quoted on Postgres); a
float that is NaN or infinite is a ``ValueError`` on both databases. ``kinds`` has one letter per
column (``s``/``S`` text, ``f``/``F`` float, ``b`` boolean, ``i`` integer); an upper-case letter is
the same type as the lower-case one (a column that may be NULL in the caller's terms). Values are
the Python values, ``None`` for NULL.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, column, insert, text
from sqlalchemy import table as sql_table
from sqlalchemy.sql.expression import ColumnClause

#: A table or column name: letters, digits and underscores. The names are the caller's constants,
#: but they are spliced into the Postgres statement, so they are checked and quoted all the same.
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

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


def _require_finite(kinds: str, rows: Sequence[Sequence[Any]]) -> None:
    """A number that is not finite is refused on both databases (SQLite would store NULL for NaN,
    Postgres cannot read it out of JSON): the same rows give the same result."""
    floats = [i for i, kind in enumerate(kinds) if kind in "fF"]
    for row in rows:
        for i in floats:
            value = row[i]
            if value is not None and not math.isfinite(value):
                raise ValueError("a number that is not finite")


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
    if any(kind not in _CASTS for kind in kinds):
        raise ValueError("an unknown kind letter")
    if any(_NAME.fullmatch(word) is None for word in (name, *columns)):
        raise ValueError("a table or column name is not letters, digits and underscores")
    if not rows:
        return
    _require_finite(kinds, rows)
    if conn.dialect.name == "postgresql":
        quote = conn.dialect.identifier_preparer.quote
        select = ", ".join(_CASTS[kind].format(f"r.value->>{i}") for i, kind in enumerate(kinds))
        statement = text(
            f"INSERT INTO {quote(name)} ({', '.join(quote(c) for c in columns)}) "
            f"SELECT {select} FROM json_array_elements(CAST(:data AS json)) AS r(value)"
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
