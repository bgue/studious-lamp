"""The runtime loader returns the committed, generated DDL (P0-I1-T04b)."""

from __future__ import annotations

import sqlite3

import pytest
from tl_schema.ddl_loader import statements
from tl_schema.generators.ddl_types import Dialect


@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
def test_statements_are_split_and_terminated(dialect: Dialect) -> None:
    found = statements("cur_core_record", dialect)
    assert len(found) == 2
    assert found[0].startswith("CREATE TABLE IF NOT EXISTS cur_core_record (")
    assert found[1].startswith("CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_core_record_scope_key")
    assert all(s.endswith(";") for s in found)


def test_sqlite_statements_execute_one_by_one() -> None:
    db = sqlite3.connect(":memory:")
    for statement in statements("cur_core_record", "sqlite"):
        db.execute(statement)
    columns = [row[1] for row in db.execute("PRAGMA table_info(cur_core_record)")]
    assert columns[0] == "id"
    assert "psets_json" in columns


def test_unknown_table_raises() -> None:
    with pytest.raises(FileNotFoundError):
        statements("cur_nope", "sqlite")
