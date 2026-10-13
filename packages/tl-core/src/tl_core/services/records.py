"""Record command handlers: the only business rules for records (brief 5.1, 5.2, 31).

``CreateRecord.record_type`` is ``core.Record`` or the name of an active extension type
(``<namespace>.<Name>``, brief 31, P0-I8): see ``tl_core.extypes``. A managed extension type takes
its initial values as psets; an object-backed one is created with its body by
``tl_core.extypes.body.create_extension_record``.

Each handler runs inside an already-entered unit of work and never commits. A failed check raises
a ServiceError (or the ledger's ConcurrencyError) before anything is appended, so nothing is
written.

A record of a module type (``tl_core.modules``, ADR-0010) is created by the module's own command
through ``create_module_record``: the same envelope event and the same key checks, plus the
module's typed events in the same append.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from tl_core.extypes.service import prepare_create, refuse_index_write
from tl_core.ledger import NewEvent
from tl_core.modules import is_module_record_type, require_generic
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import numbering_for
from tl_core.services.commands import (
    Command,
    CommandResult,
    CreateRecord,
    UpdateRecord,
    VoidRecord,
)
from tl_core.services.errors import (
    AlreadyVoidedError,
    DuplicateKeyError,
    NoChangesError,
    NoNumberingPatternError,
    RecordNotFoundError,
    RecordVoidedError,
    ReservedKeyError,
    UnsupportedFieldError,
    UnsupportedRecordTypeError,
)
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

RECORD_TYPE = "core.Record"
#: Characters a typed-in key of a generic record may not hold: module records use them to build
#: their own keys (``ISO-1234@A``, ``ISO-1234@A/pdf-1``, ``CL:Area@1.0.0``), and a generic record
#: must not be able to take such a key first.
RESERVED_KEY_CHARS = frozenset("@/")
_UPDATABLE_FIELDS = frozenset({"title", "description", "psets"})

_DUPLICATE_KEY_SQL = text("SELECT 1 FROM cur_core_record WHERE scope = :scope AND key = :key")
_LOAD_SQL = text(
    "SELECT scope, key, type, title, description, psets_json, voided "
    "FROM cur_core_record WHERE id = :id"
)


@dataclass(frozen=True)
class _StoredRecord:
    key: str | None
    type: str
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
        type=row.type,
        title=row.title,
        description=row.description,
        psets=json.loads(row.psets_json),
        voided=bool(row.voided),
    )


def _key_taken(uow: UnitOfWork, scope: str, key: str) -> bool:
    found = uow.conn().execute(_DUPLICATE_KEY_SQL, {"scope": scope, "key": key}).first()
    return found is not None


def handle_create_record(uow: UnitOfWork, cmd: CreateRecord) -> CommandResult:
    return create_record_internal(uow, cmd, allow_object_backed=False)


def create_record_internal(
    uow: UnitOfWork, cmd: CreateRecord, *, allow_object_backed: bool
) -> CommandResult:
    """``handle_create_record``, with the one switch ``create_extension_record`` needs.

    An object-backed type is refused (``BodyRequiredError``) unless ``allow_object_backed``: a
    record of such a type without a body would be a state the registry never wants to see.
    """
    extension = None
    if cmd.record_type != RECORD_TYPE:
        extension = prepare_create(
            uow,
            record_type=cmd.record_type,
            scope=cmd.scope,
            psets=cmd.psets,
            allow_object_backed=allow_object_backed,
        )
    if cmd.key is not None and RESERVED_KEY_CHARS & set(cmd.key):
        raise ReservedKeyError(
            f"key {cmd.key!r} holds '@' or '/', which module records use in their own keys"
        )
    stream_id = new_ulid()
    correlation_id = cmd.correlation_id or new_ulid()
    key = cmd.key
    if key is None:
        pattern = numbering_for(uow.conn()).find(cmd.scope, cmd.record_type)
        if pattern is None:
            raise NoNumberingPatternError(
                f"no key given and no numbering pattern for {cmd.record_type!r} in scope "
                f"{cmd.scope!r}; give a key"
            )
        allocation = allocate_key(
            uow,
            pattern=pattern,
            scope=cmd.scope,
            values=segment_values(pattern, cmd.scope, cmd.numbering),
            record_id=stream_id,
            record_type=cmd.record_type,
            actor=cmd.actor,
            source=cmd.source,
            correlation_id=correlation_id,
            causation_id=cmd.causation_id,
            is_taken=lambda candidate: _key_taken(uow, cmd.scope, candidate),
        )
        key = allocation.key
    elif _key_taken(uow, cmd.scope, key):
        raise DuplicateKeyError(f"key {key!r} is already used in scope {cmd.scope!r}")

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
                    "key": key,
                    "title": cmd.title,
                    "description": cmd.description,
                    # An extension type's initial values go in as Pset.ValuesSet events below, so
                    # they carry the conformance and schema hash like any later write.
                    "psets": cmd.psets if extension is None else {},
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=correlation_id,
        causation_id=cmd.causation_id,
    )
    events = list(result.events)
    version = result.new_version
    if extension is not None:
        from tl_core.services.psets import SetPsetValues, handle_set_pset_values

        for pset, values in cmd.psets.items():
            written = handle_set_pset_values(
                uow,
                SetPsetValues(
                    actor=cmd.actor,
                    source=cmd.source,
                    scope=cmd.scope,
                    correlation_id=correlation_id,
                    stream_id=stream_id,
                    expected_version=version,
                    pset=pset,
                    layer="standard",
                    values=values,
                ),
            )
            events.extend(written.events)
            version = written.version
    return CommandResult(
        stream_id=stream_id,
        key=key,
        version=version,
        events=events,
    )


def create_module_record(
    uow: UnitOfWork,
    cmd: Command,
    *,
    record_type: str,
    title: str,
    key: str | None,
    description: str | None = None,
    extra_events: Sequence[NewEvent] = (),
    numbering: dict[str, str] | None = None,
    composed_key: bool = False,
) -> CommandResult:
    """Create a record of a module type: ``Record.Created`` then the module's own events.

    ``record_type`` must be provided by an installed module (``UnsupportedRecordTypeError``
    otherwise). The key is checked like any record's (``DuplicateKeyError``); with no key the
    numbering service allocates one from the pattern for the type and ``numbering`` supplies the
    pattern's other fields. ``extra_events`` are appended in the same append, after the envelope
    event, so the module's projectors see the row ``RecordProjector`` just made. The record has no
    property-set values yet; write them with ``SetPsetValues`` in the same unit of work.

    A key a caller typed in (a document number, a tag number) may not hold ``@`` or ``/``
    (``ReservedKeyError``): modules build their own keys with them (``ISO-1234@B``), and a typed
    key would squat one. A module that builds the key itself passes ``composed_key=True``.
    """
    if not is_module_record_type(record_type):
        raise UnsupportedRecordTypeError(
            f"record type {record_type!r} is not provided by an installed module"
        )
    if key is not None and not composed_key and RESERVED_KEY_CHARS & set(key):
        raise ReservedKeyError(
            f"key {key!r} holds '@' or '/', which module records use in their own keys"
        )
    stream_id = new_ulid()
    correlation_id = cmd.correlation_id or new_ulid()
    if key is None:
        pattern = numbering_for(uow.conn()).find(cmd.scope, record_type)
        if pattern is None:
            raise NoNumberingPatternError(
                f"no key given and no numbering pattern for {record_type!r} in scope "
                f"{cmd.scope!r}; give a key"
            )
        key = allocate_key(
            uow,
            pattern=pattern,
            scope=cmd.scope,
            values=segment_values(pattern, cmd.scope, numbering),
            record_id=stream_id,
            record_type=record_type,
            actor=cmd.actor,
            source=cmd.source,
            correlation_id=correlation_id,
            causation_id=cmd.causation_id,
            is_taken=lambda candidate: _key_taken(uow, cmd.scope, candidate),
        ).key
    elif _key_taken(uow, cmd.scope, key):
        raise DuplicateKeyError(f"key {key!r} is already used in scope {cmd.scope!r}")
    result = uow.append(
        stream_id=stream_id,
        stream_type=record_type,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={
                    "record_type": record_type,
                    "key": key,
                    "title": title,
                    "description": description,
                    "psets": {},
                },
            ),
            *extra_events,
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=correlation_id,
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=stream_id, key=key, version=result.new_version, events=result.events
    )


def handle_update_record(uow: UnitOfWork, cmd: UpdateRecord) -> CommandResult:
    stored = _load_record(uow, cmd.scope, cmd.stream_id)
    require_generic(uow.conn(), stored.type, "UpdateRecord", cmd.stream_id)
    if stored.voided:
        raise RecordVoidedError(f"record {cmd.stream_id!r} is voided and cannot be updated")
    if "psets" in cmd.changes:
        refuse_index_write(uow, stored.type)
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
    require_generic(uow.conn(), stored.type, "VoidRecord", cmd.stream_id)
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
