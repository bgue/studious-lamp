"""Generated current-state DDL runs and stores values alike on SQLite and Postgres (P0-I5-T10)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from tl_schema.ddl_loader import statements
from tl_schema.generators.ddl_types import Dialect

TABLES = [
    "cur_core_record",
    "cur_files",
    "cur_link_counts",
    "cur_links",
    "cur_numbering",
    "cur_pset_values",
    "cur_workflow_state",
]
STAMP = "2026-10-09T12:00:00.123456+00:00"

INSERT_RECORD = text(
    "INSERT INTO cur_core_record (id, key, type, scope, title, version, last_seq, created_at, "
    "updated_at) VALUES (:id, :key, 'core.Record', :scope, 't', 1, 1, :ts, :ts)"
)


def _kind(dialect: str) -> Dialect:
    return "postgres" if dialect == "postgres" else "sqlite"


def _create(engine: Engine, table: str, kind: Dialect) -> None:
    """Run one table's generated CREATE statements in one transaction."""
    with engine.begin() as conn:
        for statement in statements(table, kind):
            conn.exec_driver_sql(statement)


@pytest.fixture
def engine(new_engine: Callable[[], Engine], dialect: str) -> Engine:
    """An empty database on the adapter under test with all seven generated tables created."""
    eng = new_engine()
    kind = _kind(dialect)
    for table in TABLES:
        _create(eng, table, kind)
    return eng


@pytest.mark.parametrize("table", TABLES)
def test_every_generated_table_can_be_created_twice(
    table: str, new_engine: Callable[[], Engine], dialect: str
) -> None:
    eng = new_engine()
    kind = _kind(dialect)
    _create(eng, table, kind)
    _create(eng, table, kind)
    with eng.begin() as conn:
        assert table in inspect(conn).get_table_names()


def test_a_key_is_unique_within_a_scope_only(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(INSERT_RECORD, {"id": "a", "key": "K-1", "scope": "project:P1", "ts": STAMP})
        conn.execute(INSERT_RECORD, {"id": "b", "key": "K-1", "scope": "project:P2", "ts": STAMP})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(INSERT_RECORD, {"id": "c", "key": "K-1", "scope": "project:P1", "ts": STAMP})


def test_a_missing_key_never_collides(engine: Engine) -> None:
    with engine.begin() as conn:
        for record_id in ("n1", "n2"):
            conn.execute(
                INSERT_RECORD, {"id": record_id, "key": None, "scope": "project:P3", "ts": STAMP}
            )
        count = conn.execute(
            text("SELECT COUNT(*) FROM cur_core_record WHERE scope = :scope"),
            {"scope": "project:P3"},
        ).scalar_one()
    assert count == 2


def test_timestamps_booleans_and_json_come_back_as_they_went_in(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cur_core_record (id, type, scope, title, psets_json, voided, "
                "version, last_seq, created_at, updated_at) VALUES ('j', 'core.Record', "
                "'project:P4', 't', :psets, TRUE, 1, 1, :ts, :ts)"
            ),
            {"psets": '{"a":{"b":1},"z":[1,2]}', "ts": STAMP},
        )
        row = (
            conn.execute(
                text(
                    "SELECT created_at, updated_at, voided, psets_json "
                    "FROM cur_core_record WHERE id = 'j'"
                )
            )
            .mappings()
            .one()
        )
    assert row["created_at"] == STAMP
    assert row["updated_at"] == STAMP
    assert row["voided"] == 1
    assert row["psets_json"] == '{"a":{"b":1},"z":[1,2]}'


def test_numbers_keep_double_precision(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cur_pset_values (record_id, scope, path, pset, property_name, layer, "
                "value_type, value_num, value_bool, last_seq, updated_at) VALUES ('r', 'company', "
                "'p.x', 'p', 'x', 'standard', 'number', :n, :b, 1, :ts)"
            ),
            {"n": 1234567.891, "b": True, "ts": STAMP},
        )
        row = (
            conn.execute(
                text("SELECT value_num, value_bool FROM cur_pset_values WHERE record_id = 'r'")
            )
            .mappings()
            .one()
        )
    assert row["value_num"] == 1234567.891
    assert row["value_bool"] == 1
