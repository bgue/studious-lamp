"""Weekly plan commands: open a week, commit IWPs to it, record outcomes, close it with the PPC.

The plan is one record per project and ISO week, keyed ``<project>-WK-<year>W<ww>`` (no
allocator). Draft to Committed on the first commitment, Committed to Closed on ``CloseWeek``, both
moves made by the module. An outcome may be corrected until the plan is Closed (a new event, never
an edit). The handlers never read ``intent`` (ADR-0025). Fixed messages, never a cell of the input.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import CommandResult
from tl_core.services.errors import DuplicateKeyError
from tl_core.services.records import create_module_record
from tl_core.settings.layers import project_of_scope
from tl_core.uow import UnitOfWork
from tl_mod_engineering import codelists
from tl_mod_engineering.errors import UnknownCodeListError

from tl_mod_awp.common import (
    append,
    correlated,
    load_record,
    move,
    record_state,
    require_project,
    silent,
    version_of,
)
from tl_mod_awp.errors import StaleVersionError, WeekRuleError, WeekStateError
from tl_mod_awp.handlers.iwp import load_iwp
from tl_mod_awp.names import (
    IWP_IN_PROGRESS,
    IWP_ISSUED,
    OUTCOME_DONE,
    OUTCOME_MISSED,
    WEEK_CLOSED,
    WEEK_CLOSED_STATE,
    WEEK_COMMITMENT_TABLE,
    WEEK_COMMITTED,
    WEEK_DRAFT,
    WEEK_IWP_COMMITTED,
    WEEK_OPENED,
    WEEK_OUTCOME_RECORDED,
    WEEKLY_PLAN,
    WEEKLY_PLAN_TABLE,
)
from tl_mod_awp.progress import engine

if TYPE_CHECKING:
    from tl_mod_awp.commands import (
        CloseWeek,
        CommitIwpToWeek,
        OpenWeeklyPlan,
        RecordWeekOutcome,
    )

MSG_STALE = "the record changed since it was read"
MSG_OPEN = "weekly plan: week already open"
MSG_NOTHING = "weekly plan: nothing committed"
MSG_OUTCOMES = "weekly plan: outcomes missing"
MSG_CLOSED = "weekly plan: a closed week takes no more commands"
MSG_NOT_COMMITTED = "weekly plan: the week is not committed yet"
MSG_IWP_STATE = "weekly plan: only an issued or in-progress package can be committed"
MSG_NOT_IN_PLAN = "weekly plan: the package is not committed in this week"
MSG_REASON_NEEDED = "weekly plan: a missed commitment needs a reason"
MSG_REASON_UNKNOWN = "weekly plan: the reason is not a miss reason"
MSG_REASON_DONE = "weekly plan: a done commitment takes no reason"
MSG_HOURS = "committed hours is a number above 0 and at most 9999999999.9, one decimal"

MAX_COMMITTED = Decimal("9999999999.9")
_HOURS = re.compile(r"[0-9]{1,10}(?:\.[0-9])?", re.ASCII)
MISS_REASON_LIST = "MissReason"

_KEY_TAKEN = text(
    "SELECT 1 FROM cur_core_record WHERE scope = :scope AND type = :type AND key = :key"
)
_WEEK_TAKEN = text(f"SELECT 1 FROM {WEEKLY_PLAN_TABLE} WHERE scope = :scope AND week = :week")
_COMMITMENTS = text(
    f"SELECT iwp_id, outcome FROM {WEEK_COMMITMENT_TABLE} WHERE plan_id = :plan ORDER BY iwp_id"
)


def parse_week_hours(value: str) -> str:
    """Committed hours above 0 and at most 9999999999.9, as text with one decimal."""
    if _HOURS.fullmatch(value) is None:
        raise ValueError(MSG_HOURS)
    hours = Decimal(value)
    if hours <= 0 or hours > MAX_COMMITTED:
        raise ValueError(MSG_HOURS)
    return f"{hours:.1f}"


def iso_week(day: date) -> tuple[date, str, str]:
    """``(Monday, "YYYY-Www", "YYYYWww")`` of the ISO week of ``day``."""
    monday = day - timedelta(days=day.weekday())
    year, week, _ = monday.isocalendar()
    return monday, f"{year}-W{week:02d}", f"{year}W{week:02d}"


def miss_reasons(conn: Connection, scope: str) -> list[str]:
    """Keys of the code list ``MissReason`` of the adopted edition (none when it is not adopted)."""
    try:
        found = codelists.values(conn, scope, MISS_REASON_LIST)
    except UnknownCodeListError:
        return []
    return [r.code for r in found]


def _now() -> datetime:
    return datetime.now(UTC)


def _fresh(actual: int, expected: int) -> None:
    if actual != expected:
        raise StaleVersionError(MSG_STALE)


def _event(kind: str, payload: dict[str, Any], at: datetime, *, card: bool = False) -> NewEvent:
    body = {**payload, "at": iso_utc(at)}
    return NewEvent(event_type=kind, payload=body if card else silent(body), effective_at=at)


class _Plan:
    def __init__(self, id: str, key: str | None, version: int, state: str) -> None:
        self.id = id
        self.key = key
        self.version = version
        self.state = state


def _load_plan(uow: UnitOfWork, cmd: Any) -> _Plan:
    ref = load_record(uow, cmd.scope, cmd.plan_id, WEEKLY_PLAN)
    plan = _Plan(
        ref.id,
        ref.key,
        version_of(uow, ref.id),
        record_state(uow.conn(), ref.id, WEEK_DRAFT),
    )
    _fresh(plan.version, cmd.expected_version)
    if plan.state == WEEK_CLOSED_STATE:
        raise WeekStateError(MSG_CLOSED)
    return plan


def _commitments(conn: Connection, plan_id: str) -> dict[str, str | None]:
    return {str(r.iwp_id): r.outcome for r in conn.execute(_COMMITMENTS, {"plan": plan_id})}


def handle_open_weekly_plan(uow: UnitOfWork, cmd: OpenWeeklyPlan) -> CommandResult:
    """Open the plan of the week of ``week_start`` (any day; its Monday is kept). Raises
    ``WeekRuleError`` when the week already has a plan."""
    require_project(cmd)
    cmd = correlated(cmd)
    monday, week, compact = iso_week(cmd.week_start)
    key = f"{project_of_scope(cmd.scope)}-WK-{compact}"
    conn = uow.conn()
    if (
        conn.execute(_WEEK_TAKEN, {"scope": cmd.scope, "week": week}).first() is not None
        or conn.execute(_KEY_TAKEN, {"scope": cmd.scope, "type": WEEKLY_PLAN, "key": key}).first()
        is not None
    ):
        raise WeekRuleError(MSG_OPEN)
    at = _now()
    try:
        return create_module_record(
            uow,
            cmd,
            record_type=WEEKLY_PLAN,
            title=f"Week {week}",
            key=key,
            composed_key=True,
            extra_events=[
                _event(WEEK_OPENED, {"week": week, "week_start": monday.isoformat()}, at)
            ],
        )
    except DuplicateKeyError:
        raise WeekRuleError(MSG_OPEN) from None


def handle_commit_iwp_to_week(uow: UnitOfWork, cmd: CommitIwpToWeek) -> CommandResult:
    """Commit an Issued or In progress IWP to a Draft or Committed plan; a second commit of the
    same IWP replaces the first. The first commitment moves the plan to Committed."""
    require_project(cmd)
    cmd = correlated(cmd)
    plan = _load_plan(uow, cmd)
    iwp = load_iwp(uow, cmd.scope, cmd.iwp_id)
    if iwp.state not in (IWP_ISSUED, IWP_IN_PROGRESS):
        raise WeekStateError(MSG_IWP_STATE)
    foreman = cmd.foreman or iwp.foreman or cmd.actor
    at = _now()
    done = append(
        uow,
        cmd,
        plan.id,
        WEEKLY_PLAN,
        [
            _event(
                WEEK_IWP_COMMITTED,
                {
                    "iwp_id": iwp.id,
                    "foreman": foreman,
                    "committed_hours": parse_week_hours(cmd.committed_hours),
                },
                at,
            )
        ],
    )
    events = list(done.events)
    version = done.new_version
    if plan.state == WEEK_DRAFT:
        moved = move(uow, cmd, plan.id, "commit")
        events.extend(moved.events)
        version = moved.version
    return CommandResult(stream_id=plan.id, key=plan.key, version=version, events=events)


def handle_record_week_outcome(uow: UnitOfWork, cmd: RecordWeekOutcome) -> CommandResult:
    """Record done, or missed with a reason, for a committed IWP; correctable until Closed."""
    require_project(cmd)
    cmd = correlated(cmd)
    plan = _load_plan(uow, cmd)
    if plan.state != WEEK_COMMITTED:
        raise WeekStateError(MSG_NOT_COMMITTED)
    conn = uow.conn()
    if cmd.iwp_id not in _commitments(conn, plan.id):
        raise WeekRuleError(MSG_NOT_IN_PLAN)
    if cmd.outcome == OUTCOME_MISSED:
        if cmd.miss_reason is None:
            raise WeekRuleError(MSG_REASON_NEEDED)
        if cmd.miss_reason not in miss_reasons(conn, cmd.scope):
            raise WeekRuleError(MSG_REASON_UNKNOWN)
    elif cmd.miss_reason is not None:
        raise WeekRuleError(MSG_REASON_DONE)
    done = append(
        uow,
        cmd,
        plan.id,
        WEEKLY_PLAN,
        [
            _event(
                WEEK_OUTCOME_RECORDED,
                {"iwp_id": cmd.iwp_id, "outcome": cmd.outcome, "miss_reason": cmd.miss_reason},
                _now(),
            )
        ],
    )
    return CommandResult(
        stream_id=plan.id, key=plan.key, version=done.new_version, events=list(done.events)
    )


def handle_close_week(uow: UnitOfWork, cmd: CloseWeek) -> CommandResult:
    """Close a Committed plan whose every commitment has an outcome; writes the PPC."""
    require_project(cmd)
    cmd = correlated(cmd)
    plan = _load_plan(uow, cmd)
    held = _commitments(uow.conn(), plan.id)
    if not held:
        raise WeekRuleError(MSG_NOTHING)
    if plan.state != WEEK_COMMITTED:
        raise WeekStateError(MSG_NOT_COMMITTED)
    if any(outcome is None for outcome in held.values()):
        raise WeekRuleError(MSG_OUTCOMES)
    value, _ = engine.ppc(sum(1 for o in held.values() if o == OUTCOME_DONE), len(held))
    if value is None:  # unreachable: held is not empty
        raise WeekRuleError(MSG_NOTHING)
    done = append(
        uow,
        cmd,
        plan.id,
        WEEKLY_PLAN,
        [_event(WEEK_CLOSED, {"ppc": f"{value:.1f}"}, _now(), card=True)],
    )
    moved = move(uow, cmd, plan.id, "close")
    return CommandResult(
        stream_id=plan.id,
        key=plan.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


__all__ = [
    "handle_close_week",
    "handle_commit_iwp_to_week",
    "handle_open_weekly_plan",
    "handle_record_week_outcome",
    "miss_reasons",
    "parse_week_hours",
]
