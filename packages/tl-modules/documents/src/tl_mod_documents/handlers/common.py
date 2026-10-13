"""Helpers every documents handler shares: scope checks, versions, module-owned transitions.

A handler runs inside an entered unit of work and never commits. The module moves its own records
through the workflow with ``transition`` (``by_module=True``): the generic ``TransitionWorkflow``
is not allowed on documents, revisions or transmittals, so a person cannot skip the checks the
module's commands make.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import text
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_documents import registry
from tl_mod_documents.errors import (
    BackdatedError,
    DocumentClosedError,
    DocumentNotFoundError,
    ProjectScopeError,
    RevisionNotFoundError,
)

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise ProjectScopeError(f"this belongs to a project; the scope is {cmd.scope!r}")


def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    if cmd.correlation_id is not None:
        return cmd
    return cmd.model_copy(update={"correlation_id": new_ulid()})


def today() -> str:
    return utcnow().date().isoformat()


def check_date(value: str | None, what: str) -> str | None:
    """``value`` when it is an ISO calendar date (or ``None``); otherwise a ``ValueError``."""
    if value is None:
        return None
    if ISO_DATE.fullmatch(value) is None:
        raise ValueError(f"{what} must be a date written YYYY-MM-DD, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{what} is not a calendar date: {value!r}") from exc
    return value


#: A date a caller states for a revision or a due date is within this many days of today.
MAX_DAYS_AHEAD = 366
MAX_DAYS_BACK = 366 * 50


def plausible_date(value: str | None, what: str) -> str | None:
    """``check_date``, and the day is at most a year ahead and 50 years back of today.

    A typo like ``2062-10-13`` or ``1926-10-13`` would put a revision or a due date where no report
    looks (P1-I2 security review).
    """
    found = check_date(value, what)
    if found is None:
        return None
    offset = (date.fromisoformat(found) - date.fromisoformat(today())).days
    if offset > MAX_DAYS_AHEAD:
        raise ValueError(f"{what} {found} is more than a year ahead of today")
    if offset < -MAX_DAYS_BACK:
        raise ValueError(f"{what} {found} is more than 50 years back")
    return found


def resolve_date(value: str | None, reason: str | None, what: str) -> tuple[str, str | None]:
    """``(date, reason)`` for an issue or answer date: today by default, never in the future.

    A date before today is a back-dated entry and needs a non-blank ``reason``, which the event
    keeps (P1-I2 security review): the controlled record says when something really happened.
    """
    now = today()
    if value is None:
        return now, None
    if value > now:
        raise BackdatedError(f"{what} {value} is in the future; today is {now}")
    if value < now and not (reason and reason.strip()):
        raise BackdatedError(
            f"{what} {value} is before today ({now}); give the reason for the date"
        )
    return value, (reason.strip() if value < now and reason else None)


def version_of(uow: UnitOfWork, record_id: str) -> int:
    """The stream version of a record now (the envelope row follows every module event)."""
    found = uow.conn().execute(_VERSION_SQL, {"id": record_id}).scalar_one_or_none()
    if found is None:
        raise LookupError(f"no record {record_id!r}")
    return int(found)


def append(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    stream_type: str,
    events: list[NewEvent],
    *,
    expected: int | None = None,
) -> AppendResult:
    """Append ``events`` to a stream at its current version (or ``expected``)."""
    return uow.append(
        stream_id=stream_id,
        stream_type=stream_type,
        scope=cmd.scope,
        expected_version=expected if expected is not None else version_of(uow, stream_id),
        events=events,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )


def transition(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    name: str,
    *,
    reason: str | None = None,
    expected: int | None = None,
) -> CommandResult:
    """Run workflow transition ``name`` on a record of this module (at ``expected`` or now)."""
    return handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            stream_id=stream_id,
            expected_version=expected if expected is not None else version_of(uow, stream_id),
            transition=name,
            reason=reason,
        ),
        by_module=True,
    )


def load_document(uow: UnitOfWork, cmd: Command, document_id: str) -> registry.DocumentRow:
    """The document, in the command's scope. Raises ``DocumentNotFoundError``."""
    found = registry.get_document(uow.conn(), document_id)
    if found is None or found.scope != cmd.scope:
        raise DocumentNotFoundError(f"no document {document_id!r} in scope {cmd.scope!r}")
    return found


def open_document(uow: UnitOfWork, cmd: Command, document_id: str) -> registry.DocumentRow:
    """Like ``load_document``, and the document must still take changes."""
    found = load_document(uow, cmd, document_id)
    if found.closed:
        raise DocumentClosedError(
            f"document {found.number} is {found.state} and takes no more changes"
        )
    return found


def load_revision(uow: UnitOfWork, cmd: Command, revision_id: str) -> registry.RevisionRow:
    """The revision, in the command's scope. Raises ``RevisionNotFoundError``."""
    found = registry.get_revision(uow.conn(), revision_id)
    if found is None or found.scope != cmd.scope:
        raise RevisionNotFoundError(f"no revision {revision_id!r} in scope {cmd.scope!r}")
    return found


def changes_of(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    """``{field: [old, new]}`` for each field of ``new`` that differs."""
    return {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}
