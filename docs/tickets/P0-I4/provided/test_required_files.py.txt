"""Required file slots: the missing list (P0-I4-T23). Rows of cur_files are inserted with SQL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.files.required import MissingFile, missing_required_files, unmet_file_slots
from tl_core.files.slots import FileSlot, FileSlotRegistry
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.records import handle_create_record

REPORT = FileSlot(name="report", cardinality="one", required_in_states=["Approved", "Closed"])
CERT = FileSlot(name="certificate", required_in_states=["Closed"])
PHOTO = FileSlot(name="photo")  # optional: no required_in_states
REGISTRY = FileSlotRegistry({"core.Record": [REPORT, PHOTO, CERT]})

INSERT = text(
    "INSERT INTO cur_files (file_id, scope, record_id, slot, revision, sha256, size, content_type, "
    "filename, status, deduplicated, superseded_by, uploaded_by, uploaded_at, updated_at, version, "
    "last_seq) VALUES (:file_id, 'project:P123', :record_id, :slot, 1, :sha, 1, 'text/plain', "
    "'f.txt', :status, 0, :superseded_by, 'user:t', '2026-01-01T00:00:00+00:00', "
    "'2026-01-01T00:00:00+00:00', 1, 1)"
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


def make_record(db: Path, key: str = "REC-1") -> str:
    with open_uow(db) as uow:
        return handle_create_record(
            uow,
            CreateRecord(
                actor="user:t",
                source="test",
                scope="project:P123",
                record_type="core.Record",
                title=key,
                key=key,
            ),
        ).stream_id


def add_file(
    db: Path,
    record_id: str,
    slot: str | None,
    *,
    status: str = "available",
    superseded_by: str | None = None,
    file_id: str | None = None,
) -> None:
    params: dict[str, Any] = {
        "file_id": file_id or f"F-{record_id}-{slot}-{status}-{superseded_by}",
        "record_id": record_id,
        "slot": slot,
        "sha": "0" * 64,
        "status": status,
        "superseded_by": superseded_by,
    }
    with open_uow(db) as uow:
        uow.conn().execute(INSERT, params)


def names(missing: list[MissingFile]) -> list[str]:
    return [m.slot.name for m in missing]


def test_all_required_slots_are_missing_on_a_new_record(db: Path) -> None:
    rec = make_record(db)
    with open_uow(db, readonly=True) as uow:
        missing = missing_required_files(uow, rec, registry=REGISTRY)
    assert names(missing) == ["report", "certificate"]  # declaration order; photo is optional
    assert [(m.found, m.needed) for m in missing] == [(0, 1), (0, 1)]
    assert missing[0].slot == REPORT


def test_a_current_file_meets_the_slot(db: Path) -> None:
    rec = make_record(db)
    add_file(db, rec, "report")
    with open_uow(db, readonly=True) as uow:
        assert names(missing_required_files(uow, rec, registry=REGISTRY)) == ["certificate"]


@pytest.mark.parametrize("status", ["quarantined", "rejected"])
def test_a_file_that_has_not_passed_its_scan_does_not_count(db: Path, status: str) -> None:
    rec = make_record(db)
    add_file(db, rec, "report", status=status)
    with open_uow(db, readonly=True) as uow:
        assert "report" in names(missing_required_files(uow, rec, registry=REGISTRY))


def test_a_superseded_file_does_not_count_but_its_replacement_does(db: Path) -> None:
    rec = make_record(db)
    add_file(db, rec, "report", file_id="OLD", superseded_by="NEW")
    with open_uow(db, readonly=True) as uow:
        assert "report" in names(missing_required_files(uow, rec, registry=REGISTRY))
    add_file(db, rec, "report", file_id="NEW")
    with open_uow(db, readonly=True) as uow:
        assert "report" not in names(missing_required_files(uow, rec, registry=REGISTRY))


def test_files_of_another_record_or_slot_do_not_count(db: Path) -> None:
    rec, other = make_record(db, "REC-1"), make_record(db, "REC-2")
    add_file(db, other, "report")
    add_file(db, rec, "photo")
    add_file(db, rec, None)  # a generic attachment is in no slot
    with open_uow(db, readonly=True) as uow:
        assert names(missing_required_files(uow, rec, registry=REGISTRY)) == [
            "report",
            "certificate",
        ]


def test_by_state_keeps_only_slots_required_in_that_state(db: Path) -> None:
    rec = make_record(db)
    with open_uow(db, readonly=True) as uow:
        assert names(missing_required_files(uow, rec, registry=REGISTRY, by_state="Approved")) == [
            "report"
        ]
        assert names(missing_required_files(uow, rec, registry=REGISTRY, by_state="Closed")) == [
            "report",
            "certificate",
        ]
        assert missing_required_files(uow, rec, registry=REGISTRY, by_state="Draft") == []


def test_a_record_type_without_slots_misses_nothing(db: Path) -> None:
    rec = make_record(db)
    with open_uow(db, readonly=True) as uow:
        assert missing_required_files(uow, rec, registry=FileSlotRegistry()) == []


def test_an_unknown_record_raises(db: Path) -> None:
    with open_uow(db, readonly=True) as uow:
        with pytest.raises(RecordNotFoundError) as caught:
            missing_required_files(uow, "NOPE", registry=REGISTRY)
    assert str(caught.value) == "no record 'NOPE'"


def test_unmet_file_slots_checks_exactly_the_slots_it_is_given(db: Path) -> None:
    rec = make_record(db)
    add_file(db, rec, "photo")
    with open_uow(db, readonly=True) as uow:
        assert names(unmet_file_slots(uow, rec, [PHOTO, REPORT])) == ["report"]
        assert unmet_file_slots(uow, rec, []) == []
