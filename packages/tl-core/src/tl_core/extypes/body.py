"""The object-backed body store: validate, store once by hash, verify on read (brief 31.2, 31.4).

An object-backed record keeps its body in the object store at
``records/<type>/<id>/<sha256>.json`` as canonical JSON (FANOUT D10). The ledger holds only
``Record.BodyStored`` (a pointer and the hash of the body it replaces), and the index fields are
copied into the type's pset in the same unit of work, so the query language filters them.

* ``store_body`` validates the body against the compiled class, puts the object (the key holds the
  hash, so an object is written once and a new body is a new object), appends the event and copies
  the index fields. Storing the same body again appends nothing; it re-puts the object, which heals
  a lost or damaged one, and lifts a quarantine.
* ``load_body`` reads the object, recomputes its hash and compares it with the pointer. A mismatch,
  or a missing object, raises ``BodyHashMismatchError`` and never returns the body (brief 31.4).
* ``read_body`` is ``load_body`` for callers that hold a unit-of-work *factory*: on a mismatch it
  records the record in ``tl_body_quarantine`` in a fresh unit of work (the failing read's own
  transaction ends in rollback) and then raises. Later reads raise ``BodyQuarantinedError`` without
  touching the object until ``recheck_body`` finds it sound or a new body is stored.
* ``create_extension_record`` creates an object-backed record and stores its first body in one unit
  of work.

Reads of ``tl_body_quarantine`` and the pointer table need only a connection, so listing works
inside any unit of work.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import Connection, text
from tl_schema.effective import canonical_dump

from tl_core.extypes.compile import body_issues
from tl_core.extypes.errors import (
    BodyHashMismatchError,
    BodyNotAllowedError,
    BodyNotFoundError,
    BodyQuarantinedError,
    BodyValidationError,
)
from tl_core.extypes.registry import UowFactory
from tl_core.extypes.service import BodyStoredOut, lookup_type, prepare_create
from tl_core.extypes.types import RECORD_BODY_STORED, BodyPointer
from tl_core.files.types import ObjectNotFound, ObjectStore
from tl_core.ledger import Event, NewEvent, iso_utc
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.errors import RecordNotFoundError, RecordVoidedError
from tl_core.services.psets import SetPsetValues, apply_index_values
from tl_core.services.records import create_record_internal
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

#: A body larger than this is refused (the object store is not a file share).
MAX_BODY_BYTES = 1024 * 1024

_RECORD = text(
    "SELECT id, scope, key, type, version, voided, psets_json FROM cur_core_record WHERE id = :id"
)
_POINTER = text(
    "SELECT record_id, scope, type_name, uri, hash, body_size, schema_hash, body_versions "
    "FROM cur_core_record_body WHERE record_id = :id"
)
_QUARANTINE = text(
    "SELECT record_id, scope, type_name, uri, expected_hash, actual_hash, reason, detected_at "
    "FROM tl_body_quarantine WHERE record_id = :id"
)
_QUARANTINE_ALL = text(
    "SELECT record_id, scope, type_name, uri, expected_hash, actual_hash, reason, detected_at "
    "FROM tl_body_quarantine ORDER BY detected_at, record_id"
)
_QUARANTINE_DELETE = text("DELETE FROM tl_body_quarantine WHERE record_id = :id")
_QUARANTINE_INSERT = text(
    "INSERT INTO tl_body_quarantine (record_id, scope, type_name, uri, expected_hash, "
    "actual_hash, reason, detected_at) VALUES (:record_id, :scope, :type_name, :uri, "
    ":expected_hash, :actual_hash, :reason, :detected_at)"
)


class BodyQuarantineEntry(BaseModel):
    record_id: str
    scope: str
    type_name: str
    uri: str
    expected_hash: str
    actual_hash: str | None
    reason: str
    detected_at: str


def body_key(type_name: str, record_id: str, sha256: str) -> str:
    """``records/<type>/<id>/<sha256>.json`` (brief 31.2)."""
    return f"records/{type_name}/{record_id}/{sha256}.json"


def canonical_body(body: dict[str, Any]) -> bytes:
    """The bytes that are stored and hashed: canonical JSON (sorted keys, no whitespace)."""
    return canonical_dump(body).encode("utf-8")


# --- storing --------------------------------------------------------------------------------


def _store(
    uow: UnitOfWork,
    store: ObjectStore,
    *,
    stream_id: str,
    body: dict[str, Any],
    actor: str,
    source: str,
    expected_version: int | None,
) -> tuple[BodyPointer, list[Event], int]:
    row = uow.conn().execute(_RECORD, {"id": stream_id}).first()
    if row is None:
        raise RecordNotFoundError(f"no record {stream_id!r}")
    if row.voided:
        raise RecordVoidedError(f"record {stream_id!r} is voided and cannot be updated")
    resolved = lookup_type(uow, row.type)
    if resolved is None or resolved.storage_mode != "object-backed":
        raise BodyNotAllowedError(f"{row.type} is not an object-backed type: it has no body")
    if expected_version is not None and expected_version != int(row.version):
        from tl_core.ledger import ConcurrencyError

        raise ConcurrencyError(f"expected version {expected_version}, record is at {row.version}")
    compiled = resolved.compiled
    issues = body_issues(compiled, body)
    if issues:
        raise BodyValidationError(f"the body is not a valid {compiled.type_name}", issues)
    data = canonical_body(body)
    if len(data) > MAX_BODY_BYTES:
        raise BodyValidationError(
            f"the body is {len(data)} bytes; the limit is {MAX_BODY_BYTES}",
            [f"(body): larger than {MAX_BODY_BYTES} bytes"],
        )
    digest = hashlib.sha256(data).hexdigest()
    key = body_key(compiled.type_name, stream_id, digest)
    store.put(key, io.BytesIO(data), size=len(data), sha256=digest, content_type="application/json")
    pointer = BodyPointer(uri=key, hash=digest, size=len(data), schema_hash=compiled.schema_hash())
    uow.conn().execute(_QUARANTINE_DELETE, {"id": stream_id})

    previous = uow.conn().execute(_POINTER, {"id": stream_id}).first()
    previous_hash = None if previous is None else str(previous.hash)
    if previous_hash == digest:
        return pointer, [], int(row.version)

    events: list[Event] = []
    result = uow.append(
        stream_id=stream_id,
        stream_type=row.type,
        scope=row.scope,
        expected_version=int(row.version),
        events=[
            NewEvent(
                event_type=RECORD_BODY_STORED,
                payload={
                    "stream_id": stream_id,
                    "pointer": pointer.model_dump(mode="json"),
                    "previous_hash": previous_hash,
                },
            )
        ],
        actor=actor,
        source=source,
        correlation_id=new_ulid(),
    )
    events.extend(result.events)
    version = result.new_version

    current: dict[str, Any] = json.loads(row.psets_json).get(compiled.pset, {})
    changed: dict[str, Any] = {}
    for name in compiled.index_fields:
        if body.get(name) != current.get(name):
            changed[name] = body.get(name)
    if changed:
        done = apply_index_values(
            uow,
            SetPsetValues(
                actor=actor,
                source=source,
                scope=row.scope,
                stream_id=stream_id,
                expected_version=version,
                pset=compiled.pset,
                layer="standard",
                values=changed,
            ),
        )
        events.extend(done.events)
        version = done.version
    return pointer, events, version


def store_body(
    uow: UnitOfWork,
    store: ObjectStore,
    *,
    stream_id: str,
    body: dict[str, Any],
    actor: str,
    source: str,
    expected_version: int | None = None,
) -> BodyPointer:
    """Validate and store a body for an object-backed record; see the module docstring.

    ``expected_version`` is an optional addition to the frozen signature: when given and the
    record has moved on, ``ConcurrencyError`` is raised (the API passes the version the editor saw).
    Raises ``BodyValidationError`` (with ``issues``), ``BodyNotAllowedError`` (not an object-backed
    record), ``RecordNotFoundError`` and ``RecordVoidedError``.
    """
    pointer, _, _ = _store(
        uow,
        store,
        stream_id=stream_id,
        body=body,
        actor=actor,
        source=source,
        expected_version=expected_version,
    )
    return pointer


def store_record_body(
    uow: UnitOfWork,
    store: ObjectStore,
    *,
    record_id: str,
    scope: str,
    body: dict[str, Any],
    actor: str,
    source: str,
    expected_version: int | None = None,
) -> BodyStoredOut:
    """``store_body`` for a caller that names the scope: the pointer and the version after.

    The record must be in ``scope`` (else ``RecordNotFoundError``, the same answer as an unknown
    record, so a scope cannot be probed). The embedded client and the API's
    ``PUT /records/{id}/body`` both call this one function. Other errors are those of
    ``store_body``: ``BodyValidationError``, ``BodyNotAllowedError`` (not an object-backed
    record), ``RecordVoidedError`` and ``ConcurrencyError``.
    """
    found = uow.conn().execute(_RECORD, {"id": record_id}).first()
    if found is None or found.scope != scope:
        raise RecordNotFoundError(f"no record {record_id!r} in scope {scope!r}")
    pointer = store_body(
        uow,
        store,
        stream_id=record_id,
        body=body,
        actor=actor,
        source=source,
        expected_version=expected_version,
    )
    after = uow.conn().execute(_RECORD, {"id": record_id}).one()
    return BodyStoredOut(pointer=pointer, version=int(after.version))


def create_extension_record(
    uow: UnitOfWork, store: ObjectStore, cmd: CreateRecord, body: dict[str, Any]
) -> CommandResult:
    """Create an object-backed record and store its first body in the one unit of work.

    ``cmd.psets`` must be empty: the index fields come from the body. A body that does not
    validate is refused before anything is written.
    """
    resolved = prepare_create(
        uow,
        record_type=cmd.record_type,
        scope=cmd.scope,
        psets=cmd.psets,
        allow_object_backed=True,
    )
    if resolved.storage_mode != "object-backed":
        raise BodyNotAllowedError(f"{cmd.record_type} is managed: its values are psets, not a body")
    issues = body_issues(resolved.compiled, body)
    if issues:
        raise BodyValidationError(f"the body is not a valid {cmd.record_type}", issues)
    created = create_record_internal(uow, cmd, allow_object_backed=True)
    pointer, events, version = _store(
        uow,
        store,
        stream_id=created.stream_id,
        body=body,
        actor=cmd.actor,
        source=cmd.source,
        expected_version=created.version,
    )
    del pointer
    return CommandResult(
        stream_id=created.stream_id,
        key=created.key,
        version=version,
        events=[*created.events, *events],
    )


# --- reading --------------------------------------------------------------------------------


def body_pointer(conn: Connection, stream_id: str) -> BodyPointer | None:
    """The current pointer of a record's body, or ``None`` when it has none."""
    row = conn.execute(_POINTER, {"id": stream_id}).first()
    if row is None:
        return None
    return BodyPointer(
        uri=row.uri, hash=row.hash, size=int(row.body_size), schema_hash=row.schema_hash
    )


