"""Permit commands: request, approve, reject, issue, revalidate, suspend, resume, hand back,
close, cancel (P2-PTW S2).

A permit is one record of ``permits.Permit``. Every state move is a ``by_module`` workflow
transition run in the same unit of work as the module's own event. Refusals use fixed messages: an
id the viewer may not read, one in another project and one that does not exist answer alike. The
clock is ``handlers.common.now``. Who may act is checked here after the platform checked the access
word: nobody approves what they requested, the holder or a controller revalidates and hands back.
Issue, Resume and Revalidate run ``guards.issue_guards``, one function.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, holds_word, normalise_word
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.uow import UnitOfWork

from tl_mod_permits import MODULE, rules
from tl_mod_permits.errors import PermitBlockedError, PermitRuleError, PermitStateError
from tl_mod_permits.guards import NEEDS, as_time, issue_guards
from tl_mod_permits.handlers.common import (
    RecordRef,
    append,
    correlated,
    load_record,
    move,
    now,
    record_state,
    require_project,
    require_version,
    silent,
)
from tl_mod_permits.names import (
    APPROVE,
    PERMIT,
    PERMIT_APPROVED,
    PERMIT_CANCELLED,
    PERMIT_CLOSED,
    PERMIT_HANDED_BACK,
    PERMIT_ISSUED,
    PERMIT_REJECTED,
    PERMIT_REQUESTED,
    PERMIT_RESUMED,
    PERMIT_REVALIDATED,
    PERMIT_SUSPENDED,
    PERMIT_TABLE,
    REQUESTED,
    T_APPROVE,
    T_CANCEL,
    T_CLOSE,
    T_HAND_BACK,
    T_ISSUE,
    T_REJECT,
    T_RESUME,
    T_REVALIDATE,
    T_SUSPEND,
)
from tl_mod_permits.types_table import load_types

if TYPE_CHECKING:
    from tl_mod_permits.commands import (
        ApprovePermit,
        CancelPermit,
        ClosePermit,
        HandBackPermit,
        IssuePermit,
        RejectPermit,
        RequestPermit,
        ResumePermit,
        RevalidatePermit,
        SuspendPermit,
    )

SHIFT_START = "permits.shift_start"
SHIFT_HOURS = "permits.shift_hours"

MSG_SELF_APPROVE = "the person who requested a permit may not approve or reject it"
MSG_NOT_PARTY = "only the permit holder or a controller may do this to a permit"
MSG_UNKNOWN_PRECAUTION = "a ticked precaution is not one of the permit type's"
MSG_ISSUE_REFUSED = "the permit cannot be made live: "
MSG_MAX_DAYS = "the permit has reached the longest validity of its type; hand it back"
MSG_WINDOW_OVER = "the permit's window has ended"
_ROW_SQL = text(f"SELECT * FROM {PERMIT_TABLE} WHERE id = :id")


@dataclass(frozen=True)
class Permit:
    """A permit as the handlers read it: the envelope, the typed row and the state shown."""

    ref: RecordRef
    state: str
    row: dict[str, Any]

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def key(self) -> str:
        return self.ref.key or ""


def load_permit(uow: UnitOfWork, scope: str, permit_id: str, at: datetime) -> Permit:
    """The permit, its state as ``rules.effective_state`` shows it at ``at``;
    ``RecordNotFoundError`` (the same words) when hidden, absent, elsewhere or not a permit."""
    ref = load_record(uow, scope, permit_id, (PERMIT,))
    row = uow.conn().execute(_ROW_SQL, {"id": ref.id}).mappings().first()
    if row is None:
        raise LookupError(f"no permit row for {ref.id}")
    stored = record_state(uow, ref.id, REQUESTED)
    until = None if row["valid_until"] is None else as_time(row["valid_until"])
    return Permit(ref=ref, state=rules.effective_state(stored, until, at), row=dict(row))


def require_state(permit: Permit, command: str) -> None:
    """The permit is in a state ``command`` takes (``guards.NEEDS``)."""
    needed = NEEDS[command]
    if permit.state not in needed:
        raise PermitStateError(
            f"a permit that is {permit.state} does not take {command}; "
            f"it needs {' or '.join(needed)}"
        )


def _is_controller(uow: UnitOfWork, cmd: Command) -> bool:
    conn = uow.conn()
    return holds_word(
        conn,
        holder_for_actor(conn, cmd.actor),
        scope=cmd.scope,
        module=MODULE,
        word=normalise_word(APPROVE),
    )


def _is_holder(permit: Permit, actor: str) -> bool:
    """The actor asked for the permit, or is the holder it names (the name or the account)."""
    if actor == permit.row["requested_by"]:
        return True
    named = str(permit.row["holder"] or "").strip().casefold()
    return bool(named) and named in (actor.casefold(), actor.split(":", 1)[-1].casefold())


def _require_party(uow: UnitOfWork, cmd: Command, permit: Permit) -> None:
    if not _is_holder(permit, cmd.actor) and not _is_controller(uow, cmd):
        raise ForbiddenError(MSG_NOT_PARTY)


def _shift_end(uow: UnitOfWork, scope: str, at: datetime) -> datetime:
    project = project_of_scope(scope)
    conn = uow.conn()
    return rules.shift_end(
        at,
        str(value_of(conn, SHIFT_START, project=project)),
        int(value_of(conn, SHIFT_HOURS, project=project)),
    )


def _window_end(day: str) -> datetime:
    """The end of the calendar day ``needed_until`` (UTC)."""
    return datetime.combine(date.fromisoformat(day) + timedelta(days=1), datetime.min.time(), UTC)


def _longest(permit: Permit) -> datetime:
    """The latest ``valid_until`` the type allows: ``max_days`` after issue."""
    days = load_types()[str(permit.row["permit_type"])].max_days
    return as_time(permit.row["issued_at"]) + timedelta(days=days)


def _refuse_blockers(uow: UnitOfWork, row: dict[str, Any], at: datetime) -> None:
    blockers = issue_guards(uow.conn(), row, at)
    if blockers:
        raise PermitBlockedError(MSG_ISSUE_REFUSED + ", ".join(blockers))


def _step(
    uow: UnitOfWork,
    cmd: Any,
    permit: Permit,
    transition: str,
    event_type: str,
    payload: dict[str, Any],
) -> CommandResult:
    """Append the module's event, then run the workflow transition (one unit of work)."""
    done = append(
        uow,
        cmd,
        permit.id,
        PERMIT,
        [NewEvent(event_type=event_type, payload=silent(permit.id, payload))],
    )
    moved = move(uow, cmd, permit.id, transition)
    return CommandResult(
        stream_id=permit.id,
        key=permit.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def _open(uow: UnitOfWork, cmd: Any, name: str) -> tuple[Any, Permit, datetime]:
    """Common start: project scope, correlation, the permit, its state, the version."""
    require_project(cmd)
    cmd = correlated(cmd)
    at = now()
    permit = load_permit(uow, cmd.scope, cmd.permit, at)
    require_state(permit, name)
    return cmd, permit, at


def handle_request_permit(uow: UnitOfWork, cmd: RequestPermit) -> CommandResult:
    """Request a permit in state Requested, numbered per project. ``requested_by`` is the actor."""
    require_project(cmd)
    cmd = correlated(cmd)
    subject = None
    if cmd.for_record_id is not None:
        subject = load_record(uow, cmd.scope, cmd.for_record_id).id
    made = create_module_record(
        uow,
        cmd,
        record_type=PERMIT,
        title=cmd.work_description.strip().splitlines()[0][:200],
        description=cmd.work_description,
        key=None,
    )
    done = append(
        uow,
        cmd,
        made.stream_id,
        PERMIT,
        [
            NewEvent(
                event_type=PERMIT_REQUESTED,
                payload=silent(
                    made.stream_id,
                    {
                        "permit_type": cmd.permit_type,
                        "for_record_id": subject,
                        "area": cmd.area,
                        "location_text": cmd.location_text,
                        "holder": cmd.holder,
                        "needed_from": cmd.needed_from,
                        "needed_until": cmd.needed_until,
                    },
                ),
            )
        ],
    )
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=done.new_version,
        events=[*made.events, *done.events],
    )


