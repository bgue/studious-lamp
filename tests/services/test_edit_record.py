"""EditRecord: field changes and pset batches in one unit of work (P0-I3-T00)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CommandResult, CreateRecord, VoidRecord
from tl_core.services.edit import EditRecord, PsetEdit, handle_edit_record
from tl_core.services.errors import (
    LayerError,
    NoChangesError,
    PsetValidationError,
    RecordVoidedError,
    UnknownPsetError,
)
from tl_core.services.records import handle_create_record, handle_void_record

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


@pytest.fixture
def record(db: Path) -> CommandResult:
    with open_uow(db) as uow:
        return handle_create_record(
            uow,
            CreateRecord(
                actor="user:u",
                source="test",
                scope=SCOPE,
                record_type="core.Record",
                title="Valve",
                key="V-1",
            ),
        )


def edit(
    db: Path,
    record: CommandResult,
    *,
    changes: dict[str, object] | None = None,
    pset_edits: list[PsetEdit] | None = None,
    version: int | None = None,
    correlation_id: str | None = None,
) -> CommandResult:
    cmd = EditRecord(
        actor="user:u",
        source="test",
        scope=SCOPE,
        stream_id=record.stream_id,
        expected_version=record.version if version is None else version,
        changes=changes or {},
        pset_edits=pset_edits or [],
        correlation_id=correlation_id,
    )
    with open_uow(db) as uow:
        return handle_edit_record(uow, cmd)


def stored(db: Path, record: CommandResult) -> dict[str, object]:
    with open_uow(db, readonly=True) as uow:
        found = (
            uow.conn()
            .exec_driver_sql("SELECT * FROM cur_core_record WHERE id = ?", (record.stream_id,))
            .mappings()
            .one()
        )
        return dict(found)


def head(db: Path) -> int:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.head_seq()


STANDARD = PsetEdit(pset="valve_data", layer="standard", values={"size_in": 4, "manufacturer": "A"})
CUSTOM = PsetEdit(pset="valve_data", layer="custom", values={"x.fat_witness_by": "client"})
PROJECT = PsetEdit(pset="prj.shutdown_tie_in", layer="project", values={"window": "SD-1"})


def test_field_changes_and_pset_edits_are_events_of_one_correlation(
    db: Path, record: CommandResult
) -> None:
    result = edit(db, record, changes={"title": "Renamed"}, pset_edits=[STANDARD, CUSTOM, PROJECT])
    assert result.version == record.version + 4
    assert result.key == "V-1"
    assert [e.event_type for e in result.events] == [
        "Record.Updated",
        "Pset.ValuesSet",
        "Pset.ValuesSet",
        "Pset.ValuesSet",
    ]
    assert [e.stream_version for e in result.events] == [2, 3, 4, 5]
    assert len({e.correlation_id for e in result.events}) == 1
    assert [e.payload.get("layer") for e in result.events[1:]] == ["standard", "custom", "project"]
    found = stored(db, record)
    assert found["title"] == "Renamed" and found["version"] == record.version + 4
    assert json.loads(str(found["psets_json"])) == {
        "valve_data": {"size_in": 4, "manufacturer": "A", "x": {"fat_witness_by": "client"}},
        "prj": {"shutdown_tie_in": {"window": "SD-1"}},
    }


def test_the_callers_correlation_id_is_used_for_every_event(
    db: Path, record: CommandResult
) -> None:
    result = edit(db, record, changes={"title": "B"}, pset_edits=[STANDARD], correlation_id="C-ONE")
    assert {e.correlation_id for e in result.events} == {"C-ONE"}


def test_only_pset_edits_or_only_field_changes_work(db: Path, record: CommandResult) -> None:
    first = edit(db, record, pset_edits=[STANDARD])
    assert [e.event_type for e in first.events] == ["Pset.ValuesSet"]
    second = edit(db, first, changes={"description": "Gate valve"})
    assert [e.event_type for e in second.events] == ["Record.Updated"]
    assert second.version == record.version + 2


def test_a_part_that_changes_nothing_is_skipped(db: Path, record: CommandResult) -> None:
    first = edit(db, record, pset_edits=[STANDARD])
    again = edit(
        db,
        first,
        changes={"title": "Valve"},  # same as now
        pset_edits=[STANDARD, CUSTOM],  # the first is unchanged, the second is new
    )
    assert [e.event_type for e in again.events] == ["Pset.ValuesSet"]
    assert again.events[0].payload["layer"] == "custom"
    assert again.version == first.version + 1


def test_an_edit_that_changes_nothing_is_refused_and_writes_nothing(
    db: Path, record: CommandResult
) -> None:
    first = edit(db, record, pset_edits=[STANDARD])
    before = head(db)
    with pytest.raises(NoChangesError):
        edit(db, first, changes={"title": "Valve"}, pset_edits=[STANDARD])
    with pytest.raises(NoChangesError):
        edit(db, first)
    assert head(db) == before


@pytest.mark.parametrize(
    ("bad", "error"),
    [
        (
            PsetEdit(pset="valve_data", layer="standard", values={"size_in": "big"}),
            PsetValidationError,
        ),
        (PsetEdit(pset="valve_data", layer="standard", values={"nope": 1}), PsetValidationError),
        (PsetEdit(pset="nope", layer="standard", values={"a": 1}), UnknownPsetError),
        (PsetEdit(pset="valve_data", layer="project", values={"size_in": 4}), LayerError),
    ],
)
def test_a_refused_part_rolls_back_the_parts_before_it(
    db: Path, record: CommandResult, bad: PsetEdit, error: type[Exception]
) -> None:
    before = head(db)
    with pytest.raises(error):
        edit(db, record, changes={"title": "Renamed"}, pset_edits=[STANDARD, bad])
    assert head(db) == before
    found = stored(db, record)
    assert found["title"] == "Valve" and found["version"] == record.version
    assert json.loads(str(found["psets_json"])) == {}


def test_a_stale_expected_version_writes_nothing(db: Path, record: CommandResult) -> None:
    edit(db, record, changes={"title": "Other"})  # somebody else saved first
    before = head(db)
    with pytest.raises(ConcurrencyError):
        edit(db, record, changes={"title": "Mine"}, pset_edits=[STANDARD])
    assert head(db) == before
    assert stored(db, record)["title"] == "Other"


def test_a_stale_expected_version_is_caught_when_there_are_only_pset_edits(
    db: Path, record: CommandResult
) -> None:
    edit(db, record, changes={"title": "Other"})
    with pytest.raises(ConcurrencyError):
        edit(db, record, pset_edits=[STANDARD])


def test_a_voided_record_cannot_be_edited(db: Path, record: CommandResult) -> None:
    with open_uow(db) as uow:
        voided = handle_void_record(
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
        edit(db, voided, changes={"title": "X"}, pset_edits=[STANDARD])
