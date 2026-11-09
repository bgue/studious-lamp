"""The rules of the core constraints and the four command handlers (ADR-0024 decisions 3 to 8).

A person's command (``handle_*``) and a module's call (``raise_constraint``,
``clear_constraint`` of the package) share one body. The person passes ``by_module=None``; a
module passes its name, which makes it the actor ``svc:<module>`` with source ``job:<module>``.
``by_module`` is a Python argument, never a field a client sets. Every id a command is given
goes through the viewer's filter: a record the viewer may not read answers as one that does not
exist, with the same words. A constraint is hidden when its subject is (the class is read from
the subject, never from the constraint). There is no ``system_view`` here.

R-P2-11, suppress after a person's clear: a check-raised constraint keeps the hash of its facts;
a person's clear of it needs a reason and keeps the hash (``suppress`` true); a module's own
clear drops it. A raise with the same subject and check name and an equal hash then writes
nothing and answers ``suppressed``; an open constraint of the same subject, phase and check name
answers ``exists``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy import Connection, text

from tl_core import confidentiality
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.constraints import guard
from tl_core.constraints.commands import (
    ACCESS_MODULE,
    ALL_SOURCES,
    CATEGORIES,
    EDIT_WORD,
    EV_ASSIGNED,
    EV_CLEARED,
    EV_RAISED,
    EV_WITHDRAWN,
    HASH_PATTERN,
    MAX_CHECK_NAME,
    MAX_REASON,
    MAX_REF_TEXT,
    MAX_TEXT,
    PHASE_PATTERN,
    RECORD_TYPE,
    REF_TYPES,
    SEVERITIES,
    SOURCE_CHECK,
    SOURCE_MANUAL,
    ST_ASSIGNED,
    ST_CLEARED,
    ST_OPEN,
    WAIVE_WORD,
    WORLD_TIME_PATTERN,
    AssignConstraint,
    ClearConstraint,
    RaiseConstraint,
    WithdrawConstraint,
)
from tl_core.constraints.errors import (
    MSG_WAIVE_WORD,
    ConstraintRuleError,
    ConstraintSourceError,
    ConstraintStateError,
    PhaseNotGatedError,
)
from tl_core.ledger import NewEvent
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import numbering_for
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoNumberingPatternError, RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow
from tl_core.workflow.provider import get_workflows

ConstraintAction = Literal["raised", "exists", "suppressed", "cleared"]

MSG_MODULE_ONLY = "a person raises only a manual constraint"
MSG_SOURCE = "the source is manual, check, rule, feed_hold or thread_hold"
MSG_CHECK_FIELDS = "a check constraint needs a check name and the hash of the facts"
MSG_CHECK_ONLY = "only a check constraint carries a check name or a hash"
MSG_OWNER = "the owner is not an account of this system"
MSG_OWNER_REQUIRED = "a manual constraint needs an owner"
MSG_FIELD = "the phase, severity, category or description is not valid"
MSG_DATE = "a date is YYYY-MM-DD and a time is YYYY-MM-DDTHH:MM:SSZ"
MSG_TARGET = "a constraint has a target record or a plain reference, not both"
MSG_REF = "a plain reference needs a type from the list and at most 60 characters of text"
MSG_NOT_GATED = "no guard of the subject's workflow names that phase"
MSG_CLEARED_BEFORE = "a constraint cannot be cleared before it began to hold things back"
MSG_REASON = "the reason is 1 to 300 characters"
MSG_OPEN_ONLY = "only an open or assigned constraint takes this command"
MSG_ASSIGN_OPEN = "only an open constraint can be assigned"
MSG_CLEAR_SOURCE = "a module clears only a constraint that was not raised by a person"
MSG_MODULE_NAME = "the module name is not valid"
MSG_PROJECT = "constraints belong to a project"

_HASH = re.compile(HASH_PATTERN)
_PHASE = re.compile(PHASE_PATTERN)
_WORLD = re.compile(WORLD_TIME_PATTERN)
_MODULE = re.compile(r"^[a-z][a-z0-9_.]{0,31}$")

_RECORD_SQL = text(
    "SELECT id, key, scope, type, voided, status, version FROM cur_core_record WHERE id = :id"
)
_ROW_SQL = text(
    "SELECT r.id, r.key, r.scope, r.voided, r.status, r.version, c.subject_id, c.source, "
    "c.check_name, c.effective_at FROM cur_core_constraint c JOIN cur_core_record r "
    "ON r.id = c.id WHERE c.id = :id"
)
_OPEN_SAME_SQL = text(
    "SELECT c.id FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.subject_id = :subject AND c.phase = :phase AND c.check_name = :check_name "
    "AND r.voided = :voided AND COALESCE(r.status, :open) IN (:open, :assigned) "
    "ORDER BY r.key, r.id LIMIT 1"
)
_SUPPRESSED_SQL = text(
    "SELECT c.id FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.subject_id = :subject AND c.check_name = :check_name AND c.suppress_hash = :hash "
    "AND r.status = :cleared AND r.voided = :voided ORDER BY r.key DESC, r.id DESC LIMIT 1"
)
_ACCOUNT_SQL = text("SELECT 1 FROM cur_account WHERE username = :name AND status = 'active'")
_KEY_TAKEN_SQL = text("SELECT 1 FROM cur_core_record WHERE scope = :scope AND key = :key")


@dataclass(frozen=True)
class _Ctx:
    """Who acts, as the ledger records it."""

    actor: str
    source: str
    scope: str
    correlation_id: str
    causation_id: str | None

    @staticmethod
    def of(cmd: Command) -> _Ctx:
        return _Ctx(
            cmd.actor, cmd.source, cmd.scope, cmd.correlation_id or new_ulid(), cmd.causation_id
        )

    @staticmethod
    def module(name: str, scope: str) -> _Ctx:
        if _MODULE.fullmatch(name) is None:
            raise ConstraintSourceError(MSG_MODULE_NAME)
        return _Ctx(f"svc:{name}", f"job:{name}", scope, new_ulid(), None)


@dataclass(frozen=True)
class _Held:
    id: str
    key: str
    scope: str
    state: str
    version: int
    subject_id: str
    source: str
    effective_at: str | None


# --- small helpers --------------------------------------------------------------------------


def parse_world_time(value: str) -> datetime:
    """A date or UTC timestamp as an aware datetime (a date is its midnight UTC)."""
    if _WORLD.fullmatch(value) is None:
        raise ConstraintRuleError(MSG_DATE)
    try:
        if "T" in value:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        day = date.fromisoformat(value)
    except ValueError:
        raise ConstraintRuleError(MSG_DATE) from None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _opt_time(value: str | None) -> str | None:
    if value is not None:
        parse_world_time(value)
    return value


def require_edit(conn: Connection, ctx: _Ctx) -> None:
    """The caller holds the word ``core.constraint.edit`` (table word ``user``) on the project."""
    require_word(
        conn,
        holder_for_actor(conn, ctx.actor),
        scope=ctx.scope,
        module=ACCESS_MODULE,
        word=normalise_word(EDIT_WORD),
        what=EDIT_WORD,
    )


def require_waive(conn: Connection, ctx: _Ctx) -> None:
    """The caller holds the word ``core.constraint.waive`` (table word ``controller``) here.

    The refusal is the fixed ``MSG_WAIVE_WORD``; it says nothing of the constraint."""
    try:
        require_word(
            conn,
            holder_for_actor(conn, ctx.actor),
            scope=ctx.scope,
            module=ACCESS_MODULE,
            word=normalise_word(WAIVE_WORD),
            what=WAIVE_WORD,
        )
    except ForbiddenError:
        raise ForbiddenError(MSG_WAIVE_WORD) from None


def _version(uow: UnitOfWork, record_id: str) -> int:
    found = uow.conn().execute(
        text("SELECT version FROM cur_core_record WHERE id = :id"), {"id": record_id}
    )
    return int(found.scalar_one())


def _visible(uow: UnitOfWork, record_id: str, scopes: tuple[str, ...]) -> Any:
    """The envelope row of a record the viewer may read, live, in one of ``scopes``; otherwise
    ``RecordNotFoundError`` (one text for hidden, absent, voided and foreign)."""
    conn = uow.conn()
    confidentiality.require_visible(conn, record_id)
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or bool(row.voided) or row.scope not in scopes:
        raise RecordNotFoundError(f"no record {record_id!r}")
    return row


def _load(uow: UnitOfWork, constraint_id: str, scope: str | None) -> _Held:
    """The constraint. Its class is the subject's, by join at read time: a constraint whose subject
    the viewer may not read does not exist for them."""
    conn = uow.conn()
    row = conn.execute(_ROW_SQL, {"id": constraint_id}).first()
    if (
        row is None
        or bool(row.voided)
        or (scope is not None and row.scope != scope)
        or confidentiality.is_hidden(conn, str(row.subject_id))
    ):
        raise RecordNotFoundError(f"no record {constraint_id!r}")
    return _Held(
        id=str(row.id),
        key=str(row.key or ""),
        scope=str(row.scope),
        state=str(row.status or ST_OPEN),
        version=int(row.version),
        subject_id=str(row.subject_id),
        source=str(row.source),
        effective_at=None if row.effective_at is None else str(row.effective_at),
    )


def _check_owner(conn: Connection, owner: str) -> None:
    kind, _, name = owner.partition(":")
    if kind != "user" or not name or conn.execute(_ACCOUNT_SQL, {"name": name}).first() is None:
        raise ConstraintRuleError(MSG_OWNER)


def _append(uow: UnitOfWork, ctx: _Ctx, record_id: str, events: list[NewEvent]) -> Any:
    return uow.append(
        stream_id=record_id,
        stream_type=RECORD_TYPE,
        scope=ctx.scope,
        expected_version=_version(uow, record_id),
        events=events,
        actor=ctx.actor,
        source=ctx.source,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
    )


def _move(
    uow: UnitOfWork, ctx: _Ctx, record_id: str, transition: str, reason: str | None = None
) -> CommandResult:
    return handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=ctx.actor,
            source=ctx.source,
            scope=ctx.scope,
            correlation_id=ctx.correlation_id,
            causation_id=ctx.causation_id,
            stream_id=record_id,
            expected_version=_version(uow, record_id),
            transition=transition,
            reason=reason,
        ),
        by_module=True,
    )


def _link(uow: UnitOfWork, ctx: _Ctx, from_id: str, to_id: str, relation: str) -> list[Any]:
    added = handle_add_link(
        uow,
        AddLink(
            actor=ctx.actor,
            source=ctx.source,
            scope=ctx.scope,
            correlation_id=ctx.correlation_id,
            causation_id=ctx.causation_id,
            from_id=from_id,
            to_id=to_id,
            relation=relation,
            link_source="rule",
        ),
        by_module=True,
    )
    return list(added.events)


def _new_key(uow: UnitOfWork, ctx: _Ctx, stream_id: str) -> str:
    pattern = numbering_for(uow.conn()).find(ctx.scope, RECORD_TYPE)
    if pattern is None:
        raise NoNumberingPatternError(f"no numbering pattern for {RECORD_TYPE!r} in {ctx.scope!r}")
    conn = uow.conn()
    return allocate_key(
        uow,
        pattern=pattern,
        scope=ctx.scope,
        values=segment_values(pattern, ctx.scope, None),
        record_id=stream_id,
        record_type=RECORD_TYPE,
        actor=ctx.actor,
        source=ctx.source,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        is_taken=lambda key: (
            conn.execute(_KEY_TAKEN_SQL, {"scope": ctx.scope, "key": key}).first() is not None
        ),
    ).key


# --- raise ----------------------------------------------------------------------------------


def _validate_fields(
    *,
    phase: str,
    severity: str,
    category: str,
    source: str,
    check_name: str | None,
    facts_hash: str | None,
    description: str | None,
    by_module: bool,
) -> None:
    if source not in ALL_SOURCES:
        raise ConstraintRuleError(MSG_SOURCE)
    if source != SOURCE_MANUAL and not by_module:
        raise ConstraintSourceError(MSG_MODULE_ONLY)
    if source == SOURCE_CHECK:
        if (
            not check_name
            or len(check_name) > MAX_CHECK_NAME
            or not facts_hash
            or _HASH.fullmatch(facts_hash) is None
        ):
            raise ConstraintRuleError(MSG_CHECK_FIELDS)
    elif check_name is not None or facts_hash is not None:
        raise ConstraintRuleError(MSG_CHECK_ONLY)
    if (
        _PHASE.fullmatch(phase) is None
        or severity not in SEVERITIES
        or category not in CATEGORIES
        or (description is not None and not 1 <= len(description) <= MAX_TEXT)
        or (description is not None and not description.strip())
    ):
        raise ConstraintRuleError(MSG_FIELD)


def _validate_target(
    target_id: str | None, ref_type: str | None, ref_text: str | None
) -> Literal["record", "reference"] | None:
    if target_id is not None and (ref_type is not None or ref_text is not None):
        raise ConstraintRuleError(MSG_TARGET)
    if target_id is not None:
        return "record"
    if ref_type is None and ref_text is None:
        return None
    if ref_type not in REF_TYPES or (
        ref_text is not None and not 1 <= len(ref_text) <= MAX_REF_TEXT
    ):
        raise ConstraintRuleError(MSG_REF)
    return "reference"


def _raise(
    uow: UnitOfWork,
    *,
    actor: _Ctx | None,
    by_module: str | None,
    subject_id: str,
    phase: str,
    severity: str,
    category: str,
    source: str,
    check_name: str | None,
    facts_hash: str | None,
    owner: str | None,
    description: str | None,
    due_at: str | None,
    effective_at: str | None,
    target_id: str | None,
    target_ref_type: str | None,
    target_ref_text: str | None,
) -> tuple[CommandResult | None, str | None, str | None, ConstraintAction]:
    """The body shared by the command and the module function: ``(result, id, key, action)``."""
    _validate_fields(
        phase=phase,
        severity=severity,
        category=category,
        source=source,
        check_name=check_name,
        facts_hash=facts_hash,
        description=description,
        by_module=by_module is not None,
    )
    _opt_time(due_at)
    _opt_time(effective_at)
    kind = _validate_target(target_id, target_ref_type, target_ref_text)
    conn = uow.conn()
    scope_row = conn.execute(_RECORD_SQL, {"id": subject_id}).first()
    if actor is None:
        # a module names no scope: the subject's own scope is the constraint's
        if scope_row is None:
            raise RecordNotFoundError(f"no record {subject_id!r}")
        assert by_module is not None
        ctx = _Ctx.module(by_module, str(scope_row.scope))
    else:
        ctx = actor
    if not ctx.scope.startswith("project:"):
        raise ConstraintRuleError(MSG_PROJECT)
    if by_module is None:
        require_edit(conn, ctx)
    subject = _visible(uow, subject_id, (ctx.scope,))
    if owner is None and source == SOURCE_MANUAL:
        raise ConstraintRuleError(MSG_OWNER_REQUIRED)
    if owner is not None:
        _check_owner(conn, owner)
    if severity == "blocking":
        definition = get_workflows().find(str(subject.type), str(subject.scope))
        if definition is None or phase not in guard.gated_phases(definition):
            raise PhaseNotGatedError(MSG_NOT_GATED)
    if target_id is not None:
        _visible(uow, target_id, (ctx.scope, "company"))
    if check_name is not None:
        held = conn.execute(
            _OPEN_SAME_SQL,
            {
                "subject": subject_id,
                "phase": phase,
                "check_name": check_name,
                "voided": False,
                "open": ST_OPEN,
                "assigned": ST_ASSIGNED,
            },
        ).scalar_one_or_none()
        if held is not None:
            return None, str(held), _key_of(conn, str(held)), "exists"
        prior = conn.execute(
            _SUPPRESSED_SQL,
            {
                "subject": subject_id,
                "check_name": check_name,
                "hash": facts_hash,
                "cleared": ST_CLEARED,
                "voided": False,
            },
        ).scalar_one_or_none()
        if prior is not None:
            return None, str(prior), _key_of(conn, str(prior)), "suppressed"
    stream_id = new_ulid()
    key = _new_key(uow, ctx, stream_id)
    title = (description or category)[:200].strip() or category
    payload: dict[str, Any] = {
        "constraint_id": stream_id,
        "subject_id": subject_id,
        "phase": phase,
        "severity": severity,
        "category": category,
        "source": source,
        "owner": owner,
        "description": description,
        "check_name": check_name,
        "facts_hash": facts_hash,
        "effective_at": effective_at,
        "due_at": due_at,
        "target_kind": kind,
        "target_id": target_id,
        "target_ref_type": target_ref_type,
        "target_ref_text": target_ref_text,
    }
    written = uow.append(
        stream_id=stream_id,
        stream_type=RECORD_TYPE,
        scope=ctx.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={
                    "record_type": RECORD_TYPE,
                    "key": key,
                    "title": title,
                    "description": description,
                    "psets": {},
                },
            ),
            NewEvent(event_type=EV_RAISED, payload=payload),
        ],
        actor=ctx.actor,
        source=ctx.source,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
    )
    events = list(written.events)
    events.extend(_link(uow, ctx, stream_id, subject_id, "blocks"))
    if target_id is not None:
        events.extend(_link(uow, ctx, stream_id, target_id, "targets"))
    result = CommandResult(stream_id=stream_id, key=key, version=written.new_version, events=events)
    return result, stream_id, key, "raised"


def _key_of(conn: Connection, record_id: str) -> str | None:
    found = conn.execute(text("SELECT key FROM cur_core_record WHERE id = :id"), {"id": record_id})
    value = found.scalar_one_or_none()
    return None if value is None else str(value)


def handle_raise_constraint(uow: UnitOfWork, cmd: RaiseConstraint) -> CommandResult:
    """A person's raise: ``manual`` only (``ConstraintSourceError`` otherwise); needs the word
    ``core.constraint.edit``; the subject and the target must be visible to the actor."""
    result, _id, _key, _action = _raise(
        uow,
        actor=_Ctx.of(cmd),
        by_module=None,
        subject_id=cmd.subject,
        phase=cmd.phase,
        severity=cmd.severity,
        category=cmd.category,
        source=cmd.source_kind,
        check_name=cmd.check_name,
        facts_hash=cmd.facts_hash,
        owner=cmd.owner,
        description=cmd.description,
        due_at=cmd.due_at,
        effective_at=cmd.effective_at,
        target_id=cmd.target,
        target_ref_type=cmd.target_ref_type,
        target_ref_text=cmd.target_ref_text,
    )
    assert result is not None  # a person raises manual: no check name, so never exists/suppressed
    return result


# --- assign, clear, withdraw ----------------------------------------------------------------


def handle_assign_constraint(uow: UnitOfWork, cmd: AssignConstraint) -> CommandResult:
    """Open to Assigned with a new owner: ``Constraint.Assigned`` and ``Workflow.Transitioned``."""
    ctx = _Ctx.of(cmd)
    conn = uow.conn()
    require_edit(conn, ctx)
    held = _load(uow, cmd.constraint, ctx.scope)
    if held.state != ST_OPEN:
        raise ConstraintStateError(MSG_ASSIGN_OPEN)
    _check_owner(conn, cmd.owner)
    done = _append(
        uow,
        ctx,
        held.id,
        [NewEvent(event_type=EV_ASSIGNED, payload={"constraint_id": held.id, "owner": cmd.owner})],
    )
    moved = _move(uow, ctx, held.id, "assign")
    return CommandResult(
        stream_id=held.id, key=held.key, version=moved.version, events=[*done.events, *moved.events]
    )


def _clear(
    uow: UnitOfWork,
    ctx: _Ctx,
    *,
    by_module: bool,
    constraint_id: str,
    reason: str,
    cleared_at: str | None,
    resolved_by: str | None,
) -> CommandResult:
    if not reason.strip() or len(reason) > MAX_REASON:
        raise ConstraintRuleError(MSG_REASON)
    conn = uow.conn()
    if not by_module:
        require_edit(conn, ctx)
    held = _load(uow, constraint_id, ctx.scope)
    if by_module and held.source == SOURCE_MANUAL:
        raise ConstraintSourceError(MSG_CLEAR_SOURCE)
    if not by_module and held.source == SOURCE_CHECK:
        require_waive(conn, ctx)  # after _load: a hidden constraint answers as missing first
    if held.state not in (ST_OPEN, ST_ASSIGNED):
        raise ConstraintStateError(MSG_OPEN_ONLY)
    when = cleared_at if cleared_at is not None else utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = parse_world_time(when)
    if held.effective_at is not None and stamp < parse_world_time(held.effective_at):
        raise ConstraintRuleError(MSG_CLEARED_BEFORE)
    if resolved_by is not None:
        _visible(uow, resolved_by, (ctx.scope, "company"))
    suppress = not by_module and held.source == SOURCE_CHECK
    cleared = _append(
        uow,
        ctx,
        held.id,
        [
            NewEvent(
                event_type=EV_CLEARED,
                payload={
                    "constraint_id": held.id,
                    "cleared_at": when,
                    "cleared_by": ctx.actor,
                    "reason": reason,
                    "resolved_by": resolved_by,
                    "suppress": suppress,
                },
            )
        ],
    )
    events = list(cleared.events)
    if resolved_by is not None:
        events.extend(_link(uow, ctx, resolved_by, held.id, "resolves"))
    moved = _move(uow, ctx, held.id, "clear", reason)
    events.extend(moved.events)
    return CommandResult(stream_id=held.id, key=held.key, version=moved.version, events=events)


def handle_clear_constraint(uow: UnitOfWork, cmd: ClearConstraint) -> CommandResult:
    """A person's clear: needs a reason; a clear of a check-raised constraint keeps the hash."""
    return _clear(
        uow,
        _Ctx.of(cmd),
        by_module=False,
        constraint_id=cmd.constraint,
        reason=cmd.reason,
        cleared_at=cmd.cleared_at,
        resolved_by=cmd.resolved_by,
    )