def load_body(
    conn: Connection,
    store: ObjectStore,
    *,
    stream_id: str,
    ignore_quarantine: bool = False,
) -> dict[str, Any]:
    """The verified body of a record. Never returns bytes whose hash differs from the pointer.

    Raises ``BodyNotFoundError`` (no pointer), ``BodyQuarantinedError`` (an earlier read failed and
    nothing has fixed it since; ``ignore_quarantine`` skips that check, for ``recheck_body``) and
    ``BodyHashMismatchError`` (object missing, wrong size, or wrong hash). This function only
    reads; ``read_body`` also records the quarantine.
    """
    row = conn.execute(_POINTER, {"id": stream_id}).first()
    if row is None:
        raise BodyNotFoundError(f"record {stream_id!r} has no stored body")
    if not ignore_quarantine:
        held = conn.execute(_QUARANTINE, {"id": stream_id}).first()
        if held is not None and held.expected_hash == row.hash:
            raise BodyQuarantinedError(
                f"the body of {stream_id} failed verification ({held.reason}); "
                "store it again or run `tl types quarantine recheck`"
            )
    uri, expected, size = str(row.uri), str(row.hash), int(row.body_size)

    def mismatch(reason: str, actual: str | None) -> BodyHashMismatchError:
        return BodyHashMismatchError(
            f"the stored body of {stream_id} does not match its recorded hash: {reason}",
            record_id=stream_id,
            uri=uri,
            expected=expected,
            actual=actual,
        )

    try:
        handle = store.get(uri)
    except ObjectNotFound:
        raise mismatch("object missing", None) from None
    with handle:
        data = handle.read(size + 1)
    actual = hashlib.sha256(data).hexdigest()
    if len(data) != size:
        raise mismatch(f"{len(data)} bytes found, {size} recorded", actual)
    if actual != expected:
        raise mismatch("hash differs", actual)
    loaded: Any = json.loads(data)
    if not isinstance(loaded, dict):
        raise mismatch("not a JSON object", actual)
    return dict(cast("dict[str, Any]", loaded))


