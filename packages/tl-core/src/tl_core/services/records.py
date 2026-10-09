"""Record command handlers: the only business rules for core.Record (brief 5.1, 5.2).

Each handler runs inside an already-entered unit of work and never commits. A failed check raises
a ServiceError (or the ledger's ConcurrencyError) before anything is appended, so nothing is
written.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from tl_core.ledger import NewEvent
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord, VoidRecord
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
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

RECORD_TYPE = "core.Record"
_UPDATABLE_FIELDS = frozenset({"title", "description", "psets"})

_DUPLICATE_KEY_SQL = text("SELECT 1 FROM cur_core_record WHERE scope = :scope AND key = :key")
_LOAD_SQL = text(
    "SELECT scope, key, title, description, psets_json, voided FROM cur_core_record WHERE id = :id"
)


@dataclass(frozen=True)
class _StoredRecord:
    key: str | None
    title: str
    description: str | None
    psets: dict[str, Any]
    voided: bool


def _load_record(uow: UnitOfWork, scope: str, stream_id: str) -> _StoredRecord:
    row = uow.conn().execute(_LOAD_SQL, {"id": stream_id}).first()
    if row is None or row.scope != scope:
        raise RecordNotFoundError(f"no record {stream_id!r} in scope {scope!r}")
    return _StoredRecord(
        key=row.key,
        title=row.title,
        description=row.description,
        psets=json.loads(row.psets_json),
        voided=bool(row.voided),
    )


def handle_create_record(uow: UnitOfWork, cmd: CreateRecord) -> CommandResult:
    if cmd.record_type != RECORD_TYPE:
        raise UnsupportedRecordTypeError(
            f"record type {cmd.record_type!r} is not supported; only {RECORD_TYPE!r} is"
        )
    if cmd.key is None:
        raise KeyRequiredError("a key is required to create a record")
    duplicate = uow.conn().execute(_DUPLICATE_KEY_SQL, {"scope": cmd.scope, "key": cmd.key}).first()
    if duplicate is not None:
        raise DuplicateKeyError(f"key {cmd.key!r} is already used in scope {cmd.scope!r}")

    stream_id = new_ulid()
    correlation_id = cmd.correlation_id or new_ulid()
    result = uow.append(
        stream_id=stream_id,
        stream_type=cmd.record_type,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={
                    "record_type": cmd.record_type,
                    "key": cmd.key,
                    "title": cmd.title,
                    "description": cmd.description,
                    "psets": cmd.psets,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=correlation_id,
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=stream_id,
        key=cmd.key,
        version=result.new_version,
        events=result.events,
    )


def handle_update_record(uow: UnitOfWork, cmd: UpdateRecord) -> CommandResult:
    stored = _load_record(uow, cmd.scope, cmd.stream_id)
    if stored.voided:
        raise RecordVoidedError(f"record {cmd.stream_id!r} is voided and cannot be updated")
    unsupported = sorted(set(cmd.changes) - _UPDATABLE_FIELDS)
    if unsupported:
        raise UnsupportedFieldError(
            f"fields {', '.join(unsupported)} cannot be updated; "
            f"only {', '.join(sorted(_UPDATABLE_FIELDS))} can"
        )

    current: dict[str, Any] = {
        "title": stored.title,
        "description": stored.description,
        "psets": stored.psets,
    }
    changes: dict[str, list[Any]] = {}
    for field, new_value in cmd.changes.items():
        old_value = current[field]
        if new_value != old_value:
            changes[field] = [old_value, new_value]
    if not changes:
        raise NoChangesError(f"no field of record {cmd.stream_id!r} differs from the request")

    result = uow.append(
        stream_id=cmd.stream_id,
        stream_type=RECORD_TYPE,
        scope=cmd.scope,
        expected_version=cmd.expected_version,
        events=[NewEvent(event_type="Record.Updated", payload={"changes": changes})],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.stream_id,
        key=stored.key,
        version=result.new_version,
        events=result.events,
    )


def handle_void_record(uow: UnitOfWork, cmd: VoidRecord) -> CommandResult:
    stored = _load_record(uow, cmd.scope, cmd.stream_id)
    if stored.voided:
        raise AlreadyVoidedError(f"record {cmd.stream_id!r} is already voided")

    result = uow.append(
        stream_id=cmd.stream_id,
        stream_type=RECORD_TYPE,
        scope=cmd.scope,
        expected_version=cmd.expected_version,
        events=[NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.stream_id,
        key=stored.key,
        version=result.new_version,
        events=result.events,
    )
