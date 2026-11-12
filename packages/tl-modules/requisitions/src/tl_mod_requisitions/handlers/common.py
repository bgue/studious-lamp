"""Helpers the requisitions handlers share: scope, versions, appends, record lookups, moves.

Every id a command is given goes through ``load_record_of`` (``require_visible`` first, ADR-0016
section 5): a record the viewer may not read, one in another project, one of another type and one
that does not exist all answer ``RecordNotFoundError`` with the same words.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, holds_word, normalise_word
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_requisitions import MODULE
from tl_mod_requisitions.errors import RequisitionScopeError, StaleVersionError
from tl_mod_requisitions.names import APPROVE, FEED_NONE

MSG_STALE = "the record changed since it was read"
_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")
_RECORD_SQL = text("SELECT id, key, title, scope, type, voided FROM cur_core_record WHERE id = :id")
_STATUS_SQL = text("SELECT status FROM cur_core_record WHERE id = :id")


@dataclass(frozen=True)
class RecordRef:
    id: str
    key: str | None
    title: str
    record_type: str


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise RequisitionScopeError(f"requisitions belong to a project; the scope is {cmd.scope!r}")


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


def require_version(uow: UnitOfWork, record_id: str, expected: int) -> None:
    """``StaleVersionError`` unless the record is at ``expected`` (ADR-0027 plan-check answer)."""
    if version_of(uow, record_id) != expected:
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


def silent(payload: dict[str, Any]) -> dict[str, Any]:
    """``payload`` with the feed policy of the events that make no card."""
    return {**payload, "feed_policy": FEED_NONE}


def load_record_of(
    uow: UnitOfWork, scope: str, record_id: str, record_types: Collection[str]
) -> RecordRef:
    """The record ``record_id`` of one of ``record_types`` in ``scope``; ``RecordNotFoundError``
    (the same words) when it is hidden, absent, in another project, voided or of another type."""
    conn = uow.conn()
    confidentiality.require_visible(conn, record_id)
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or row.scope != scope or row.type not in record_types or bool(row.voided):
        raise RecordNotFoundError(f"no record {record_id!r}")
    return RecordRef(
        id=str(row.id),
        key=None if row.key is None else str(row.key),
        title=row.title,
        record_type=str(row.type),
    )


def move(
    uow: UnitOfWork, cmd: Command, record_id: str, transition: str, reason: str | None = None
) -> CommandResult:
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
            reason=reason,
        ),
        by_module=True,
    )


def holds_approve(uow: UnitOfWork, cmd: Command) -> bool:
    """The command's actor holds ``requisitions.approve`` on the project (its table word)."""
    conn = uow.conn()
    return holds_word(
        conn,
        holder_for_actor(conn, cmd.actor),
        scope=cmd.scope,
        module=MODULE,
        word=normalise_word(APPROVE),
    )
