"""Response-clock commands: start, pause, resume, restart, meet, cancel, sweep (brief 9 M10).

Every figure of a clock comes from its events and the calendar version named in its first event
(D4). A handler replays the clock's events with ``clocks.replay`` plus the event it is about to
append: if the engine refuses the result (a date that moves back, an event the state does not allow,
a due date that differs from the engine's), nothing is appended and the caller gets
``ClockStateError``. Time comes only from ``today()`` (the injectable clock), and a date a caller
states is today or earlier, with a reason when it is earlier.

``start_clock`` is the one place a clock record is made; triage, issue and the person's own
``StartClock`` all call it. ``sweep_clocks`` records ``Warned`` and ``Expired`` for the clocks it
may read; the scheduled sweep runs as the system and so reaches them all.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.calendars import CalendarError
from tl_mod_correspondence.clocks import (
    ClockReplayError,
    Fact,
    Figures,
    check_params,
    check_warn_days,
    days_left,
    replay,
    resume_due,
    warning_to_raise,
)
from tl_mod_correspondence.errors import (
    CalendarUnavailableError,
    ClockStateError,
    InvalidClockError,
    ItemStateError,
)
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    open_item,
    require_project,
    resolve_date,
    today,
    today_date,
)
from tl_mod_correspondence.limits import (
    MAX_CLOCKS_PER_ITEM,
    MAX_DURATION_DAYS,
    MAX_NUMBER,
    MAX_REASON,
    MAX_TEXT,
    MAX_WARNINGS,
)
from tl_mod_correspondence.names import (
    CLOCK,
    CLOCK_CANCELLED,
    CLOCK_EXPIRED,
    CLOCK_MET,
    CLOCK_PAUSED,
    CLOCK_RESTARTED,
    CLOCK_RESUMED,
    CLOCK_STARTED,
    CLOCK_WARNED,
)

log = logging.getLogger(__name__)

ClockKind = Literal["response_from_them", "response_from_us", "time_bar"]
DayType = Literal["calendar", "working"]
Trigger = Literal["receipt", "issue", "triage", "manual"]


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class StartClock(Command):
    """Start a response clock on an item that takes changes (any signed-in person's act).

    The count starts on ``start_on`` (today by default; an earlier day needs ``start_reason``),
    runs ``duration_days`` calendar or working days on the project's calendar, and warns at each
    threshold of ``warn_days`` (days before the due date) when the sweep runs. A contract clause,
    when named, must be active.
    """

    model_config = ConfigDict(extra="forbid")

    item_id: str
    label: str = Field(min_length=1, max_length=MAX_TEXT)
    kind: ClockKind = "response_from_them"
    duration_days: int = Field(ge=1, le=MAX_DURATION_DAYS)
    day_type: DayType = "calendar"
    warn_days: list[int] = Field(default_factory=list, max_length=MAX_WARNINGS)
    start_on: str | None = Field(default=None, max_length=10)
    start_reason: str | None = Field(default=None, max_length=MAX_REASON)
    owner: str | None = Field(default=None, max_length=MAX_NUMBER)
    clause_id: str | None = Field(default=None, max_length=MAX_NUMBER)

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        return _non_blank(value)


class _ClockAct(Command):
    model_config = ConfigDict(extra="forbid")

    clock_id: str
    on: str | None = Field(default=None, max_length=10, description="The day; default today.")


class PauseClock(_ClockAct):
    """Pause a running clock: the days of the pause do not count. A reason is required."""

    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class ResumeClock(_ClockAct):
    """Run a paused clock again; its due date moves by the days of the pause.

    A resume dated before today needs a ``reason``.
    """

    reason: str | None = Field(default=None, max_length=MAX_REASON)


class RestartClock(_ClockAct):
    """Count again from a new day zero with the same parameters (an extension, a new notice).

    ``on`` is the new day zero. A closed, expired or paused clock runs again; the warnings are
    forgotten. A reason is required.
    """

    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class MeetClock(_ClockAct):
    """Close a clock because the answer came (in time or late: the date says which).

    ``response_id`` names the answering item when there is one; ``reason`` says how it was met.
    """

    response_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class CancelClock(_ClockAct):
    """Close a clock because no answer is needed any more. A reason is required."""

    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class SweepClocks(Command):
    """Record the warnings and expiries that are due (a document controller's act, or the job).

    For each running clock the viewer may read: ``Expired`` when today is past its due date,
    otherwise ``Warned`` for the smallest warning threshold it has crossed and not yet raised.
    Safe to repeat on the same day: it records nothing twice. ``on`` judges as of that day
    (never later than today).
    """

    model_config = ConfigDict(extra="forbid")

    on: str | None = Field(default=None, max_length=10)


# --- the engine on the ledger ----------------------------------------------------------------


def load_clock(uow: UnitOfWork, cmd: Command, clock_id: str) -> registry.ClockRow:
    """The clock in the command's scope that the viewer may read.

    A clock hangs on its item, so one the viewer may not read answers like a missing one: the same
    ``RecordNotFoundError`` as an unknown id (ADR-0016).
    """
    found = registry.get_clock(uow.conn(), clock_id)
    if found is None or found.scope != cmd.scope:
        raise RecordNotFoundError(f"no record {clock_id!r}")
    return found


def figures_of(uow: UnitOfWork, clock: registry.ClockRow) -> tuple[list[Fact], Figures]:
    """The clock's events and what they add up to. Raises ``ClockStateError`` when the engine
    refuses the history (a forged event, a changed calendar file)."""
    facts = registry.clock_facts(uow.conn(), clock.id)
    calendar = catalog.calendar_for(clock.calendar, clock.scope)
    try:
        return facts, replay(facts, calendar)
    except ClockReplayError as exc:
        raise ClockStateError(f"clock {clock.id} cannot be recomputed: {exc}") from exc


def _day(cmd_on: str | None, reason: str | None, what: str) -> tuple[str, str | None]:
    """Today, or the day the caller states (never later than today; earlier needs a reason)."""
    if cmd_on is not None:
        try:
            date.fromisoformat(cmd_on)
        except ValueError as exc:
            raise InvalidClockError(
                f"{what} must be a date written YYYY-MM-DD: {cmd_on!r}"
            ) from exc
    return resolve_date(cmd_on, reason, what)


def _check_with(facts: Sequence[Fact], fact: Fact, clock: registry.ClockRow) -> Figures:
    """The figures after ``fact``: the engine must accept the whole history."""
    calendar = catalog.calendar_for(clock.calendar, clock.scope)
    try:
        return replay([*facts, fact], calendar)
    except ClockReplayError as exc:
        raise ClockStateError(f"{exc}") from exc
    except CalendarError as exc:
        raise CalendarUnavailableError(str(exc)) from exc


def _result(clock: registry.ClockRow, done: Any) -> CommandResult:
    return CommandResult(
        stream_id=clock.id, key=clock.item_number, version=done.new_version, events=done.events
    )


def start_clock(
    uow: UnitOfWork,
    cmd: Command,
    *,
    item: registry.ItemRow,
    label: str,
    kind: str,
    duration_days: int,
    day_type: str,
    warn_days: Sequence[int],
    start_on: str,
    trigger: str,
    owner: str | None = None,
    clause_id: str | None = None,
    calendar_ref: str | None = None,
) -> CommandResult:
    """Create a clock record for ``item``: ``Record.Created`` then ``ResponseClock.Started``.

    ``start_on`` is already judged by the caller (today or an explained earlier day). The due date
    is the engine's, on the named calendar (the project's default when none is named). Raises
    ``InvalidClockError`` (a length, type or threshold), ``CalendarUnavailableError`` (no such
    calendar, or the count leaves its range) and ``ItemStateError`` (too many clocks).
    """
    try:
        check_params(duration_days, day_type)
        warn = check_warn_days(list(warn_days), duration_days)
        first = date.fromisoformat(start_on)
    except ValueError as exc:
        raise InvalidClockError(str(exc)) from exc
    existing = registry.clocks_of(uow.conn(), item.id)
    if len(existing) >= MAX_CLOCKS_PER_ITEM:
        raise ItemStateError(f"item {item.number} already has {MAX_CLOCKS_PER_ITEM} clocks")
    if clause_id is not None:
        clause = registry.get_clause(uow.conn(), clause_id)
        if clause is None or clause.scope != cmd.scope or not clause.is_active:
            raise InvalidClockError(f"clause {clause_id!r} is not an active clause of {cmd.scope}")
    ref = calendar_ref or catalog.default_calendar_ref(cmd.scope)
    calendar = catalog.calendar_for(ref, cmd.scope)
    due = catalog.due_for(calendar, first, duration_days, day_type)
    return create_module_record(
        uow,
        cmd,
        record_type=CLOCK,
        title=label,
        key=f"{item.number}-C{len(existing) + 1:02d}",
        extra_events=[
            NewEvent(
                event_type=CLOCK_STARTED,
                payload={
                    "item_id": item.id,
                    "item_number": item.number,
                    "label": label,
                    "kind": kind,
                    "start_on": start_on,
                    "duration_days": duration_days,
                    "day_type": day_type,
                    "calendar": calendar.ref,
                    "warn_days": list(warn),
                    "due_on": due.isoformat(),
                    "owner": owner,
                    "clause_id": clause_id,
                    "trigger": trigger,
                },
            )
        ],
    )


def handle_start_clock(uow: UnitOfWork, cmd: StartClock) -> CommandResult:
    """Append ``Record.Created`` and ``ResponseClock.Started`` for a clock a person starts.

    Raises ``CorrespondenceScopeError``, ``RecordNotFoundError`` (no such item, or one the viewer
    may not read), ``ItemStateError`` (the item is void, closed or replaced), ``InvalidClockError``
    and ``CalendarUnavailableError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    item = open_item(uow, cmd, cmd.item_id)
    start_on, _ = _day(cmd.start_on, cmd.start_reason, "the start day")
    return start_clock(
        uow,
        cmd,
        item=item,
        label=cmd.label,
        kind=cmd.kind,
        duration_days=cmd.duration_days,
        day_type=cmd.day_type,
        warn_days=cmd.warn_days,
        start_on=start_on,
        trigger="manual",
        owner=cmd.owner,
        clause_id=cmd.clause_id,
    )


def handle_pause_clock(uow: UnitOfWork, cmd: PauseClock) -> CommandResult:
    """Append ``ResponseClock.Paused``. Raises ``ClockStateError`` unless the clock is running."""
    cmd = correlated(cmd)
    clock = load_clock(uow, cmd, cmd.clock_id)
    facts, _ = figures_of(uow, clock)
    day, _reason = _day(cmd.on, cmd.reason, "the pause day")
    payload = {"day": day, "reason": cmd.reason}
    _check_with(facts, Fact(CLOCK_PAUSED, payload), clock)
    done = append(uow, cmd, clock.id, CLOCK, [NewEvent(event_type=CLOCK_PAUSED, payload=payload)])
    return _result(clock, done)


def handle_resume_clock(uow: UnitOfWork, cmd: ResumeClock) -> CommandResult:
    """Append ``ResponseClock.Resumed`` with the new due date. ``ClockStateError`` unless paused."""
    cmd = correlated(cmd)
    clock = load_clock(uow, cmd, cmd.clock_id)
    facts, fig = figures_of(uow, clock)
    day, reason = _day(cmd.on, cmd.reason, "the resume day")
    calendar = catalog.calendar_for(clock.calendar, clock.scope)
    if fig.state != "paused":
        raise ClockStateError(f"clock {clock.id} is {fig.state}; only a paused clock resumes")
    try:
        due = resume_due(calendar, fig.remaining, date.fromisoformat(day), fig.day_type)
    except CalendarError as exc:
        raise CalendarUnavailableError(str(exc)) from exc
    payload = {"day": day, "due_on": due.isoformat(), "reason": reason}
    _check_with(facts, Fact(CLOCK_RESUMED, payload), clock)
    done = append(uow, cmd, clock.id, CLOCK, [NewEvent(event_type=CLOCK_RESUMED, payload=payload)])
    return _result(clock, done)


def handle_restart_clock(uow: UnitOfWork, cmd: RestartClock) -> CommandResult:
    """Append ``ResponseClock.Restarted``: a new day zero, the same length, no warnings yet."""
    cmd = correlated(cmd)
    clock = load_clock(uow, cmd, cmd.clock_id)
    facts, fig = figures_of(uow, clock)
    start, _ = _day(cmd.on, cmd.reason, "the new start day")
    calendar = catalog.calendar_for(clock.calendar, clock.scope)
    due = catalog.due_for(calendar, date.fromisoformat(start), fig.duration_days, fig.day_type)
    payload = {"start_on": start, "due_on": due.isoformat(), "reason": cmd.reason}
    _check_with(facts, Fact(CLOCK_RESTARTED, payload), clock)
    done = append(
        uow, cmd, clock.id, CLOCK, [NewEvent(event_type=CLOCK_RESTARTED, payload=payload)]
    )
    return _result(clock, done)


def _close(
    uow: UnitOfWork,
    cmd: Command,
    clock: registry.ClockRow,
    event_type: str,
    payload: dict[str, Any],
) -> CommandResult:
    facts, _ = figures_of(uow, clock)
    _check_with(facts, Fact(event_type, payload), clock)
    done = append(uow, cmd, clock.id, CLOCK, [NewEvent(event_type=event_type, payload=payload)])
    return _result(clock, done)


def handle_meet_clock(uow: UnitOfWork, cmd: MeetClock) -> CommandResult:
    """Append ``ResponseClock.Met``. A late answer is allowed (the date says so)."""
    cmd = correlated(cmd)
    clock = load_clock(uow, cmd, cmd.clock_id)
    day, _ = _day(cmd.on, cmd.reason, "the answer day")
    if cmd.response_id is not None:
        answer = registry.get_item(uow.conn(), cmd.response_id)
        if answer is None or answer.scope != cmd.scope:
            raise RecordNotFoundError(f"no record {cmd.response_id!r}")
    return _close(
        uow,
        cmd,
        clock,
        CLOCK_MET,
        {"day": day, "response_id": cmd.response_id, "reason": cmd.reason},
    )


def handle_cancel_clock(uow: UnitOfWork, cmd: CancelClock) -> CommandResult:
    """Append ``ResponseClock.Cancelled``."""
    cmd = correlated(cmd)
    clock = load_clock(uow, cmd, cmd.clock_id)
    day, _ = _day(cmd.on, cmd.reason, "the day")
    return _close(uow, cmd, clock, CLOCK_CANCELLED, {"day": day, "reason": cmd.reason})


def close_clocks_of_item(
    uow: UnitOfWork,
    cmd: Command,
    item_id: str,
    *,
    how: Literal["met", "cancelled"],
    day: str,
    reason: str,
    response_id: str | None = None,
    kinds: Sequence[str] | None = None,
) -> list[Event]:
    """Close the item's open clocks (``kinds`` limits which) and return the events.

    Used by recording a response (``met``, with the answering item) and by voiding or closing an
    item (``cancelled``). A clock that is already closed is left alone.
    """
    events: list[Event] = []
    for clock in registry.clocks_of(uow.conn(), item_id):
        if clock.state in ("met", "cancelled") or (kinds is not None and clock.kind not in kinds):
            continue
        if how == "met":
            payload: dict[str, Any] = {"day": day, "response_id": response_id, "reason": reason}
            result = _close(uow, cmd, clock, CLOCK_MET, payload)
        else:
            result = _close(uow, cmd, clock, CLOCK_CANCELLED, {"day": day, "reason": reason})
        events.extend(result.events)
    return events


def handle_sweep_clocks(uow: UnitOfWork, cmd: SweepClocks) -> CommandResult:
    """Record ``Expired`` and ``Warned`` events for the running clocks of the scope.

    The result's ``stream_id`` is the scope (many streams change); ``events`` lists what was
    recorded. A clock whose calendar cannot be read, or whose history the engine refuses, is
    skipped and logged: one bad clock must not stop the others.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    now = today_date()
    judged = now
    if cmd.on is not None:
        try:
            judged = date.fromisoformat(cmd.on)
        except ValueError as exc:
            raise InvalidClockError(f"on must be a date written YYYY-MM-DD: {cmd.on!r}") from exc
        if judged > now:
            raise InvalidClockError(f"on {cmd.on} is in the future; today is {today()}")
    events: list[Event] = []
    for clock in registry.list_clocks(uow.conn(), cmd.scope, limit=5000):
        if clock.state != "running":
            continue
        try:
            facts, fig = figures_of(uow, clock)
            calendar = catalog.calendar_for(clock.calendar, clock.scope)
            left = days_left(calendar, fig, judged)
            if left < 0:
                fact = Fact(CLOCK_EXPIRED, {"day": judged.isoformat(), "days_overdue": -left})
            else:
                level = warning_to_raise(fig, left)
                if level is None:
                    continue
                fact = Fact(
                    CLOCK_WARNED,
                    {"day": judged.isoformat(), "level": level, "days_left": left},
                )
            _check_with(facts, fact, clock)
        except (ClockStateError, CalendarUnavailableError, CalendarError, ValueError) as exc:
            log.warning("clock %s skipped by the sweep: %s", clock.id, exc)
            continue
        done = append(
            uow,
            cmd,
            clock.id,
            CLOCK,
            [NewEvent(event_type=fact.event_type, payload=dict(fact.payload))],
        )
        events.extend(done.events)
    return CommandResult(stream_id=cmd.scope, key=None, version=0, events=events)


__all__ = [
    "CancelClock",
    "MeetClock",
    "PauseClock",
    "RestartClock",
    "ResumeClock",
    "StartClock",
    "SweepClocks",
    "close_clocks_of_item",
    "figures_of",
    "handle_cancel_clock",
    "handle_meet_clock",
    "handle_pause_clock",
    "handle_restart_clock",
    "handle_resume_clock",
    "handle_start_clock",
    "handle_sweep_clocks",
    "load_clock",
    "start_clock",
]