def _record_quarantine(factory: UowFactory, error: BodyHashMismatchError) -> None:
    with factory(readonly=False) as uow:
        pointer = uow.conn().execute(_POINTER, {"id": error.record_id}).first()
        if pointer is None or str(pointer.hash) != error.expected:
            return  # a newer body was stored meanwhile: not this one's failure
        uow.conn().execute(_QUARANTINE_DELETE, {"id": error.record_id})
        uow.conn().execute(
            _QUARANTINE_INSERT,
            {
                "record_id": error.record_id,
                "scope": pointer.scope,
                "type_name": pointer.type_name,
                "uri": error.uri,
                "expected_hash": error.expected,
                "actual_hash": error.actual,
                "reason": "object missing" if error.actual is None else "hash mismatch",
                "detected_at": iso_utc(utcnow()),
            },
        )


def read_body(factory: UowFactory, store: ObjectStore, *, stream_id: str) -> dict[str, Any]:
    """``load_body`` that quarantines the record when the object fails verification."""
    try:
        with factory(readonly=True) as uow:
            return load_body(uow.conn(), store, stream_id=stream_id)
    except BodyHashMismatchError as error:
        _record_quarantine(factory, error)
        raise


def recheck_body(factory: UowFactory, store: ObjectStore, *, stream_id: str) -> bool:
    """Verify a quarantined body again; lift the quarantine and return ``True`` when it is sound.

    Returns ``False`` (quarantine kept, refreshed) when it still fails. A record that is not
    quarantined is simply verified.
    """
    try:
        with factory(readonly=True) as uow:
            load_body(uow.conn(), store, stream_id=stream_id, ignore_quarantine=True)
    except BodyHashMismatchError as error:
        _record_quarantine(factory, error)
        return False
    with factory(readonly=False) as uow:
        uow.conn().execute(_QUARANTINE_DELETE, {"id": stream_id})
    return True


def list_body_quarantine(conn: Connection) -> list[BodyQuarantineEntry]:
    """Records whose stored body failed verification, oldest first."""
    return [
        BodyQuarantineEntry(
            record_id=row.record_id,
            scope=row.scope,
            type_name=row.type_name,
            uri=row.uri,
            expected_hash=row.expected_hash,
            actual_hash=row.actual_hash,
            reason=row.reason,
            detected_at=str(row.detected_at),
        )
        for row in conn.execute(_QUARANTINE_ALL)
    ]
