"""Profile the rows of a file with DuckDB (brief 29.6: columns, value distributions, keys,
duplicates, pattern matches).

The rows go into an in-memory DuckDB table of text columns through a scratch NDJSON file (the way
the lake loads: row by row inserts are orders of magnitude slower), and each column is asked a few
SQL questions. Nothing is written to the lake or the ledger. Column names become ``c0``, ``c1``,
... inside SQL, so a header can never be an identifier or an injection; the profile is keyed by the
original names, which the reader has already bounded (200 columns, 255 characters).

A value shown is cut to 60 characters, and at most five values are shown per column. A column is a
*key candidate* when it has no empty cell and no repeat.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import duckdb
from pydantic import BaseModel

from tl_mod_legacy.limits import MAX_PROFILE_VALUES, MAX_VALUE_SHOWN
from tl_mod_legacy.model import Grid

_SHAPES = (
    ("integer", r"^[0-9]+$"),
    ("decimal", r"^-?[0-9]+\.[0-9]+$"),
    ("date", r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    ("code", r"^[A-Za-z0-9]+([-_./][A-Za-z0-9]+)+$"),
    ("word", r"^[A-Za-z]+$"),
)


class ValueCount(BaseModel):
    value: str
    count: int


class ColumnProfile(BaseModel):
    name: str
    non_empty: int
    empty: int
    distinct: int
    repeats: int  # non-empty cells that repeat an earlier value
    min_length: int
    max_length: int
    shape: str | None  # the one shape every non-empty cell has, or None
    key_candidate: bool
    top_values: list[ValueCount]


class Profile(BaseModel):
    rows: int
    columns: list[ColumnProfile]
    duplicate_rows: int  # rows identical to an earlier row in every column


def _shown(value: str) -> str:
    return value if len(value) <= MAX_VALUE_SHOWN else value[: MAX_VALUE_SHOWN - 1] + "…"


def profile_grid(grid: Grid) -> Profile:
    """The profile of ``grid``. An empty grid has a profile with no rows."""
    names = [f"c{i}" for i in range(len(grid.columns))]
    con = duckdb.connect(":memory:", config={"autoload_known_extensions": False})
    try:
        if grid.rows and names:
            _load(con, grid, names)
        else:
            con.execute(
                "CREATE TABLE t (" + ", ".join(f"{n} VARCHAR" for n in names or ["c0"]) + ")"
            )
        columns = [
            _column(con, original, name, len(grid.rows))
            for original, name in zip(grid.columns, names, strict=True)
        ]
        duplicate_rows = 0
        if grid.rows and names:
            row = con.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT ("
                + ", ".join(f"COALESCE({n}, '')" for n in names)
                + ")) FROM t"
            ).fetchone()
            duplicate_rows = int(row[0]) if row else 0
        return Profile(rows=len(grid.rows), columns=columns, duplicate_rows=duplicate_rows)
    finally:
        con.close()


def _load(con: duckdb.DuckDBPyConnection, grid: Grid, names: list[str]) -> None:
    spec = ", ".join(f"'{n}': 'VARCHAR'" for n in names)
    with tempfile.TemporaryDirectory(prefix="tl-profile-") as scratch:
        path = Path(scratch) / "rows.ndjson"
        with path.open("w", encoding="utf-8") as out:
            for row in grid.rows:
                out.write(json.dumps(dict(zip(names, row, strict=True)), ensure_ascii=False))
                out.write("\n")
        literal = str(path).replace("'", "''")
        con.execute(
            "CREATE TABLE t AS SELECT * FROM read_json('"
            + literal
            + "', format = 'newline_delimited', columns = {"
            + spec
            + "})"
        )


def _column(con: duckdb.DuckDBPyConnection, original: str, name: str, rows: int) -> ColumnProfile:
    stats = con.execute(
        f"SELECT COUNT(NULLIF({name}, '')), COUNT(DISTINCT NULLIF({name}, '')), "
        f"COALESCE(MIN(LENGTH(NULLIF({name}, ''))), 0), "
        f"COALESCE(MAX(LENGTH(NULLIF({name}, ''))), 0) "
        "FROM t"
    ).fetchone()
    assert stats is not None
    non_empty, distinct, shortest, longest = (int(v) for v in stats)
    top = con.execute(
        f"SELECT {name}, COUNT(*) AS n FROM t WHERE NULLIF({name}, '') IS NOT NULL "
        f"GROUP BY {name} ORDER BY n DESC, {name} LIMIT {MAX_PROFILE_VALUES}"
    ).fetchall()
    shape: str | None = None
    if non_empty:
        for label, pattern in _SHAPES:
            matched = con.execute(
                f"SELECT COUNT(*) FROM t WHERE NULLIF({name}, '') IS NOT NULL "
                f"AND regexp_matches({name}, '{pattern}')"
            ).fetchone()
            if matched is not None and int(matched[0]) == non_empty:
                shape = label
                break
    return ColumnProfile(
        name=original,
        non_empty=non_empty,
        empty=rows - non_empty,
        distinct=distinct,
        repeats=non_empty - distinct,
        min_length=shortest,
        max_length=longest,
        shape=shape,
        key_candidate=bool(rows) and non_empty == rows and distinct == non_empty,
        top_values=[ValueCount(value=_shown(str(v)), count=int(n)) for v, n in top],
    )
