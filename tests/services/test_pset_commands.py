"""SetPsetValues against a real SQLite ledger (P0-I2-T06). Copied into place; do not edit."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import pytest
from tl_adapters.sqlite.uow import create_schema, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.schema_provider import DirectorySchemaProvider, get_provider, use_provider
from tl_core.services.commands import CommandResult, CreateRecord, VoidRecord
from tl_core.services.errors import (
    LayerError,
    NoChangesError,
    PsetValidationError,
    RecordNotFoundError,
    RecordVoidedError,
    UnknownPsetError,
)
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_create_record, handle_void_record
from tl_core.util import new_ulid

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
Layer = Literal["standard", "custom", "project"]


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


def make_record(db: Path, key: str = "V-1", scope: str = SCOPE) -> CommandResult:
    with open_uow(db) as uow:
        return handle_create_record(
            uow,
            CreateRecord(
                actor="user:u",
                source="test",
                scope=scope,
                record_type="core.Record",
                title="Valve",
                key=key,
            ),
        )


def set_values(
    db: Path,
    record: CommandResult,
    pset: str,
    values: dict[str, Any],
    *,
    layer: Layer = "standard",
    version: int | None = None,
    scope: str = SCOPE,
) -> CommandResult:
    cmd = SetPsetValues(
        actor="user:u",
        source="test",
        scope=scope,
        stream_id=record.stream_id,
        expected_version=record.version if version is None else version,
        pset=pset,
        layer=layer,
        values=values,
    )
    with open_uow(db) as uow:
        return handle_set_pset_values(uow, cmd)


def row(db: Path, record: CommandResult) -> dict[str, Any]:
    with open_uow(db, readonly=True) as uow:
        found = (
            uow.conn()
            .exec_driver_sql("SELECT * FROM cur_core_record WHERE id = ?", (record.stream_id,))
            .mappings()
            .one()
        )
        return dict(found)


def pset_rows(db: Path, record: CommandResult) -> dict[str, dict[str, Any]]:
    with open_uow(db, readonly=True) as uow:
        found = (
            uow.conn()
            .exec_driver_sql(
                "SELECT * FROM cur_pset_values WHERE record_id = ? ORDER BY path",
                (record.stream_id,),
            )
            .mappings()
        )
        return {r["path"]: dict(r) for r in found}


def event_count(db: Path) -> int:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.head_seq()


# --- writes ------------------------------------------------------------------------------------


def test_sets_standard_values_and_emits_one_event(db: Path) -> None:
    record = make_record(db)
    result = set_values(db, record, "valve_data", {"size_in": 4, "manufacturer": "Acme"})
    assert result.version == 2 and result.key == "V-1"
    [event] = result.events
    assert event.event_type == "Pset.ValuesSet"
    assert event.stream_id == record.stream_id and event.stream_type == "core.Record"
    assert event.scope == SCOPE and event.actor == "user:u" and event.source == "test"
    schema = get_provider().effective(SCOPE)
    assert event.payload == {
        "pset": "valve_data",
        "layer": "standard",
        "values": {"size_in": 4, "manufacturer": "Acme"},
        "effective_schema_hash": schema.hash,
        "conformance": "ok",
        "units": {"size_in": "[in_i]"},
    }


def test_projections_follow_the_event(db: Path) -> None:
    record = make_record(db)
    set_values(db, record, "valve_data", {"size_in": 4, "body_material": "CS", "manufacturer": "A"})
    stored = row(db, record)
    assert json.loads(stored["psets_json"]) == {
        "valve_data": {"size_in": 4, "body_material": "CS", "manufacturer": "A"}
    }
    assert stored["effective_schema_hash"] == get_provider().effective(SCOPE).hash
    assert stored["conformance"] == "ok"
    assert stored["version"] == 2
    assert stored["pset__valve_data__size_in"] == 4  # promoted column, added on first write
    assert stored["pset__valve_data__body_material"] == "CS"
    rows = pset_rows(db, record)
    assert rows["psets.valve_data.size_in"]["unit"] == "[in_i]"
    assert rows["psets.valve_data.size_in"]["layer"] == "standard"


def test_custom_and_project_layers(db: Path) -> None:
    record = make_record(db)
    first = set_values(db, record, "valve_data", {"x.fat_witness_by": "client"}, layer="custom")
    second = set_values(
        db,
        record,
        "prj.shutdown_tie_in",
        {"window": "SD-1", "approved": True},
        layer="project",
        version=first.version,
    )
    assert second.version == 3
    assert json.loads(row(db, record)["psets_json"]) == {
        "valve_data": {"x": {"fat_witness_by": "client"}},
        "prj": {"shutdown_tie_in": {"window": "SD-1", "approved": True}},
    }
    rows = pset_rows(db, record)
    assert rows["psets.valve_data.x.fat_witness_by"]["layer"] == "custom"
    assert rows["psets.prj.shutdown_tie_in.window"]["layer"] == "project"
    assert first.events[0].payload["layer"] == "custom"
    assert second.events[0].payload["units"] == {}


def test_a_missing_advisory_property_shows_a_warning(db: Path) -> None:
    record = make_record(db)
    set_values(db, record, "valve_data", {"size_in": 4})
    assert row(db, record)["conformance"] == "warning"  # manufacturer is advisory and required


def test_out_of_range_values_are_stored_and_flagged(db: Path) -> None:
    record = make_record(db)
    result = set_values(db, record, "valve_data", {"size_in": 500, "manufacturer": "A"})
    assert result.events[0].payload["conformance"] == "nonconformant"
    assert row(db, record)["conformance"] == "nonconformant"
    result = set_values(
        db, record, "valve_data", {"tag_no": "bad", "size_in": 4}, version=result.version
    )
    assert result.events[0].payload["conformance"] == "warning"  # tag_no pattern is advisory


def test_a_required_in_state_property_is_nonconformant_in_that_state(db: Path) -> None:
    record = make_record(db)
    with open_uow(db) as uow:
        appended = uow.append(
            stream_id=record.stream_id,
            stream_type="core.Record",
            scope=SCOPE,
            expected_version=record.version,
            events=[
                NewEvent(
                    event_type="Record.Corrected",
                    payload={"changes": {"status": [None, "Design"]}, "reason": "state for test"},
                )
            ],
            actor="user:u",
            source="test",
            correlation_id=new_ulid(),
        )
    result = set_values(
        db, record, "valve_data", {"manufacturer": "Acme"}, version=appended.new_version
    )
    assert result.events[0].payload["conformance"] == "nonconformant"  # size_in, body_material


def test_locked_psets_accept_values(db: Path) -> None:
    record = make_record(db, scope="company")
    result = set_values(db, record, "safety_data", {"sil_rating": 2}, scope="company")
    assert result.events[0].payload["conformance"] == "ok"


def test_rebuilding_projections_reproduces_the_rows(db: Path) -> None:
    record = make_record(db)
    first = set_values(db, record, "valve_data", {"size_in": 4, "manufacturer": "A"})
    set_values(
        db, record, "valve_data", {"x.fat_witness_by": "c"}, layer="custom", version=first.version
    )
    before = (row(db, record), pset_rows(db, record))
    assert rebuild_projections(db) == 3
    assert (row(db, record), pset_rows(db, record)) == before


# --- refusals: nothing is appended -------------------------------------------------------------


@pytest.mark.parametrize(
    ("pset", "layer", "values", "error"),
    [
        ("valve_data", "standard", {"size_in": "four"}, PsetValidationError),
        ("valve_data", "standard", {"nope": 1}, PsetValidationError),
        ("valve_data", "standard", {"size_in": None}, PsetValidationError),
        ("valve_data", "custom", {"x.nope": "v"}, PsetValidationError),
        ("prj.shutdown_tie_in", "project", {"approved": "yes"}, PsetValidationError),
        ("prj.shutdown_tie_in", "project", {"zzz": 1}, PsetValidationError),
        ("valve_data", "standard", {"x.fat_witness_by": "c"}, LayerError),
        ("valve_data", "custom", {"size_in": 4}, LayerError),
        ("valve_data", "project", {"size_in": 4}, LayerError),
        ("prj.shutdown_tie_in", "standard", {"window": "w"}, LayerError),
        ("prj.shutdown_tie_in", "custom", {"x.window": "w"}, LayerError),
        ("enrich.ai_classifier", "standard", {"valve_type": "ball"}, LayerError),
        ("src.ifc.Pset_V", "standard", {"Size": 1}, LayerError),
        ("no_such_pset", "standard", {"a": 1}, UnknownPsetError),
        ("safety_data", "standard", {"sil_rating": 2}, UnknownPsetError),  # not adopted by P123
        ("valve_data", "standard", {}, NoChangesError),
    ],
)
def test_refusals_append_nothing(
    db: Path, pset: str, layer: Layer, values: dict[str, Any], error: type[Exception]
) -> None:
    record = make_record(db)
    before = event_count(db)
    with pytest.raises(error):
        set_values(db, record, pset, values, layer=layer)
    assert event_count(db) == before


def test_validation_errors_list_each_issue(db: Path) -> None:
    record = make_record(db)
    with pytest.raises(PsetValidationError) as caught:
        set_values(db, record, "valve_data", {"size_in": "four", "manufacturer": 7})
    assert len(caught.value.issues) == 2
    assert caught.value.issues[0].startswith("psets.valve_data.manufacturer")
    assert caught.value.issues[1].startswith("psets.valve_data.size_in")


def test_a_locked_pset_has_no_custom_section(db: Path) -> None:
    record = make_record(db, scope="company")
    with pytest.raises(LayerError):
        set_values(db, record, "safety_data", {"x.note": "n"}, layer="custom", scope="company")


def test_unchanged_values_are_refused(db: Path) -> None:
    record = make_record(db)
    first = set_values(db, record, "valve_data", {"size_in": 4})
    with pytest.raises(NoChangesError):
        set_values(db, record, "valve_data", {"size_in": 4}, version=first.version)


def test_record_checks(db: Path) -> None:
    record = make_record(db)
    with pytest.raises(RecordNotFoundError):
        set_values(
            db,
            CommandResult(stream_id=new_ulid(), key=None, version=1, events=[]),
            "valve_data",
            {"size_in": 4},
        )
    other_scope = make_record(db, key="C-1", scope="company")
    with pytest.raises(RecordNotFoundError):  # the record lives in another scope
        set_values(db, other_scope, "valve_data", {"size_in": 4}, scope=SCOPE)
    with pytest.raises(ConcurrencyError):
        set_values(db, record, "valve_data", {"size_in": 4}, version=5)
    with open_uow(db) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor="user:u",
                source="test",
                scope=SCOPE,
                stream_id=record.stream_id,
                expected_version=record.version,
                reason="dup",
            ),
        )
    with pytest.raises(RecordVoidedError):
        set_values(db, record, "valve_data", {"size_in": 4}, version=2)