def handle_withdraw_constraint(uow: UnitOfWork, cmd: WithdrawConstraint) -> CommandResult:
    """Open or assigned to Withdrawn: ``Constraint.Withdrawn`` and ``Workflow.Transitioned``."""
    ctx = _Ctx.of(cmd)
    if not cmd.reason.strip() or len(cmd.reason) > MAX_REASON:
        raise ConstraintRuleError(MSG_REASON)
    require_edit(uow.conn(), ctx)
    held = _load(uow, cmd.constraint, ctx.scope)
    if held.state not in (ST_OPEN, ST_ASSIGNED):
        raise ConstraintStateError(MSG_OPEN_ONLY)
    done = _append(
        uow,
        ctx,
        held.id,
        [
            NewEvent(
                event_type=EV_WITHDRAWN, payload={"constraint_id": held.id, "reason": cmd.reason}
            )
        ],
    )
    moved = _move(uow, ctx, held.id, "withdraw", cmd.reason)
    return CommandResult(
        stream_id=held.id, key=held.key, version=moved.version, events=[*done.events, *moved.events]
    )


def clear_by_module(
    uow: UnitOfWork,
    *,
    constraint_id: str,
    reason: str,
    by_module: str,
    cleared_at: str | None,
    resolved_by: str | None,
) -> tuple[str, str | None]:
    """A module's clear: only a constraint that is not ``manual``; ``(id, key)`` of the cleared."""
    scope = (
        uow.conn()
        .execute(text("SELECT scope FROM cur_core_record WHERE id = :id"), {"id": constraint_id})
        .scalar_one_or_none()
    )
    if scope is None:
        raise RecordNotFoundError(f"no record {constraint_id!r}")
    result = _clear(
        uow,
        _Ctx.module(by_module, str(scope)),
        by_module=True,
        constraint_id=constraint_id,
        reason=reason,
        cleared_at=cleared_at,
        resolved_by=resolved_by,
    )
    return result.stream_id, result.key


def raise_by_module(
    uow: UnitOfWork,
    *,
    subject_id: str,
    phase: str,
    severity: str,
    category: str,
    source: str,
    check_name: str | None,
    facts_hash: str | None,
    by_module: str,
    owner: str | None,
    description: str | None,
    due_at: str | None,
    effective_at: str | None,
    target_id: str | None,
    target_ref_type: str | None,
    target_ref_text: str | None,
) -> tuple[str | None, str | None, ConstraintAction]:
    """A module's raise: ``(id, key, action)`` with action raised, exists or suppressed."""
    _result, cid, key, action = _raise(
        uow,
        actor=None,
        by_module=by_module,
        subject_id=subject_id,
        phase=phase,
        severity=severity,
        category=category,
        source=source,
        check_name=check_name,
        facts_hash=facts_hash,
        owner=owner,
        description=description,
        due_at=due_at,
        effective_at=effective_at,
        target_id=target_id,
        target_ref_type=target_ref_type,
        target_ref_text=target_ref_text,
    )
    return cid, key, action