def _decide(uow: UnitOfWork, cmd: Any, name: str) -> tuple[Any, Permit]:
    cmd, permit, _at = _open(uow, cmd, name)
    if cmd.actor == permit.row["requested_by"]:
        raise ForbiddenError(MSG_SELF_APPROVE)
    require_version(uow, permit.id, cmd.expected_version)
    return cmd, permit


def handle_approve_permit(uow: UnitOfWork, cmd: ApprovePermit) -> CommandResult:
    """Requested to Approved, by a controller other than the requester."""
    cmd, permit = _decide(uow, cmd, "ApprovePermit")
    return _step(uow, cmd, permit, T_APPROVE, PERMIT_APPROVED, {})


def handle_reject_permit(uow: UnitOfWork, cmd: RejectPermit) -> CommandResult:
    """Requested to Rejected, with a reason, by a controller other than the requester."""
    cmd, permit = _decide(uow, cmd, "RejectPermit")
    return _step(uow, cmd, permit, T_REJECT, PERMIT_REJECTED, {"reason": cmd.reason})


def handle_issue_permit(uow: UnitOfWork, cmd: IssuePermit) -> CommandResult:
    """Approved to Active: the issue guards pass, ``valid_until`` is the end of the shift (or the
    window's end if sooner) and the ticked precautions are stored."""
    cmd, permit, at = _open(uow, cmd, "IssuePermit")
    require_version(uow, permit.id, cmd.expected_version)
    asked = {p.id: p for p in load_types()[str(permit.row["permit_type"])].precautions}
    if any(tick not in asked for tick in cmd.precautions):
        raise PermitRuleError(MSG_UNKNOWN_PRECAUTION)
    ticked = [{"id": p.id, "text": p.text} for p in asked.values() if p.id in cmd.precautions]
    _refuse_blockers(uow, {**permit.row, "precautions_json": json.dumps(ticked)}, at)
    until = _shift_end(uow, cmd.scope, at)
    if permit.row["needed_until"]:
        until = min(until, _window_end(str(permit.row["needed_until"])))
    if until <= at:
        raise PermitRuleError(MSG_WINDOW_OVER)
    payload = {"issued_at": iso_utc(at), "valid_until": iso_utc(until), "precautions": ticked}
    return _step(uow, cmd, permit, T_ISSUE, PERMIT_ISSUED, payload)


