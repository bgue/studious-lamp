"""Helpers every legacy stage shares: versions, appends, module-owned transitions, text."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")


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
    """Append ``events`` to a stream at its current version, in the scope of the stream."""
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


def transition(
    uow: UnitOfWork, cmd: Command, stream_id: str, name: str, *, reason: str | None = None
) -> CommandResult:
    """Run workflow transition ``name`` on a record of this module, as the module."""
    return handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            stream_id=stream_id,
            expected_version=version_of(uow, stream_id),
            transition=name,
            reason=reason,
        ),
        by_module=True,
    )


def canonical(value: Any) -> str:
    """Canonical JSON text: sorted keys, no spaces, UTF-8 kept (the ledger's form)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
