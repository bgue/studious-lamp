"""The sets that drop the "empty sorts last" term follow the NOT NULL columns of the DDL."""

from __future__ import annotations

import sqlite3

from tl_core.query.fields import ENVELOPE_FIELDS, NEVER_NULL_FIELDS, SORTABLE_FIELDS
from tl_core.services.queries import _NEVER_EMPTY  # pyright: ignore[reportPrivateUsage]
from tl_schema.ddl_loader import statements


def not_null_columns() -> set[str]:
    db = sqlite3.connect(":memory:")
    for statement in statements("cur_core_record", "sqlite"):
        db.execute(statement)
    return {row[1] for row in db.execute("PRAGMA table_info(cur_core_record)") if row[3]}


def test_never_null_fields_are_the_sortable_non_text_not_null_columns() -> None:
    expected = {
        name
        for name in SORTABLE_FIELDS
        if ENVELOPE_FIELDS[name].kind != "text" and name in not_null_columns()
    }
    assert set(NEVER_NULL_FIELDS) == expected


def test_never_empty_columns_are_not_null_and_not_text() -> None:
    assert _NEVER_EMPTY <= not_null_columns()
    assert all(ENVELOPE_FIELDS[name].kind != "text" for name in _NEVER_EMPTY)
