"""The response-clock engine: dates, state and warnings from a clock's events (brief 9 M10).

Everything here is a pure function of the clock's facts and of a calendar. Nothing reads the
ledger, a table or the clock: the caller passes the facts (``Fact``), the calendar (``Calendar``)
and, when it needs one, today's date. That is what makes a clock *recomputable from the ledger*:
``replay`` over the events of a clock gives the figures the projection holds, and the tests check
that they are equal.

The model. A clock has a day zero (``start_on``), a length in days (``duration_days``) and a day
type (``calendar`` or ``working``). While it runs, it counts days after ``run_from``; ``remaining``
is the number of counted days it still has when it started running from ``run_from``. Then:

* ``Started``: ``remaining = duration``, ``run_from = start_on``, ``due_on = add_days(start_on,
  duration)``.
* ``Paused`` on ``P``: ``remaining -= count_days(run_from, P)``; the clock stops counting.
* ``Resumed`` on ``R``: ``run_from = R``; ``due_on = add_days(R, remaining)``.
* ``Restarted`` on ``S``: ``remaining = duration``, ``run_from = S``, ``due_on = add_days(S,
  duration)``; warnings are forgotten, a closed or expired clock runs again.
* ``Met`` and ``Cancelled`` close the clock; ``Met`` may follow ``Expired`` (a late answer).
* ``Warned`` records the smallest warning threshold raised; ``Expired`` marks a running clock
  past its due date. Both come from the sweep and never change a date.

Whether a running clock is *expired* depends on today's date, so it is not stored: use
``effective_state``. The events carry the due dates the engine computed, and ``replay`` checks that
each equals what the engine computes now (a different value means the calendar file changed or the
event was forged: ``ClockReplayError``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from tl_mod_correspondence.calendars import Calendar, CalendarError
from tl_mod_correspondence.limits import MAX_CLOCK_EVENTS, MAX_DURATION_DAYS, MAX_WARNINGS
from tl_mod_correspondence.names import (
    CLOCK_CANCELLED,
    CLOCK_CANCELLED_STATE,
    CLOCK_EXPIRED,
    CLOCK_EXPIRED_STATE,
    CLOCK_MET,
    CLOCK_MET_STATE,
    CLOCK_PAUSED,
    CLOCK_PAUSED_STATE,
    CLOCK_RESTARTED,
    CLOCK_RESUMED,
    CLOCK_RUNNING,
    CLOCK_STARTED,
    CLOCK_WARNED,
    DAY_TYPES,
)

#: The states from which a clock is finished until it is restarted.
CLOSED_STATES: Final = (CLOCK_MET_STATE, CLOCK_CANCELLED_STATE)


class ClockReplayError(ValueError):
    """The events of a clock do not make a valid history, or do not match the engine."""


@dataclass(frozen=True)
class Fact:
    """One event of a clock: its type and its payload (as the ledger holds them)."""

    event_type: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class Figures:
    """What the events of a clock add up to."""

    state: str  # running, paused, met, cancelled or expired
    start_on: date
    duration_days: int
    day_type: str
    calendar: str  # code@version
    warn_days: tuple[int, ...]
    due_on: date
    remaining: int  # counted days left at ``run_from``
    run_from: date  # day zero of the current run
    paused_on: date | None
    closed_on: date | None
    warned_level: int | None
    restarts: int
    last_on: date  # the date of the newest event: dates only move forward


def parse_day(value: object, what: str) -> date:
    """``value`` (an ISO ``YYYY-MM-DD`` string) as a date. Raises ``ClockReplayError``."""
    if not isinstance(value, str) or len(value) != 10:
        raise ClockReplayError(f"{what} must be a date written YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ClockReplayError(f"{what} is not a calendar date: {value!r}") from exc


def check_warn_days(values: Sequence[int], duration_days: int) -> tuple[int, ...]:
    """The warning thresholds as a tuple, largest first, or ``ValueError``.

    Each is an integer from 1 up to ``duration_days``, thresholds are distinct, and there are at
    most ``MAX_WARNINGS``.
    """
    if len(values) > MAX_WARNINGS:
        raise ValueError(f"a clock has at most {MAX_WARNINGS} warning thresholds")
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= duration_days:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("a warning threshold is a whole number of days from 1 to the length")
    if len(set(values)) != len(values):
        raise ValueError("warning thresholds must be distinct")
    return tuple(sorted(values, reverse=True))


def check_params(duration_days: int, day_type: str) -> None:
    """Raise ``ValueError`` unless the length is 1 to ``MAX_DURATION_DAYS`` and the type known."""
    if (
        isinstance(duration_days, bool)
        or not isinstance(duration_days, int)  # pyright: ignore[reportUnnecessaryIsInstance]
        or not 1 <= duration_days <= MAX_DURATION_DAYS
    ):
        raise ValueError(f"a clock is 1 to {MAX_DURATION_DAYS} days long")
    if day_type not in DAY_TYPES:
        raise ValueError(f"day_type is one of {', '.join(DAY_TYPES)}")


def start_due(calendar: Calendar, start_on: date, duration_days: int, day_type: str) -> date:
    """The due date of a clock that starts on ``start_on``."""
    check_params(duration_days, day_type)
    return calendar.add_days(start_on, duration_days, day_type)


def pause_remaining(calendar: Calendar, figures: Figures, on: date) -> int:
    """The counted days left if the clock is paused on ``on`` (never below zero)."""
    used = calendar.count_days(figures.run_from, on, figures.day_type)
    return max(0, figures.remaining - used)


def resume_due(calendar: Calendar, remaining: int, on: date, day_type: str) -> date:
    """The due date of a clock that runs again from ``on`` with ``remaining`` counted days."""
    return calendar.add_days(on, remaining, day_type)


def days_left(calendar: Calendar, figures: Figures, today: date) -> int:
    """Counted days from today to the due date: negative once past it, zero on the day.

    Running clocks count from today; a paused clock reports its ``remaining``; a closed clock
    reports 0. Counted in the clock's own day type, on the calendar named in the figures.
    """
    if figures.state == CLOCK_PAUSED_STATE:
        return figures.remaining
    if figures.state in CLOSED_STATES:
        return 0
    if today <= figures.due_on:
        return calendar.count_days(today, figures.due_on, figures.day_type)
    return -calendar.count_days(figures.due_on, today, figures.day_type)


def effective_state(state: str, due_on: date, today: date) -> str:
    """``expired`` for a running clock past its due date, else ``state`` (no calendar needed)."""
    if state == CLOCK_RUNNING and today > due_on:
        return CLOCK_EXPIRED_STATE
    return state


def warning_to_raise(figures: Figures, left: int) -> int | None:
    """The warning threshold the sweep should record now, or ``None``.

    Only a running clock warns. It is the smallest threshold ``w`` with ``left <= w`` that is
    smaller than ``figures.warned_level`` (every threshold when none was raised); thresholds
    already passed are not repeated. A clock past due (``left < 0``) raises none: it expires.
    """
    if figures.state != CLOCK_RUNNING or left < 0:
        return None
    crossed = [w for w in figures.warn_days if left <= w]
    if figures.warned_level is not None:
        crossed = [w for w in crossed if w < figures.warned_level]
    return min(crossed) if crossed else None


def replay(facts: Sequence[Fact], calendar: Calendar) -> Figures:
    """The figures a clock's events add up to, checked against the engine.

    ``facts`` are the clock's events in ledger order. Raises ``ClockReplayError`` when: there are
    more than ``MAX_CLOCK_EVENTS`` or none; the first is not ``Started``; the calendar is not the
    one the first event names; a date is not a date or moves backwards; an event is not allowed in
    the state the clock is in; a stored ``due_on`` differs from the engine's; a threshold is not
    one of the clock's.
    """
    if not facts or len(facts) > MAX_CLOCK_EVENTS:
        raise ClockReplayError(f"a clock has 1 to {MAX_CLOCK_EVENTS} events")
    first = facts[0]
    if first.event_type != CLOCK_STARTED:
        raise ClockReplayError("the first event of a clock is Started")
    p = first.payload
    if p.get("calendar") != calendar.ref:
        raise ClockReplayError(f"the clock counts on {p.get('calendar')}, not {calendar.ref}")
    try:
        duration, day_type = p["duration_days"], p["day_type"]
        check_params(duration, day_type)
        warn_list = p.get("warn_days") or []
        if not isinstance(warn_list, list):
            raise ValueError("warn_days is a list of whole numbers")
        warn = check_warn_days(warn_list, duration)
        start_on = parse_day(p["start_on"], "start_on")
        stated_due = parse_day(p["due_on"], "due_on")
        due = start_due(calendar, start_on, duration, day_type)
    except (KeyError, TypeError, ValueError, CalendarError) as exc:
        raise ClockReplayError(f"Started is not valid: {exc}") from exc
    if stated_due != due:
        raise ClockReplayError(f"Started states due {stated_due}, the engine computes {due}")
    fig = Figures(
        state=CLOCK_RUNNING,
        start_on=start_on,
        duration_days=duration,
        day_type=day_type,
        calendar=calendar.ref,
        warn_days=warn,
        due_on=due,
        remaining=duration,
        run_from=start_on,
        paused_on=None,
        closed_on=None,
        warned_level=None,
        restarts=0,
        last_on=start_on,
    )
    for fact in facts[1:]:
        fig = _step(fig, fact, calendar)
    return fig


def _day(fact: Fact, key: str, fig: Figures) -> date:
    on = parse_day(fact.payload.get(key), key)
    if on < fig.last_on:
        raise ClockReplayError(f"{fact.event_type} is dated {on}, before {fig.last_on}")
    return on


def _step(fig: Figures, fact: Fact, calendar: Calendar) -> Figures:
    et, p = fact.event_type, fact.payload
    state = fig.state
    try:
        if et == CLOCK_PAUSED:
            if state not in (CLOCK_RUNNING, CLOCK_EXPIRED_STATE):
                raise ClockReplayError(f"Paused while {state}")
            on = _day(fact, "on", fig)
            return _with(
                fig,
                state=CLOCK_PAUSED_STATE,
                remaining=pause_remaining(calendar, fig, on),
                paused_on=on,
                last_on=on,
            )
        if et == CLOCK_RESUMED:
            if state != CLOCK_PAUSED_STATE:
                raise ClockReplayError(f"Resumed while {state}")
            on = _day(fact, "on", fig)
            due = resume_due(calendar, fig.remaining, on, fig.day_type)
            _same_due(p, due)
            return _with(
                fig, state=CLOCK_RUNNING, run_from=on, due_on=due, paused_on=None, last_on=on
            )
        if et == CLOCK_RESTARTED:
            on = parse_day(p.get("start_on"), "start_on")
            if on < fig.last_on:
                raise ClockReplayError(f"Restarted is dated {on}, before {fig.last_on}")
            due = calendar.add_days(on, fig.duration_days, fig.day_type)
            _same_due(p, due)
            return _with(
                fig,
                state=CLOCK_RUNNING,
                start_on=on,
                run_from=on,
                due_on=due,
                remaining=fig.duration_days,
                paused_on=None,
                closed_on=None,
                warned_level=None,
                restarts=fig.restarts + 1,
                last_on=on,
            )
        if et in (CLOCK_MET, CLOCK_CANCELLED):
            if state in CLOSED_STATES:
                raise ClockReplayError(f"{et} while {state}")
            on = _day(fact, "on", fig)
            closed = CLOCK_MET_STATE if et == CLOCK_MET else CLOCK_CANCELLED_STATE
            return _with(fig, state=closed, closed_on=on, paused_on=None, last_on=on)
        if et == CLOCK_WARNED:
            if state != CLOCK_RUNNING:
                raise ClockReplayError(f"Warned while {state}")
            on = _day(fact, "on", fig)
            level = p["level"]
            if isinstance(level, bool) or not isinstance(level, int):
                raise ValueError("level is a whole number of days")
            if level not in fig.warn_days or (
                fig.warned_level is not None and level >= fig.warned_level
            ):
                raise ClockReplayError(f"Warned at {level}, which is not a new threshold")
            return _with(fig, warned_level=level, last_on=on)
        if et == CLOCK_EXPIRED:
            if state != CLOCK_RUNNING:
                raise ClockReplayError(f"Expired while {state}")
            on = _day(fact, "on", fig)
            if on <= fig.due_on:
                raise ClockReplayError(f"Expired on {on}, which is not past {fig.due_on}")
            return _with(fig, state=CLOCK_EXPIRED_STATE, last_on=on)
    except (KeyError, TypeError, ValueError, CalendarError) as exc:
        if isinstance(exc, ClockReplayError):
            raise
        raise ClockReplayError(f"{et} is not valid: {exc}") from exc
    raise ClockReplayError(f"{et} is not an event of a clock after Started")


def _same_due(payload: Mapping[str, Any], computed: date) -> None:
    stated = parse_day(payload.get("due_on"), "due_on")
    if stated != computed:
        raise ClockReplayError(f"the event states due {stated}, the engine computes {computed}")


def _with(fig: Figures, **changes: Any) -> Figures:
    values = {**fig.__dict__, **changes}
    return Figures(**values)