def handle_revalidate_permit(uow: UnitOfWork, cmd: RevalidatePermit) -> CommandResult:
    """Active or Lapsed: the holder or a controller moves ``valid_until`` to the end of the next
    shift, never past the type's longest validity from issue (a gas-test type needs a fresh
    passing test: the issue guards again)."""
    cmd, permit, at = _open(uow, cmd, "RevalidatePermit")
    _require_party(uow, cmd, permit)
    require_version(uow, permit.id, cmd.expected_version)
    _refuse_blockers(uow, permit.row, at)
    ends = as_time(permit.row["valid_until"]) if permit.row["valid_until"] else at
    longest = _longest(permit)
    if at >= longest:
        raise PermitRuleError(MSG_MAX_DAYS)
    until = min(_shift_end(uow, cmd.scope, max(ends, at)), longest)
    return _step(
        uow,
        cmd,
        permit,
        T_REVALIDATE,
        PERMIT_REVALIDATED,
        {"at": iso_utc(at), "valid_until": iso_utc(until)},
    )


def handle_suspend_permit(uow: UnitOfWork, cmd: SuspendPermit) -> CommandResult:
    """Active or Lapsed to Suspended (stop work), by anyone holding the word."""
    cmd, permit, _at = _open(uow, cmd, "SuspendPermit")
    require_version(uow, permit.id, cmd.expected_version)
    return _step(
        uow, cmd, permit, T_SUSPEND, PERMIT_SUSPENDED, {"reason": cmd.reason, "gas_test_id": None}
    )


def handle_resume_permit(uow: UnitOfWork, cmd: ResumePermit) -> CommandResult:
    """Suspended to Active; the issue guards run again and ``valid_until`` is the end of the
    shift, never past the type's longest validity."""
    cmd, permit, at = _open(uow, cmd, "ResumePermit")
    require_version(uow, permit.id, cmd.expected_version)
    _refuse_blockers(uow, permit.row, at)
    longest = _longest(permit)
    if at >= longest:
        raise PermitRuleError(MSG_MAX_DAYS)
    until = min(_shift_end(uow, cmd.scope, at), longest)
    return _step(
        uow,
        cmd,
        permit,
        T_RESUME,
        PERMIT_RESUMED,
        {"at": iso_utc(at), "valid_until": iso_utc(until)},
    )


def handle_hand_back_permit(uow: UnitOfWork, cmd: HandBackPermit) -> CommandResult:
    """Active, Lapsed or Suspended to Handed back, by the holder or a controller."""
    cmd, permit, _at = _open(uow, cmd, "HandBackPermit")
    _require_party(uow, cmd, permit)
    require_version(uow, permit.id, cmd.expected_version)
    return _step(uow, cmd, permit, T_HAND_BACK, PERMIT_HANDED_BACK, {"note": cmd.handback_note})


def handle_close_permit(uow: UnitOfWork, cmd: ClosePermit) -> CommandResult:
    """Handed back to Closed."""
    cmd, permit, _at = _open(uow, cmd, "ClosePermit")
    require_version(uow, permit.id, cmd.expected_version)
    return _step(uow, cmd, permit, T_CLOSE, PERMIT_CLOSED, {})


def handle_cancel_permit(uow: UnitOfWork, cmd: CancelPermit) -> CommandResult:
    """Requested or Approved to Cancelled, with a reason."""
    cmd, permit, _at = _open(uow, cmd, "CancelPermit")
    require_version(uow, permit.id, cmd.expected_version)
    return _step(uow, cmd, permit, T_CANCEL, PERMIT_CANCELLED, {"reason": cmd.reason})


__all__ = [
    "Permit",
    "handle_approve_permit",
    "handle_cancel_permit",
    "handle_close_permit",
    "handle_hand_back_permit",
    "handle_issue_permit",
    "handle_reject_permit",
    "handle_request_permit",
    "handle_resume_permit",
    "handle_revalidate_permit",
    "handle_suspend_permit",
]
