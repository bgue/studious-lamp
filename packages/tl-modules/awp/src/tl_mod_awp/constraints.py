"""Constraints on an IWP: raise, assign, clear, void, aging, and the calls the checks make.

A constraint (``awp.Constraint``, numbered ``{project}-CON-{seq:4}``, gap-free) holds one IWP back
until it is cleared. It has five sources: a person raises ``manual``; the readiness engine and the
other modules raise ``check``, ``rule``, ``feed_hold`` and ``thread_hold`` through the plain
functions here (``raise_constraint``, ``clear_constraint``), which a person's command never reaches
with a module source. A constraint ``blocks`` its IWP (a link the module writes, source
``rule``) and ``resolves`` is the link from the record that resolved it.

R-P2-11, suppress after a person's clear: a check-raised constraint keeps the hash of the facts it
was raised on (``Constraint.Raised.suppress_hash``). A person's clear of it needs a reason and keeps
the hash (``Constraint.Cleared`` carries ``suppress: true``); a check's own clear drops it
(``suppress: false``). ``raise_constraint`` for the same IWP and check name with an equal hash then
changes nothing and answers the cleared constraint with the code ``suppressed``; a different hash
raises a new one. Fixed messages, never a cell of the input.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_mod_awp.common import (
    account_actor_exists,
    append,
    correlated,
    move,
    record_state,
    require_list_code,
    require_project,
    setting_value,
    version_of,
)
from tl_mod_awp.errors import (
    ConstraintRuleError,
    ConstraintSourceError,
    ConstraintStateError,
    IwpStateError,
)
from tl_mod_awp.fields import parse_date
from tl_mod_awp.handlers.iwp import load_iwp
from tl_mod_awp.limits import (
    HASH_PATTERN,
    MAX_CHECK_NAME,
    MAX_CLEAR_REASON,
    MAX_CONSTRAINT_TEXT,
    MAX_TITLE,
)
from tl_mod_awp.linking import sync_links
from tl_mod_awp.names import (
    ALL_SOURCES,
    BLOCKS_RELATION,
    CODE_SUPPRESSED,
    CON_ASSIGNED,
    CON_CLEARED,
    CON_OPEN,
    CONSTRAINT,
    CONSTRAINT_ASSIGNED,
    CONSTRAINT_CLEARED,
    CONSTRAINT_RAISED,
    IWP_TERMINAL,
    MODULE_SOURCES,
    RESOLVES_RELATION,
    SOURCE_MANUAL,
)

TYPE_LIST = "ConstraintType"
LEAD_SETTING = "awp.iwp.ready_lead_weeks"
AGING_SETTING = "awp.constraint.aging_days"
MSG_MODULE_ONLY = "a person raises only a manual constraint"
MSG_CHECK_FIELDS = "a check constraint needs a check name and the hash of the facts"
MSG_CHECK_ONLY = "only a check constraint carries a check name or a hash"
MSG_SOURCE = "the source is manual, check, rule, feed_hold or thread_hold"
MSG_OWNER = "the owner is not an account of this system"
MSG_NEED_BY = "a constraint needs a need-by date or an IWP with a planned start"
MSG_TERMINAL = "a package that is closed, split or cancelled takes no new constraint"
MSG_OPEN_ONLY = "only an open or assigned constraint takes this command"
MSG_ASSIGN_OPEN = "only an open constraint can be assigned"
MSG_TEXT = "the description is 1 to 500 characters"
MSG_REASON = "the reason is 1 to 300 characters"
MSG_CLEAR_SOURCE = "a check clears only a constraint a check raised"
MSG_RESOLVED_BY = "no record with that id in the project"
BLOCKS_REASON = "the constraint ended"
_HASH = re.compile(HASH_PATTERN)

_ROW_SQL = text(
    "SELECT r.id, r.key, r.status, c.iwp_id, c.constraint_type, c.source, c.owner, c.need_by, "
    "c.description_text, c.check_name, c.raised_at, c.cleared_at, c.cleared_by, c.clear_reason, "
    "c.suppress_hash FROM cur_core_record r JOIN cur_awp_constraint c ON c.id = r.id "
    "WHERE r.id = :id"
)
_SUPPRESSED_SQL = text(
    "SELECT c.id FROM cur_awp_constraint c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.iwp_id = :iwp AND c.check_name = :check_name AND c.suppress_hash = :hash "
    "AND r.status = :cleared ORDER BY c.raised_at DESC, c.id DESC LIMIT 1"
)
_OPEN_SQL = text(
    "SELECT c.id FROM cur_awp_constraint c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.iwp_id = :iwp AND COALESCE(r.status, :open) IN (:open, :assigned) ORDER BY r.key"
)
_RECORD_SQL = text("SELECT scope, voided FROM cur_core_record WHERE id = :id")


@dataclass(frozen=True)
class ConstraintRow:
    """A constraint as the handlers and the views read it."""

    id: str
    key: str
    state: str
    iwp_id: str
    constraint_type: str
    source: str
    owner: str
    need_by: str | None
    description: str | None
    check_name: str | None
    raised_at: str | None
    cleared_at: str | None
    cleared_by: str | None
    clear_reason: str | None
    suppress_hash: str | None
    version: int = 0


class RaiseResult(CommandResult):
    """The result of ``raise_constraint``: ``code`` is ``suppressed`` when a person's clear of the
    same check result stands (nothing was written; the stream is the cleared constraint)."""

    code: str | None = None


def _opt(value: Any) -> str | None:
    return None if value is None else str(value)


def load_constraint(uow: UnitOfWork, scope: str, constraint_id: str) -> ConstraintRow:
    """The constraint; ``RecordNotFoundError`` (the same words) when it is hidden, absent, in
    another project or not a constraint."""
    conn = uow.conn()
    confidentiality.require_visible(conn, constraint_id)
    row = conn.execute(_ROW_SQL, {"id": constraint_id}).first()
    meta = conn.execute(_RECORD_SQL, {"id": constraint_id}).first()
    if row is None or meta is None or meta.scope != scope:
        raise RecordNotFoundError(f"no record {constraint_id!r}")
    return ConstraintRow(
        id=str(row.id),
        key=str(row.key or ""),
        state=str(row.status or CON_OPEN),
        iwp_id=str(row.iwp_id),
        constraint_type=str(row.constraint_type),
        source=str(row.source),
        owner=str(row.owner),
        need_by=_opt(row.need_by),
        description=_opt(row.description_text),
        check_name=_opt(row.check_name),
        raised_at=_opt(row.raised_at),
        cleared_at=_opt(row.cleared_at),
        cleared_by=_opt(row.cleared_by),
        clear_reason=_opt(row.clear_reason),
        suppress_hash=_opt(row.suppress_hash),
        version=version_of(uow, str(row.id)),
    )


def _field(row: ConstraintRow | Mapping[str, Any], name: str) -> Any:
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name)


def constraint_age_days(row: ConstraintRow | Mapping[str, Any], today: date) -> int:
    """Whole days from the day the constraint was raised to ``today`` (to the day it was cleared
    when it is cleared). A pure function of the row; never negative."""
    raised = _field(row, "raised_at")
    if raised is None:
        return 0
    cleared = _field(row, "cleared_at")
    end = today if cleared is None else date.fromisoformat(str(cleared)[:10])
    return max(0, (end - date.fromisoformat(str(raised)[:10])).days)


def is_aging(row: ConstraintRow | Mapping[str, Any], today: date, aging_days: int) -> bool:
    """The constraint is open and has stood longer than ``aging_days`` (``aging`` flag)."""
    if _field(row, "cleared_at") is not None:
        return False
    return constraint_age_days(row, today) > aging_days


def aging_days_of(conn: Connection, scope: str) -> int:
    """The setting ``awp.constraint.aging_days`` for the project of ``scope``."""
    return int(setting_value(conn, scope, AGING_SETTING))


def need_by_default(conn: Connection, scope: str, planned_start: str | None) -> str | None:
    """The planned start minus ``awp.iwp.ready_lead_weeks`` weeks; ``None`` without a start."""
    if planned_start is None:
        return None
    weeks = int(setting_value(conn, scope, LEAD_SETTING))
    return (date.fromisoformat(planned_start) - timedelta(weeks=weeks)).isoformat()


def _check_owner(conn: Connection, owner: str) -> None:
    if not account_actor_exists(conn, owner):
        raise ConstraintRuleError(MSG_OWNER)


def raise_constraint(
    uow: UnitOfWork,
    cmd: Command,
    *,
    iwp_id: str,
    constraint_type: str,
    source: str,
    owner: str,
    description: str,
    need_by: str | None = None,
    check_name: str | None = None,
    facts_hash: str | None = None,
    by_module: bool = True,
) -> RaiseResult:
    """Raise a constraint on an IWP: ``Numbering.Allocated``, ``Record.Created``,
    ``Constraint.Raised`` and the ``blocks`` link to the IWP.

    ``by_module`` is a Python argument, never a field a client sets: the readiness engine and the
    other modules call this function (default ``True``); the person's command passes ``False`` and
    is refused every source but ``manual`` (``ConstraintSourceError``). A ``check`` needs a check
    name and the hash of its facts; a ``check`` whose hash a person already cleared for the same
    IWP and check name changes nothing and answers the cleared constraint with the code
    ``suppressed``. Without ``need_by`` the date is the planned start minus the lead weeks
    (``ConstraintRuleError`` when the IWP has no planned start either)."""
    require_project(cmd)
    cmd = correlated(cmd)
    if source not in ALL_SOURCES:
        raise ConstraintRuleError(MSG_SOURCE)
    if source != SOURCE_MANUAL and not by_module:
        raise ConstraintSourceError(MSG_MODULE_ONLY)
    if source == "check":
        if not check_name or not facts_hash or _HASH.fullmatch(facts_hash) is None:
            raise ConstraintRuleError(MSG_CHECK_FIELDS)
        if len(check_name) > MAX_CHECK_NAME:
            raise ConstraintRuleError(MSG_CHECK_FIELDS)
    elif check_name is not None or facts_hash is not None:
        raise ConstraintRuleError(MSG_CHECK_ONLY)
    if not 1 <= len(description) <= MAX_CONSTRAINT_TEXT:
        raise ConstraintRuleError(MSG_TEXT)
    conn = uow.conn()
    iwp = load_iwp(uow, cmd.scope, iwp_id)
    if iwp.state in IWP_TERMINAL:
        raise IwpStateError(MSG_TERMINAL)
    if source == "check":
        prior = conn.execute(
            _SUPPRESSED_SQL,
            {"iwp": iwp.id, "check_name": check_name, "hash": facts_hash, "cleared": CON_CLEARED},
        ).scalar_one_or_none()
        if prior is not None:
            held = load_constraint(uow, cmd.scope, str(prior))
            return RaiseResult(
                stream_id=held.id,
                key=held.key,
                version=held.version,
                events=[],
                code=CODE_SUPPRESSED,
            )
    _check_owner(conn, owner)
    require_list_code(conn, cmd.scope, TYPE_LIST, constraint_type, "the constraint type")
    when: str | None
    if need_by is not None:
        try:
            when = parse_date(need_by)
        except ValueError:
            raise ConstraintRuleError(MSG_NEED_BY) from None
    else:
        when = need_by_default(conn, cmd.scope, iwp.planned_start)
    if when is None:
        raise ConstraintRuleError(MSG_NEED_BY)
    made = create_module_record(
        uow,
        cmd,
        record_type=CONSTRAINT,
        title=description[:MAX_TITLE].strip() or constraint_type,
        key=None,
        extra_events=[
            NewEvent(
                event_type=CONSTRAINT_RAISED,
                payload={
                    "iwp_id": iwp.id,
                    "constraint_type": constraint_type,
                    "source": source,
                    "owner": owner,
                    "need_by": when,
                    "description": description,
                    "check_name": check_name,
                    "raised_at": iso_utc(utcnow()),
                    "suppress_hash": facts_hash,
                },
            )
        ],
    )
    events = list(made.events)
    events.extend(sync_links(uow, cmd, made.stream_id, BLOCKS_RELATION, {iwp.id}, BLOCKS_REASON))
    return RaiseResult(stream_id=made.stream_id, key=made.key, version=made.version, events=events)


def assign_constraint(
    uow: UnitOfWork, cmd: Command, *, constraint_id: str, owner: str
) -> CommandResult:
    """Open to Assigned with a new owner: ``Constraint.Assigned`` and ``Workflow.Transitioned``."""
    require_project(cmd)
    cmd = correlated(cmd)
    row = load_constraint(uow, cmd.scope, constraint_id)
    if row.state != CON_OPEN:
        raise ConstraintStateError(MSG_ASSIGN_OPEN)
    _check_owner(uow.conn(), owner)
    assigned = append(
        uow,
        cmd,
        row.id,
        CONSTRAINT,
        [
            NewEvent(
                event_type=CONSTRAINT_ASSIGNED, payload={"owner": owner, "need_by": row.need_by}
            )
        ],
    )
    moved = move(uow, cmd, row.id, "assign")
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=moved.version,
        events=[*assigned.events, *moved.events],
    )


def clear_constraint(
    uow: UnitOfWork,
    cmd: Command,
    *,
    constraint_id: str,
    reason: str,
    resolved_by: str | None = None,
    by_source: str | None = None,
) -> CommandResult:
    """Clear an open or assigned constraint: ``Constraint.Cleared``, the ``resolves`` link from
    ``resolved_by`` when given, ``Workflow.Transitioned``.

    ``by_source`` is ``None`` for a person (any source; a clear of a check-raised constraint keeps
    the hash, so the same result does not raise it again). A module passes its own source and is
    refused (``ConstraintSourceError``) a constraint another source raised: a check clears only
    what a check raised. A ``resolved_by`` the viewer may not read answers as a record that does not
    exist (``RecordNotFoundError``)."""
    require_project(cmd)
    cmd = correlated(cmd)
    if not 1 <= len(reason) <= MAX_CLEAR_REASON:
        raise ConstraintRuleError(MSG_REASON)
    row = load_constraint(uow, cmd.scope, constraint_id)
    if by_source is not None and (by_source not in MODULE_SOURCES or row.source != by_source):
        raise ConstraintSourceError(MSG_CLEAR_SOURCE)
    if row.state not in (CON_OPEN, CON_ASSIGNED):
        raise ConstraintStateError(MSG_OPEN_ONLY)
    conn = uow.conn()
    if resolved_by is not None:
        confidentiality.require_visible(conn, resolved_by)
        found = conn.execute(_RECORD_SQL, {"id": resolved_by}).first()
        if found is None or bool(found.voided) or found.scope not in (cmd.scope, "company"):
            raise RecordNotFoundError(MSG_RESOLVED_BY)
    payload: dict[str, Any] = {
        "by": cmd.actor,
        "reason": reason,
        "resolved_by": resolved_by,
        "suppress": by_source is None,
    }
    cleared = append(
        uow, cmd, row.id, CONSTRAINT, [NewEvent(event_type=CONSTRAINT_CLEARED, payload=payload)]
    )
    events = list(cleared.events)
    if resolved_by is not None:
        added = handle_add_link(
            uow,
            AddLink(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                from_id=resolved_by,
                to_id=row.id,
                relation=RESOLVES_RELATION,
                link_source="rule",
            ),
            by_module=True,
        )
        events.extend(added.events)
    moved = move(uow, cmd, row.id, "clear", reason)
    events.extend(moved.events)
    return CommandResult(stream_id=row.id, key=row.key, version=moved.version, events=events)


def void_constraint(
    uow: UnitOfWork, cmd: Command, *, constraint_id: str, reason: str
) -> CommandResult:
    """Open or assigned to Void: ``Workflow.Transitioned`` only."""
    require_project(cmd)
    cmd = correlated(cmd)
    if not 1 <= len(reason) <= MAX_CLEAR_REASON:
        raise ConstraintRuleError(MSG_REASON)
    row = load_constraint(uow, cmd.scope, constraint_id)
    if row.state not in (CON_OPEN, CON_ASSIGNED):
        raise ConstraintStateError(MSG_OPEN_ONLY)
    moved = move(uow, cmd, row.id, "void", reason)
    return CommandResult(stream_id=row.id, key=row.key, version=moved.version, events=moved.events)


def void_open_constraints(uow: UnitOfWork, cmd: Command, iwp_id: str, reason: str) -> list[Any]:
    """Void every open or assigned constraint of an IWP with ``reason`` (a split does it)."""
    conn = uow.conn()
    ids = conn.execute(
        _OPEN_SQL, {"iwp": iwp_id, "open": CON_OPEN, "assigned": CON_ASSIGNED}
    ).scalars()
    events: list[Any] = []
    for constraint_id in [str(i) for i in ids]:
        if record_state(conn, constraint_id, CON_OPEN) in (CON_OPEN, CON_ASSIGNED):
            events.extend(move(uow, cmd, constraint_id, "void", reason).events)
    return events


__all__ = [
    "ConstraintRow",
    "RaiseResult",
    "aging_days_of",
    "assign_constraint",
    "clear_constraint",
    "constraint_age_days",
    "is_aging",
    "load_constraint",
    "need_by_default",
    "raise_constraint",
    "void_constraint",
    "void_open_constraints",
]
