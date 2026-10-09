"""Record command handlers against a real SQLite ledger (P0-I1-T09)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.ledger import ConcurrencyError, Event
from tl_core.services.commands import (
    CommandResult,
    CreateRecord,
    UpdateRecord,
    VoidRecord,
)
from tl_core.services.errors import (
    AlreadyVoidedError,
    DuplicateKeyError,
    KeyRequiredError,
    NoChangesError,
    RecordNotFoundError,
    RecordVoidedError,
    UnsupportedFieldError,
    UnsupportedRecordTypeError,
)
from tl_core.services.records import (
    handle_create_record,
    handle_update_record,
    handle_void_record,
)
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

Handler = Callable[[UnitOfWork, Any], CommandResult]
Run = Callable[[Handler, Any], CommandResult]


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


@pytest.fixture
def run(db: Path) -> Run:
    def _run(handler: Handler, cmd: Any) -> CommandResult:
        with open_uow(db) as uow:
            return handler(uow, cmd)

    return _run


def create_cmd(**overrides: Any) -> CreateRecord:
    fields: dict[str, Any] = {
        "actor": "user:u-1",
        "source": "test",
        "scope": "company",
        "record_type": "core.Record",
        "title": "Pour slab",
        "description": "Level 2",
        "key": "REC-1",
        "psets": {"discipline": "structural"},
    }
    fields.update(overrides)
    return CreateRecord(**fields)


def update_cmd(
    stream_id: str, expected_version: int, changes: dict[str, Any], **kw: Any
) -> UpdateRecord:
    fields: dict[str, Any] = {
        "actor": "user:u-1",
        "source": "test",
        "scope": "company",
        "stream_id": stream_id,
        "expected_version": expected_version,
        "changes": changes,
    }
    fields.update(kw)
    return UpdateRecord(**fields)


def void_cmd(stream_id: str, expected_version: int, reason: str = "entered in error") -> VoidRecord:
    return VoidRecord(
        actor="user:u-1",
        source="test",
        scope="company",
        stream_id=stream_id,
        expected_version=expected_version,
        reason=reason,
    )


def read_row(db: Path, stream_id: str) -> dict[str, Any] | None:
    with open_uow(db, readonly=True) as uow:
        row = (
            uow.conn()
            .execute(
                text(
                    "SELECT id, key, scope, title, description, psets_json, voided, version "
                    "FROM cur_core_record WHERE id = :id"
                ),
                {"id": stream_id},
            )
            .mappings()
            .first()
        )
        return None if row is None else dict(row)


def count_rows(db: Path) -> int:
    with open_uow(db, readonly=True) as uow:
        value: int = uow.conn().execute(text("SELECT COUNT(*) FROM cur_core_record")).scalar_one()
        return value


def read_events(db: Path, stream_id: str) -> list[Event]:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.read_stream(stream_id)


def head_seq(db: Path) -> int:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.head_seq()


# --- create ---------------------------------------------------------------------------------------


def test_create_emits_one_record_created_with_exact_payload(db: Path, run: Run) -> None:
    result = run(handle_create_record, create_cmd())

    events = read_events(db, result.stream_id)
    assert len(events) == 1
    assert events[0].event_type == "Record.Created"
    assert events[0].payload == {
        "record_type": "core.Record",
        "key": "REC-1",
        "title": "Pour slab",
        "description": "Level 2",
        "psets": {"discipline": "structural"},
    }
    assert events[0].actor == "user:u-1"
    assert events[0].source == "test"


def test_create_writes_row_at_version_one(db: Path, run: Run) -> None:
    result = run(handle_create_record, create_cmd())

    row = read_row(db, result.stream_id)
    assert row is not None
    assert row["title"] == "Pour slab"
    assert row["key"] == "REC-1"
    assert row["scope"] == "company"
    assert row["version"] == 1
    assert row["voided"] == 0


def test_create_result_carries_stream_id_key_and_version(run: Run) -> None:
    result = run(handle_create_record, create_cmd())

    assert len(result.stream_id) == 26
    assert result.key == "REC-1"
    assert result.version == 1
    assert len(result.events) == 1


def test_create_keeps_passed_correlation_id(db: Path, run: Run) -> None:
    correlation = new_ulid()
    result = run(
        handle_create_record, create_cmd(correlation_id=correlation, causation_id="cause-9")
    )

    event = read_events(db, result.stream_id)[0]
    assert event.correlation_id == correlation
    assert event.causation_id == "cause-9"


def test_create_generates_correlation_id_when_absent(db: Path, run: Run) -> None:
    result = run(handle_create_record, create_cmd())

    correlation = read_events(db, result.stream_id)[0].correlation_id
    assert len(correlation) == 26
    assert correlation != result.stream_id


# --- create failures ------------------------------------------------------------------------------


def test_create_without_key_raises_key_required(db: Path, run: Run) -> None:
    with pytest.raises(KeyRequiredError):
        run(handle_create_record, create_cmd(key=None))
    assert count_rows(db) == 0
    assert head_seq(db) == 0


def test_duplicate_key_in_same_scope_raises_and_first_record_is_unchanged(
    db: Path, run: Run
) -> None:
    first = run(handle_create_record, create_cmd(title="First"))
    seq_before = head_seq(db)

    with pytest.raises(DuplicateKeyError):
        run(handle_create_record, create_cmd(title="Second"))

    assert head_seq(db) == seq_before
    assert count_rows(db) == 1
    row = read_row(db, first.stream_id)
    assert row is not None
    assert row["title"] == "First"
    assert row["version"] == 1


def test_same_key_in_another_scope_succeeds(db: Path, run: Run) -> None:
    run(handle_create_record, create_cmd(scope="company"))

    other = run(handle_create_record, create_cmd(scope="project:p-1"))

    row = read_row(db, other.stream_id)
    assert row is not None
    assert row["scope"] == "project:p-1"
    assert count_rows(db) == 2


def test_unsupported_record_type_raises(db: Path, run: Run) -> None:
    with pytest.raises(UnsupportedRecordTypeError):
        run(handle_create_record, create_cmd(record_type="qc.Inspection"))
    assert count_rows(db) == 0
    assert head_seq(db) == 0


def test_empty_title_is_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        create_cmd(title="")


def test_bad_scope_is_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        create_cmd(scope="portfolio")
    with pytest.raises(ValidationError):
        create_cmd(scope="project:")


# --- update ---------------------------------------------------------------------------------------


def test_update_title_and_description_emits_updated_and_bumps_version(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd(title="Old", description="old text"))

    result = run(
        handle_update_record,
        update_cmd(created.stream_id, 1, {"title": "New", "description": "new text"}),
    )

    assert result.version == 2
    assert result.key == "REC-1"
    update_event = read_events(db, created.stream_id)[-1]
    assert update_event.event_type == "Record.Updated"
    assert update_event.payload == {
        "changes": {"title": ["Old", "New"], "description": ["old text", "new text"]}
    }
    row = read_row(db, created.stream_id)
    assert row is not None
    assert row["title"] == "New"
    assert row["description"] == "new text"
    assert row["version"] == 2


def test_update_leaves_unchanged_fields_out_of_changes(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd(title="Old", description="same"))

    run(
        handle_update_record,
        update_cmd(created.stream_id, 1, {"title": "New", "description": "same"}),
    )

    update_event = read_events(db, created.stream_id)[-1]
    assert update_event.payload == {"changes": {"title": ["Old", "New"]}}


def test_update_psets_emits_changed_mapping(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd(psets={"discipline": "structural"}))

    run(
        handle_update_record,
        update_cmd(created.stream_id, 1, {"psets": {"discipline": "mep"}}),
    )

    update_event = read_events(db, created.stream_id)[-1]
    assert update_event.payload == {
        "changes": {"psets": [{"discipline": "structural"}, {"discipline": "mep"}]}
    }
    row = read_row(db, created.stream_id)
    assert row is not None
    assert json.loads(row["psets_json"]) == {"discipline": "mep"}


def test_update_psets_compares_as_dicts_not_key_order(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd(psets={"a": 1, "b": 2}))

    with pytest.raises(NoChangesError):
        run(handle_update_record, update_cmd(created.stream_id, 1, {"psets": {"b": 2, "a": 1}}))


def test_update_with_no_differences_raises_no_changes(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd(title="Same"))
    seq_before = head_seq(db)

    with pytest.raises(NoChangesError):
        run(handle_update_record, update_cmd(created.stream_id, 1, {"title": "Same"}))

    assert head_seq(db) == seq_before


def test_update_of_unsupported_field_raises(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd())
    seq_before = head_seq(db)

    with pytest.raises(UnsupportedFieldError):
        run(handle_update_record, update_cmd(created.stream_id, 1, {"status": "closed"}))

    assert head_seq(db) == seq_before


def test_stale_expected_version_raises_concurrency_and_writes_nothing(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd(title="Original"))
    seq_before = head_seq(db)

    with pytest.raises(ConcurrencyError):
        run(handle_update_record, update_cmd(created.stream_id, 0, {"title": "Stale"}))

    assert head_seq(db) == seq_before
    row = read_row(db, created.stream_id)
    assert row is not None
    assert row["title"] == "Original"
    assert row["version"] == 1


def test_update_of_unknown_stream_raises_not_found(run: Run) -> None:
    with pytest.raises(RecordNotFoundError):
        run(handle_update_record, update_cmd(new_ulid(), 1, {"title": "X"}))


def test_update_of_stream_in_another_scope_raises_not_found(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd(scope="company"))
    seq_before = head_seq(db)

    with pytest.raises(RecordNotFoundError):
        run(
            handle_update_record,
            update_cmd(created.stream_id, 1, {"title": "X"}, scope="project:p-1"),
        )

    assert head_seq(db) == seq_before


def test_update_of_voided_record_raises_voided(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd())
    run(handle_void_record, void_cmd(created.stream_id, 1))
    seq_before = head_seq(db)

    with pytest.raises(RecordVoidedError):
        run(handle_update_record, update_cmd(created.stream_id, 2, {"title": "After void"}))

    assert head_seq(db) == seq_before


# --- void -----------------------------------------------------------------------------------------


def test_void_emits_voided_and_keeps_the_row(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd())

    result = run(handle_void_record, void_cmd(created.stream_id, 1, reason="duplicate entry"))

    assert result.version == 2
    void_event = read_events(db, created.stream_id)[-1]
    assert void_event.event_type == "Record.Voided"
    assert void_event.payload == {"reason": "duplicate entry"}
    row = read_row(db, created.stream_id)
    assert row is not None
    assert row["voided"] == 1
    assert row["version"] == 2


def test_void_with_blank_reason_is_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        void_cmd(new_ulid(), 1, reason="   ")


def test_voiding_twice_raises_already_voided(db: Path, run: Run) -> None:
    created = run(handle_create_record, create_cmd())
    run(handle_void_record, void_cmd(created.stream_id, 1))
    seq_before = head_seq(db)

    with pytest.raises(AlreadyVoidedError):
        run(handle_void_record, void_cmd(created.stream_id, 2))

    assert head_seq(db) == seq_before


# --- atomicity ------------------------------------------------------------------------------------


def test_failed_handler_leaves_ledger_and_table_unchanged(db: Path, run: Run) -> None:
    run(handle_create_record, create_cmd())
    seq_before = head_seq(db)
    rows_before = count_rows(db)

    with pytest.raises(DuplicateKeyError):
        run(handle_create_record, create_cmd(title="Duplicate"))

    assert head_seq(db) == seq_before
    assert count_rows(db) == rows_before


def test_error_after_a_write_in_the_same_transaction_rolls_back_that_write(db: Path) -> None:
    seq_before = head_seq(db)

    with pytest.raises(DuplicateKeyError), open_uow(db) as uow:
        handle_create_record(uow, create_cmd(key="SAME"))
        handle_create_record(uow, create_cmd(key="SAME", title="Second"))

    assert head_seq(db) == seq_before
    assert count_rows(db) == 0
