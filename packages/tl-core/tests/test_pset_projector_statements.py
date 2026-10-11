"""PsetProjector round trips (P0-I8 D13): one statement for all the rows of a record, same rows.

Projector time on Postgres is dominated by statements, not by data: a record with five pset
values cost nine statements to project (read the record, read the units, delete, five inserts).
These tests pin the budget and the rows. The behaviour tests stay in ``test_pset_projector.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, event, text
from tl_core.ledger import Event
from tl_core.projection.defaults import default_registry
from tl_core.projection.pset import PsetProjector
from tl_core.projection.record import RecordProjector

AT = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
RID = "rec-1"


def make(seq: int, event_type: str, payload: dict[str, Any], version: int = 1) -> Event:
    return Event(
        event_type=event_type,
        payload=payload,
        seq=seq,
        event_id=f"E{seq:06d}",
        stream_id=RID,
        stream_type="core.Record",
        stream_version=version,
        scope="project:P123",
        actor="user:test",
        recorded_at=AT,
        effective_at=AT,
        correlation_id="c",
        causation_id=None,
        source="test",
        prev_hash=None,
        hash=f"h{seq}",
    )


def created(psets: dict[str, Any]) -> Event:
    payload = {"record_type": "core.Record", "key": "K-1", "title": "t", "psets": psets}
    return make(1, "Record.Created", payload)


FIVE = {
    "valve_data": {"size_in": 4.0, "body_material": "SS316L", "fail_action": "FC", "tag_no": "V-1"},
    "inspection": {"interval_days": 90},
}


@pytest.fixture
def engine(new_engine: Callable[[], Engine], dialect: str) -> Iterator[Engine]:
    eng = new_engine()
    with eng.begin() as conn:
        for projector in default_registry().all():
            for statement in projector.ddl(dialect):
                conn.exec_driver_sql(statement)
    yield eng
    eng.dispose()


def count_statements(conn: Connection, run: Callable[[], None]) -> list[str]:
    seen: list[str] = []

    def listener(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
        seen.append(statement)

    event.listen(conn.engine, "before_cursor_execute", listener)
    try:
        run()
    finally:
        event.remove(conn.engine, "before_cursor_execute", listener)
    return seen


def rows(conn: Connection) -> list[dict[str, Any]]:
    found = conn.execute(text("SELECT * FROM cur_pset_values ORDER BY path")).mappings()
    return [dict(r) for r in found]


def test_a_new_record_with_five_values_is_projected_in_at_most_three_statements(
    engine: Engine,
) -> None:
    first = created(FIVE)
    with engine.begin() as conn:
        RecordProjector().apply(conn, first)
        statements = count_statements(conn, lambda: PsetProjector().apply(conn, first))
        found = rows(conn)
    assert len(statements) <= 3, statements
    assert [(r["path"], r["value_type"]) for r in found] == [
        ("psets.inspection.interval_days", "number"),
        ("psets.valve_data.body_material", "string"),
        ("psets.valve_data.fail_action", "string"),
        ("psets.valve_data.size_in", "number"),
        ("psets.valve_data.tag_no", "string"),
    ]
    by_path = {r["path"]: r for r in found}
    size = by_path["psets.valve_data.size_in"]
    assert size["value_num"] == 4.0 and size["value_text"] is None and size["value_bool"] is None
    assert size["pset"] == "valve_data" and size["property_name"] == "size_in"
    assert size["layer"] == "standard" and size["unit"] is None
    assert size["record_id"] == RID and size["scope"] == "project:P123" and size["last_seq"] == 1
    tag = by_path["psets.valve_data.tag_no"]
    assert tag["value_text"] == "V-1" and tag["value_num"] is None


def test_a_created_event_without_psets_writes_no_pset_rows(engine: Engine) -> None:
    first = created({})
    with engine.begin() as conn:
        RecordProjector().apply(conn, first)
        PsetProjector().apply(conn, first)
        assert rows(conn) == []


def test_booleans_lists_and_nulls_survive_the_single_insert(engine: Engine) -> None:
    psets = {"flags": {"on": True, "tags": ["a", "b"], "count": 3}}
    first = created(psets)
    with engine.begin() as conn:
        RecordProjector().apply(conn, first)
        PsetProjector().apply(conn, first)
        found = {r["path"]: r for r in rows(conn)}
    assert found["psets.flags.on"]["value_bool"] in (True, 1)
    assert found["psets.flags.on"]["value_type"] == "boolean"
    assert found["psets.flags.tags"]["value_type"] == "json"
    assert found["psets.flags.tags"]["value_json"] == '["a","b"]'
    assert found["psets.flags.count"]["value_num"] == 3


def test_hundreds_of_values_in_one_record_are_all_written(engine: Engine) -> None:
    psets = {"big": {f"p{i:04d}": i for i in range(1500)}}
    first = created(psets)
    with engine.begin() as conn:
        RecordProjector().apply(conn, first)
        PsetProjector().apply(conn, first)
        count = conn.execute(text("SELECT COUNT(*) FROM cur_pset_values")).scalar_one()
    assert count == 1500


def test_a_values_set_of_three_values_costs_at_most_six_statements(engine: Engine) -> None:
    first = created(FIVE)
    update = make(
        2,
        "Pset.ValuesSet",
        {
            "pset": "valve_data",
            "layer": "standard",
            "values": {"size_in": 6.0, "body_material": "CS", "fail_action": None},
            "effective_schema_hash": "hash-1",
            "conformance": "ok",
            "units": {"size_in": "[in_i]"},
        },
        version=2,
    )
    with engine.begin() as conn:
        RecordProjector().apply(conn, first)
        PsetProjector().apply(conn, first)
        statements = count_statements(conn, lambda: PsetProjector().apply(conn, update))
        found = {r["path"]: r for r in rows(conn)}
    assert len(statements) <= 6, statements
    assert found["psets.valve_data.size_in"]["value_num"] == 6.0
    assert found["psets.valve_data.size_in"]["unit"] == "[in_i]"
    assert found["psets.valve_data.body_material"]["value_text"] == "CS"
    assert "psets.valve_data.fail_action" not in found
    assert found["psets.valve_data.tag_no"]["last_seq"] == 2  # rebuilt from the merged psets
