"""Helpers every cost handler shares: scope check, versions, appends."""

from __future__ import annotations

from sqlalchemy import text
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_cost.errors import CostScopeError

_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise CostScopeError(f"cost codes belong to a project; the scope is {cmd.scope!r}")


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
