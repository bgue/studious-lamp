"""Helpers every correspondence handler shares: scope checks, dates, appends, transitions.

A handler runs inside an entered unit of work and never commits. The module moves its own records
through the workflow with ``transition`` (``by_module=True``): the generic ``TransitionWorkflow``
is not allowed on correspondence items, so a person cannot skip the checks the module's commands
make. A handler reads through ``registry`` (which applies the viewer's confidentiality, ADR-0016):
an item the viewer may not read answers ``RecordNotFoundError`` exactly as a missing one does.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from tl_core import confidentiality
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import (
    CorrespondenceScopeError,
    ItemBackdatedError,
    ItemStateError,
)
from tl_mod_correspondence.names import COMMERCIAL, CORRESPONDENCE

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise CorrespondenceScopeError(
            f"correspondence belongs to a project; the scope is {cmd.scope!r}"
        )


def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    if cmd.correlation_id is not None:
        return cmd
    return cmd.model_copy(update={"correlation_id": new_ulid()})


def now() -> datetime:
    """The current instant: the one place this module reads the clock (tests freeze it)."""
    return utcnow()


def today() -> str:
    """Today's date, ISO, from ``now``."""
    return now().date().isoformat()


def today_date() -> date:
    return now().date()


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


#: A date a caller states for an item is within this many days of today.
MAX_DAYS_AHEAD = 366
MAX_DAYS_BACK = 366 * 50


def plausible_date(value: str | None, what: str) -> str | None:
    """``check_date``, and the day is at most a year ahead and 50 years back of today."""
    found = check_date(value, what)
    if found is None:
        return None
    offset = (date.fromisoformat(found) - today_date()).days
    if offset > MAX_DAYS_AHEAD:
        raise ValueError(f"{what} {found} is more than a year ahead of today")
    if offset < -MAX_DAYS_BACK:
        raise ValueError(f"{what} {found} is more than 50 years back")
    return found


def resolve_date(value: str | None, reason: str | None, what: str) -> tuple[str, str | None]:
    """``(date, reason)`` for an act's date: today by default, never in the future.

    A date before today is a back-dated entry and needs a non-blank ``reason``, which the event
    keeps: the record says when something really happened and why it was entered later.
    """
    now = today()
    if value is None:
        return now, None
    if value > now:
        raise ItemBackdatedError(f"{what} {value} is in the future; today is {now}")
    if value < now and not (reason and reason.strip()):
        raise ItemBackdatedError(
            f"{what} {value} is before today ({now}); give the reason for the date"
        )
    return value, (reason.strip() if value < now and reason else None)


def version_of(uow: UnitOfWork, record_id: str) -> int:
    """The stream version of a record now (the envelope row follows every module event)."""
    found = uow.conn().execute(_VERSION_SQL, {"id": record_id}).scalar_one_or_none()
    if found is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
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


def load_item(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """The item, in the command's scope and readable by the viewer.

    A missing item, one in another scope and one the viewer may not read all raise the same
    ``RecordNotFoundError`` (ADR-0016): the message must not tell them apart.
    """
    found = registry.get_item(uow.conn(), item_id)
    if found is None or found.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {item_id!r}")
    return found


def load_item_for_control(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """The item for a command that must work on an item its actor cannot read (ADR-0016 section
    2: naming who may read a privileged item, so that the last reader leaving does not lock the
    item). Only a controller-level viewer takes this path; for anyone else it is ``load_item``.

    The item must exist in the command's scope; nothing of it is shown to the actor. A missing
    item and one of another scope raise the same ``RecordNotFoundError`` as ``load_item``.
    """
    if confidentiality.current_viewer().level < 1:
        return load_item(uow, cmd, item_id)
    found = registry.get_item_for_control(uow.conn(), item_id)
    if found is None or found.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {item_id!r}")
    return found


def open_item(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """Like ``load_item``, and the item must still take changes (not void, closed or replaced)."""
    found = load_item(uow, cmd, item_id)
    if found.closed:
        raise ItemStateError(
            f"item {found.number} is {found.state}"
            + (f", replaced by {found.superseded_by_id}" if found.superseded_by_id else "")
            + " and takes no more changes"
        )
    return found


def require_controller_for(item: registry.ItemRow) -> None:
    """Refuse a viewer below a document controller when ``item`` is a Commercial item.

    A Commercial item is changed by controllers only, **whatever the access word of the command**
    (ADR-0019 section 3): a person named on a privileged one (an escalation names the readers of
    the RFI) may read it and must not pause its clock, void it, thread it or attach to it. Called
    by every command of the module that changes an item or its clocks.
    """
    if item.record_type == COMMERCIAL and confidentiality.current_viewer().level < 1:
        raise ForbiddenError("commercial items are for the document_controller and admin roles")


def require_core(item: registry.ItemRow) -> None:
    """Raise ``ItemStateError`` unless the item is a core item (General, Document control).

    A Technical or Commercial item has a workflow of its own (brief 8): the commands that move a
    core item through Received, Triaged, Issued and Responded do not apply to it, and it is
    changed with the commands of its domain.
    """
    if item.record_type != CORRESPONDENCE:
        raise ItemStateError(
            f"item {item.number} belongs to the {item.domain or 'domain'} domain, which has "
            "commands of its own; this command is for letters and minutes"
        )


def require_state(item: registry.ItemRow, *states: str) -> None:
    """Raise ``ItemStateError`` unless the item is in one of ``states``."""
    if item.state not in states:
        raise ItemStateError(
            f"item {item.number} is {item.state}; this needs it to be {' or '.join(states)}"
        )


def changes_of(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    """``{field: [old, new]}`` for each field of ``new`` that differs."""
    return {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}


__all__ = [
    "append",
    "changes_of",
    "check_date",
    "correlated",
    "load_item",
    "now",
    "open_item",
    "plausible_date",
    "require_controller_for",
    "require_core",
    "require_project",
    "require_state",
    "resolve_date",
    "today",
    "today_date",
    "transition",
    "version_of",
]
