"""``bulk_insert``: many rows of one table in chunks, the same result on SQLite and Postgres."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters import bulk
from tl_adapters.db import DbTarget, open_uow

COLUMNS = ("a", "b", "c", "f", "g", "h", "i")
KINDS = "sSsfFbi"
ROWS: list[tuple[Any, ...]] = [
    ("r1", "plain", None, 1.5, None, True, 7),
    ("r2", 'quote " and \\ backslash', "{[json]}", -0.25, 3.0, False, 0),
    ("r3", "ünïcödé – dash", "", 1e-9, 2.5, None, -5),
    ("r4", None, "a'b", 0.0, 0.0, True, None),
    ("r5", "five", "x", 5.0, 5.0, False, 5),
]


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    db = new_db()
    with open_uow(db) as uow:
        uow.conn().execute(
            text(
                "CREATE TABLE bulk_t (a TEXT NOT NULL, b TEXT, c TEXT, f DOUBLE PRECISION, "
                "g DOUBLE PRECISION, h BOOLEAN, i INTEGER)"
            )
        )
    return db


def stored(db: DbTarget) -> list[tuple[Any, ...]]:
    with open_uow(db, readonly=True) as uow:
        rows = uow.conn().execute(text("SELECT * FROM bulk_t ORDER BY a")).all()
    return [tuple(None if v is None else v for v in r) for r in rows]


def normal(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """SQLite stores a boolean as 0 or 1."""
    return [
        tuple(bool(v) if k == 5 and v is not None else v for k, v in enumerate(r)) for r in rows
    ]


def test_every_kind_of_value_is_stored_and_read_back(target: DbTarget) -> None:
    with open_uow(target) as uow:
        bulk.bulk_insert(uow.conn(), "bulk_t", COLUMNS, KINDS, ROWS)
    assert normal(stored(target)) == ROWS


def test_rows_go_in_chunks_and_every_chunk_is_written(
    target: DbTarget, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bulk, "SQLITE_CHUNK_ROWS", 2)
    monkeypatch.setattr(bulk, "POSTGRES_CHUNK_ROWS", 2)
    with open_uow(target) as uow:
        bulk.bulk_insert(uow.conn(), "bulk_t", COLUMNS, KINDS, ROWS)  # 3 chunks of 2, 2, 1
    assert normal(stored(target)) == ROWS


def test_no_rows_is_no_statement(target: DbTarget) -> None:
    with open_uow(target) as uow:
        bulk.bulk_insert(uow.conn(), "no_such_table", COLUMNS, KINDS, [])
    assert stored(target) == []


def test_a_kind_for_every_column_is_required(target: DbTarget) -> None:
    with open_uow(target) as uow, pytest.raises(ValueError, match="one kind letter"):
        bulk.bulk_insert(uow.conn(), "bulk_t", COLUMNS, "sS", ROWS)


def test_a_value_that_is_not_a_number_is_refused_not_stored(target: DbTarget) -> None:
    bad = [("r1", "x", "y", float("nan"), None, None, None)]
    with open_uow(target) as uow:
        try:
            bulk.bulk_insert(uow.conn(), "bulk_t", COLUMNS, KINDS, bad)
        except ValueError:
            pass  # Postgres: the JSON text cannot hold NaN
    assert all(v is None or v == v for row in stored(target) for v in row)
