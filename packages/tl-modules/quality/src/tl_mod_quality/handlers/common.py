"""Helpers the punch handlers share: scope, versions, appends, the viewer-filtered record lookup.

Every id a command is given goes through ``load_record`` (``require_visible`` first, ADR-0016
section 5): a record the viewer may not read, one in another project, one of another type and one
that does not exist all answer ``RecordNotFoundError`` with the same words.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from tl_core import confidentiality
from tl_core.ledger import AppendResult, NewEvent, iso_utc
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_quality.errors import PunchRuleError, QualityScopeError, StaleVersionError
from tl_mod_quality.names import FEED_NONE

MSG_UNKNOWN = "no record with that id"
MSG_STALE = "the record changed since it was read"
MSG_FUTURE = "the time is in the future"
MSG_BEFORE_RAISED = "the time is before the day the punch item was raised"
_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")
_STATUS_SQL = text("SELECT status FROM cur_core_record WHERE id = :id")
_RECORD_SQL = text(
    "SELECT id, key, title, description, scope, type, voided, created_at "
    "FROM cur_core_record WHERE id = :id"
)


@dataclass(frozen=True)
class RecordRef:
    id: str
    key: str | None
    title: str
    description: str | None
    record_type: str
    created_on: str


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise QualityScopeError(f"punch items belong to a project; the scope is {cmd.scope!r}")


def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    if cmd.correlation_id is not None:
        return cmd
    return cmd.model_copy(update={"correlation_id": new_ulid()})


def version_of(uow: UnitOfWork, record_id: str) -> int:
    found = uow.conn().execute(_VERSION_SQL, {"id": record_id}).scalar_one_or_none()
    if found is None:
        raise LookupError(f"no record {record_id!r}")
    return int(found)


def require_version(uow: UnitOfWork, record_id: str, expected: int | None) -> None:
    """``StaleVersionError`` unless the record is at ``expected`` (``None`` skips the check)."""
    if expected is not None and version_of(uow, record_id) != expected:
        raise StaleVersionError(MSG_STALE)


def record_state(uow: UnitOfWork, record_id: str, initial: str) -> str:
    found = uow.conn().execute(_STATUS_SQL, {"id": record_id}).scalar_one_or_none()
    return initial if found is None else str(found)


def append(
    uow: UnitOfWork, cmd: Command, stream_id: str, stream_type: str, events: list[NewEvent]
) -> AppendResult:
    """Append ``events`` to a stream at its current version."""
    return uow.append(
        stream_id=stream_id,
        stream_type=stream_type,
        scope=cmd.scope,
        expected_version=version_of(uow, stream_id),
        events=events,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )


def silent(payload: dict[str, object]) -> dict[str, object]:
    """``payload`` with the feed policy of the events that make no card."""
    return {**payload, "feed_policy": FEED_NONE}


def load_record(
    uow: UnitOfWork, scope: str, record_id: str, record_types: Collection[str] | None = None
) -> RecordRef:
    """The record ``record_id`` in ``scope`` (of one of ``record_types`` when given);
    ``RecordNotFoundError`` (one text) when it is hidden, absent, in another project, voided or of
    another type."""
    conn = uow.conn()
    try:
        confidentiality.require_visible(conn, record_id)
    except RecordNotFoundError:
        raise RecordNotFoundError(MSG_UNKNOWN) from None
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if (
        row is None
        or row.scope != scope
        or bool(row.voided)
        or (record_types is not None and row.type not in record_types)
    ):
        raise RecordNotFoundError(MSG_UNKNOWN)
    return RecordRef(
        id=str(row.id),
        key=None if row.key is None else str(row.key),
        title=str(row.title),
        description=None if row.description is None else str(row.description),
        record_type=str(row.type),
        created_on=str(row.created_at)[:10],
    )


def valid_time(at: datetime | None, raised_on: str) -> str:
    """``at`` as the event carries it, now when not given; never in the future and never before
    the day the item was raised."""
    now = utcnow()
    moment = now if at is None else at
    if moment > now:
        raise PunchRuleError(MSG_FUTURE)
    if iso_utc(moment)[:10] < raised_on:
        raise PunchRuleError(MSG_BEFORE_RAISED)
    return iso_utc(moment)


def move(uow: UnitOfWork, cmd: Command, record_id: str, transition: str) -> CommandResult:
    """Run workflow transition ``transition`` of a record as the module (no roles guard)."""
    return handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            stream_id=record_id,
            expected_version=version_of(uow, record_id),
            transition=transition,
            reason=None,
        ),
        by_module=True,
    )
