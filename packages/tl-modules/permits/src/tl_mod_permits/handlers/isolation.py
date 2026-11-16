"""Isolation commands: apply, verify, remove, link and unlink (P2-PTW S3).

An isolation is one record of ``permits.Isolation``. Verify and Remove are ``by_module`` workflow
transitions run in the same unit of work as the module's own event. A permit depends on an isolation
by the ``Permit.IsolationLinked`` and ``Permit.IsolationUnlinked`` events of its own stream, the
ones ``guards.issue_guards`` reads. Refusals use fixed messages: an id the viewer may not read, one
in another project and one that does not exist answer alike, and a refusal never names a permit the
viewer cannot read (``a permit you cannot see``, however many there are).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core import confidentiality
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_permits.errors import IsolationInUseError, IsolationRuleError, IsolationStateError
from tl_mod_permits.guards import dependent_permits, linked_isolations
from tl_mod_permits.handlers import common
from tl_mod_permits.handlers.common import (
    RecordRef,
    append,
    correlated,
    load_record,
    move,
    record_state,
    require_project,
    require_version,
    silent,
)
from tl_mod_permits.handlers.permit import load_permit
from tl_mod_permits.names import (
    ACTIVE,
    APPLIED,
    ISOLATION,
    ISOLATION_APPLIED,
    ISOLATION_REMOVED,
    ISOLATION_TABLE,
    ISOLATION_VERIFIED,
    LAPSED,
    PERMIT,
    PERMIT_ISOLATION_LINKED,
    PERMIT_ISOLATION_UNLINKED,
    REMOVED,
    T_REMOVE,
    T_VERIFY,
    VERIFIED,
)

if TYPE_CHECKING:
    from tl_mod_permits.iso_commands import (
        ApplyIsolation,
        LinkIsolation,
        RemoveIsolation,
        UnlinkIsolation,
        VerifyIsolation,
    )

MSG_SELF_VERIFY = "the person who applied an isolation may not verify it"
MSG_LINK_LIVE = (
    "a permit that is Active or Lapsed does not take an isolation change; suspend it first"
)
MSG_LINK_REMOVED = "an isolation that is Removed cannot be linked to a permit"
MSG_LINK_STRICTER = "the isolation cannot be linked to this permit"
MSG_ALREADY_LINKED = "the isolation is already linked to the permit"
MSG_NOT_LINKED = "the isolation is not linked to the permit"
MSG_IN_USE = "the isolation is still needed by "
MSG_HIDDEN_PERMIT = "a permit you cannot see"
_APPLIED_BY_SQL = text(f"SELECT applied_by FROM {ISOLATION_TABLE} WHERE id = :id")


def _load(uow: UnitOfWork, scope: str, isolation_id: str) -> tuple[RecordRef, str]:
    """The isolation and its state; ``RecordNotFoundError`` (one text) when hidden or absent."""
    ref = load_record(uow, scope, isolation_id, (ISOLATION,))
    return ref, record_state(uow, ref.id, APPLIED)


def _require_state(state: str, allowed: tuple[str, ...], command: str) -> None:
    if state not in allowed:
        raise IsolationStateError(
            f"an isolation that is {state} does not take {command}; it needs {' or '.join(allowed)}"
        )


def _step(
    uow: UnitOfWork,
    cmd: Any,
    ref: RecordRef,
    transition: str,
    event_type: str,
    payload: dict[str, Any],
) -> CommandResult:
    """Append the module's event, then run the workflow transition (one unit of work)."""
    event = NewEvent(event_type=event_type, payload=silent(ref.id, payload))
    done = append(uow, cmd, ref.id, ISOLATION, [event])
    moved = move(uow, cmd, ref.id, transition)
    return CommandResult(
        stream_id=ref.id,
        key=ref.key or "",
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def handle_apply_isolation(uow: UnitOfWork, cmd: ApplyIsolation) -> CommandResult:
    """Record an isolation in state Applied, numbered per project. ``applied_by`` is the actor."""
    require_project(cmd)
    cmd = correlated(cmd)
    at = common.now()
    point = None
    if cmd.point_record_id is not None:
        point = load_record(uow, cmd.scope, cmd.point_record_id).id
    made = create_module_record(
        uow, cmd, record_type=ISOLATION, title=cmd.point_text[:200], key=None
    )
    done = append(
        uow,
        cmd,
        made.stream_id,
        ISOLATION,
        [
            NewEvent(
                event_type=ISOLATION_APPLIED,
                payload=silent(
                    made.stream_id,
                    {
                        "point_text": cmd.point_text,
                        "point_record_id": point,
                        "energy": cmd.energy,
                        "method": cmd.method,
                        "lock_number": cmd.lock_number,
                        "tag_number": cmd.tag_number,
                        "applied_at": iso_utc(at),
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


def handle_verify_isolation(uow: UnitOfWork, cmd: VerifyIsolation) -> CommandResult:
    """Applied to Verified, by a controller other than the person who applied it."""
    require_project(cmd)
    cmd = correlated(cmd)
    at = common.now()
    ref, state = _load(uow, cmd.scope, cmd.isolation)
    _require_state(state, (APPLIED,), "VerifyIsolation")
    applied_by = uow.conn().execute(_APPLIED_BY_SQL, {"id": ref.id}).scalar_one()
    if cmd.actor == applied_by:
        raise ForbiddenError(MSG_SELF_VERIFY)
    require_version(uow, ref.id, cmd.expected_version)
    return _step(uow, cmd, ref, T_VERIFY, ISOLATION_VERIFIED, {"verified_at": iso_utc(at)})


def _refuse_dependents(uow: UnitOfWork, isolation_id: str) -> None:
    """``IsolationInUseError`` while a permit that links the isolation is Approved, Active or
    Suspended. A permit the viewer can read is named by its key; any others are one phrase."""
    conn = uow.conn()
    keys: list[str] = []
    unseen = False
    for permit in dependent_permits(conn, isolation_id):
        if confidentiality.is_hidden(conn, str(permit["id"])):
            unseen = True
        else:
            keys.append(str(permit["key"]))
    if not keys and not unseen:
        return
    names = sorted(keys) + ([MSG_HIDDEN_PERMIT] if unseen else [])
    named = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    raise IsolationInUseError(MSG_IN_USE + named)


def handle_remove_isolation(uow: UnitOfWork, cmd: RemoveIsolation) -> CommandResult:
    """Applied or Verified to Removed, unless a permit still depends on it."""
    require_project(cmd)
    cmd = correlated(cmd)
    at = common.now()
    ref, state = _load(uow, cmd.scope, cmd.isolation)
    _require_state(state, (APPLIED, VERIFIED), "RemoveIsolation")
    require_version(uow, ref.id, cmd.expected_version)
    _refuse_dependents(uow, ref.id)
    return _step(uow, cmd, ref, T_REMOVE, ISOLATION_REMOVED, {"removed_at": iso_utc(at)})


def _stricter(uow: UnitOfWork, isolation_id: str, permit_id: str) -> bool:
    """The isolation (through its own class or its point record) is hidden from a reader who may
    read the permit: its id would reach the permit's stream, which any reader of the permit sees."""
    conn = uow.conn()
    return any(
        confidentiality.is_hidden(conn, isolation_id, viewer)
        and not confidentiality.is_hidden(conn, permit_id, viewer)
        for viewer in (confidentiality.LOWEST, confidentiality.RESTRICTED_ONLY)
    )


def _change_link(
    uow: UnitOfWork, cmd: LinkIsolation | UnlinkIsolation, event_type: str
) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    at = common.now()
    permit = load_permit(uow, cmd.scope, cmd.permit, at)
    ref, state = _load(uow, cmd.scope, cmd.isolation)
    if event_type == PERMIT_ISOLATION_LINKED and _stricter(uow, ref.id, permit.id):
        raise IsolationRuleError(MSG_LINK_STRICTER)
    if permit.state in (ACTIVE, LAPSED):
        raise IsolationRuleError(MSG_LINK_LIVE)
    linked = ref.id in linked_isolations(uow.conn(), permit.id)
    if event_type == PERMIT_ISOLATION_LINKED:
        if state == REMOVED:
            raise IsolationStateError(MSG_LINK_REMOVED)
        if linked:
            raise IsolationRuleError(MSG_ALREADY_LINKED)
    elif not linked:
        raise IsolationRuleError(MSG_NOT_LINKED)
    done = append(
        uow,
        cmd,
        permit.id,
        PERMIT,
        [NewEvent(event_type=event_type, payload=silent(permit.id, {"isolation_id": ref.id}))],
    )
    return CommandResult(
        stream_id=permit.id, key=permit.key, version=done.new_version, events=done.events
    )


def handle_link_isolation(uow: UnitOfWork, cmd: LinkIsolation) -> CommandResult:
    """The permit depends on the isolation: one ``Permit.IsolationLinked`` event."""
    return _change_link(uow, cmd, PERMIT_ISOLATION_LINKED)


def handle_unlink_isolation(uow: UnitOfWork, cmd: UnlinkIsolation) -> CommandResult:
    """The permit no longer depends on the isolation: one ``Permit.IsolationUnlinked`` event."""
    return _change_link(uow, cmd, PERMIT_ISOLATION_UNLINKED)


__all__ = [
    "handle_apply_isolation",
    "handle_link_isolation",
    "handle_remove_isolation",
    "handle_unlink_isolation",
    "handle_verify_isolation",
]
