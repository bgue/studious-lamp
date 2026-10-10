"""Unsetting pset values: replay determinism and clearing locked or state-required values."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow, rebuild_projections
from tl_core.ledger import NewEvent
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.psets import SetPsetValues, conformance, handle_set_pset_values
from tl_core.services.records import handle_create_record
from tl_core.util import new_ulid

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    path = new_db()
    create_schema(path)
    return path


def create(db: DbTarget, scope: str) -> CommandResult:
    with open_uow(db) as uow:
        return handle_create_record(
            uow,
            CreateRecord(
                actor="user:u",
                source="test",
                scope=scope,
                record_type="core.Record",
                title="Valve",
                key="V-1",
            ),
        )


def write(
    db: DbTarget, record: CommandResult, scope: str, pset: str, values: dict[str, Any], version: int
) -> CommandResult:
    cmd = SetPsetValues(
        actor="user:u",
        source="test",
        scope=scope,
        stream_id=record.stream_id,
        expected_version=version,
        pset=pset,
        layer="standard",
        values=values,
    )
    with open_uow(db) as uow:
        return handle_set_pset_values(uow, cmd)


def set_state(db: DbTarget, record: CommandResult, scope: str, version: int, state: str) -> int:
    with open_uow(db) as uow:
        result = uow.append(
            stream_id=record.stream_id,
            stream_type="core.Record",
            scope=scope,
            expected_version=version,
            events=[
                NewEvent(
                    event_type="Record.Corrected",
                    payload={"changes": {"status": [None, state]}, "reason": "test state"},
                )
            ],
            actor="user:u",
            source="test",
            correlation_id=new_ulid(),
        )
    return result.new_version


def snapshot(db: DbTarget, record: CommandResult) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        row = (
            conn.execute(
                text("SELECT * FROM cur_core_record WHERE id = :id"),
                {"id": record.stream_id},
            )
            .mappings()
            .one()
        )
        values = conn.execute(
            text("SELECT * FROM cur_pset_values WHERE record_id = :id ORDER BY path"),
            {"id": record.stream_id},
        ).mappings()
        return dict(row), [dict(v) for v in values]


def test_set_unset_set_replays_to_the_same_rows(db: DbTarget) -> None:
    scope = "project:P123"
    record = create(db, scope)
    version = record.version
    for values in ({"size_in": 4, "manufacturer": "A"}, {"size_in": None}, {"size_in": 6}):
        version = write(db, record, scope, "valve_data", values, version).version
    before = snapshot(db, record)
    assert json.loads(before[0]["psets_json"]) == {
        "valve_data": {"size_in": 6, "manufacturer": "A"}
    }
    assert before[0]["pset__valve_data__size_in"] == 6
    assert rebuild_projections(db) == 4
    assert snapshot(db, record) == before
    assert rebuild_projections(db) == 4
    assert snapshot(db, record) == before


def test_clearing_a_state_required_value_succeeds_and_reports_nonconformant(db: DbTarget) -> None:
    scope = "project:P123"
    record = create(db, scope)
    version = write(
        db,
        record,
        scope,
        "valve_data",
        {"size_in": 4, "body_material": "CS", "manufacturer": "A"},
        record.version,
    ).version
    version = set_state(db, record, scope, version, "Design")
    with open_uow(db, readonly=True) as uow:
        assert conformance(uow, record.stream_id).status == "ok"
    cleared = write(db, record, scope, "valve_data", {"size_in": None}, version)
    assert cleared.events[0].payload["values"] == {"size_in": None}
    assert cleared.events[0].payload["conformance"] == "nonconformant"
    with open_uow(db, readonly=True) as uow:
        report = conformance(uow, record.stream_id)
    assert [(i.path, i.rule, i.level) for i in report.issues] == [
        ("psets.valve_data.size_in", "required_in_state", "nonconformant")
    ]


def test_clearing_a_value_in_a_locked_pset_is_a_data_edit(db: DbTarget) -> None:
    scope = "company"
    record = create(db, scope)
    version = write(db, record, scope, "safety_data", {"sil_rating": 2}, record.version).version
    version = set_state(db, record, scope, version, "Installed")
    cleared = write(db, record, scope, "safety_data", {"sil_rating": None}, version)
    assert cleared.events[0].payload["conformance"] == "ok"  # nothing left in the pset: not engaged
    row, rows = snapshot(db, record)
    assert json.loads(row["psets_json"]) == {}
    assert rows == []


def test_clearing_a_locked_property_of_an_open_pset(db: DbTarget) -> None:
    scope = "project:P123"
    record = create(db, scope)
    first = write(
        db, record, scope, "valve_data", {"fail_action": "FC", "manufacturer": "A"}, record.version
    )
    cleared = write(db, record, scope, "valve_data", {"fail_action": None}, first.version)
    assert cleared.events[0].payload["conformance"] == "ok"  # locked is not required-in-state
    assert json.loads(snapshot(db, record)[0]["psets_json"]) == {
        "valve_data": {"manufacturer": "A"}
    }
