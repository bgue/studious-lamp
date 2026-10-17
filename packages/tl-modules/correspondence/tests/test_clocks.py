"""The clock engine: dates, state and warnings from a clock's events (P1-I5-T04)."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

import pytest
from corrworld import FIXTURES
from tl_mod_correspondence import calendars as cal
from tl_mod_correspondence import clocks as ck
from tl_mod_correspondence.limits import MAX_CLOCK_EVENTS


@pytest.fixture(scope="module")
def p123() -> cal.Calendar:
    return cal.load_calendar("P123-default@1", FIXTURES)


def d(text: str) -> date:
    return date.fromisoformat(text)


def started(
    p123: cal.Calendar,
    start: str = "2026-10-17",
    n: int = 14,
    day_type: str = "calendar",
    **more: Any,
) -> ck.Fact:
    payload: dict[str, Any] = {
        "start_on": start,
        "duration_days": n,
        "day_type": day_type,
        "calendar": p123.ref,
        "warn_days": [w for w in (7, 3, 1) if w <= n],
        "due_on": p123.add_days(d(start), n, day_type).isoformat(),
        **more,
    }
    return ck.Fact("ResponseClock.Started", payload)


def fact(event_type: str, **payload: Any) -> ck.Fact:
    return ck.Fact(f"ResponseClock.{event_type}", payload)


def test_a_fourteen_calendar_day_clock_is_due_two_weeks_after_day_zero(p123: cal.Calendar) -> None:
    fig = ck.replay([started(p123)], p123)
    assert fig.state == "running" and fig.due_on == d("2026-10-31") and fig.remaining == 14
    assert fig.start_on == d("2026-10-17") and fig.run_from == d("2026-10-17")
    assert fig.warn_days == (7, 3, 1) and fig.restarts == 0 and fig.warned_level is None


def test_a_working_day_clock_skips_weekends_and_holidays(p123: cal.Calendar) -> None:
    fig = ck.replay([started(p123, "2026-12-18", 5, "working")], p123)
    # Fri 18th: Mon 21, Tue 22, Wed 23, Thu 24, then 25th is a holiday, 28th too: Tue 29th
    assert fig.due_on == d("2026-12-29")


def test_warning_thresholds_are_sorted_largest_first_and_checked(p123: cal.Calendar) -> None:
    assert ck.check_warn_days([1, 7, 3], 14) == (7, 3, 1)
    for bad in ([0], [15], [-1], [3, 3], list(range(1, 12)), [True]):
        with pytest.raises(ValueError):
            ck.check_warn_days(bad, 14)  # type: ignore[arg-type]


def test_a_clock_length_and_day_type_are_checked() -> None:
    ck.check_params(1, "calendar")
    ck.check_params(3650, "working")
    for n, kind in ((0, "calendar"), (3651, "calendar"), (5, "weekly"), (True, "calendar")):
        with pytest.raises(ValueError):
            ck.check_params(n, kind)  # type: ignore[arg-type]


def test_pause_stops_the_count_and_resume_moves_the_due_date(p123: cal.Calendar) -> None:
    facts = [
        started(p123),
        fact("Paused", on="2026-10-20", reason="Waiting for a drawing"),
        fact("Resumed", on="2026-10-23", due_on="2026-11-03"),
    ]
    fig = ck.replay(facts[:2], p123)
    assert fig.state == "paused" and fig.remaining == 11 and fig.paused_on == d("2026-10-20")
    assert fig.due_on == d("2026-10-31")  # unchanged until it runs again
    fig = ck.replay(facts, p123)
    assert fig.state == "running" and fig.due_on == d("2026-11-03") and fig.paused_on is None
    assert fig.run_from == d("2026-10-23") and fig.remaining == 11


def test_a_working_clock_does_not_count_the_weekend_of_a_pause(p123: cal.Calendar) -> None:
    facts = [
        started(p123, "2026-10-19", 5, "working"),  # due Mon 26th
        fact("Paused", on="2026-10-21", reason="Wait"),  # two working days used
        fact("Resumed", on="2026-10-26", due_on="2026-10-29"),  # three left, from Monday
    ]
    fig = ck.replay(facts, p123)
    assert fig.due_on == d("2026-10-29") and fig.remaining == 3


def test_pausing_and_resuming_the_same_day_changes_nothing(p123: cal.Calendar) -> None:
    facts = [
        started(p123),
        fact("Paused", on="2026-10-20", reason="x"),
        fact("Resumed", on="2026-10-20", due_on="2026-10-31"),
    ]
    assert ck.replay(facts, p123).due_on == d("2026-10-31")


def test_two_pauses_add_up(p123: cal.Calendar) -> None:
    facts = [
        started(p123),
        fact("Paused", on="2026-10-19", reason="a"),  # 2 used, 12 left
        fact("Resumed", on="2026-10-21", due_on="2026-11-02"),
        fact("Paused", on="2026-10-24", reason="b"),  # 3 more used, 9 left
        fact("Resumed", on="2026-10-30", due_on="2026-11-08"),
    ]
    fig = ck.replay(facts, p123)
    assert fig.remaining == 9 and fig.due_on == d("2026-11-08")


def test_restart_counts_again_from_the_new_day_zero_and_forgets_warnings(
    p123: cal.Calendar,
) -> None:
    facts = [
        started(p123),
        fact("Warned", on="2026-10-24", level=7, days_left=7),
        fact("Restarted", start_on="2026-10-27", due_on="2026-11-10", reason="Revised letter"),
    ]
    fig = ck.replay(facts, p123)
    assert fig.start_on == d("2026-10-27") and fig.due_on == d("2026-11-10")
    assert fig.warned_level is None and fig.restarts == 1 and fig.remaining == 14


def test_restart_reopens_a_clock_that_was_met_cancelled_or_expired(p123: cal.Calendar) -> None:
    for closing in (
        fact("Met", on="2026-10-20"),
        fact("Cancelled", on="2026-10-20", reason="x"),
        fact("Expired", on="2026-11-02", days_overdue=2),
    ):
        facts = [
            started(p123),
            closing,
            fact("Restarted", start_on="2026-11-03", due_on="2026-11-17", reason="again"),
        ]
        fig = ck.replay(facts, p123)
        assert fig.state == "running" and fig.closed_on is None and fig.due_on == d("2026-11-17")


def test_met_and_cancelled_close_the_clock_and_a_late_answer_still_meets_it(
    p123: cal.Calendar,
) -> None:
    met = ck.replay([started(p123), fact("Met", on="2026-10-25")], p123)
    assert met.state == "met" and met.closed_on == d("2026-10-25")
    cancelled = ck.replay([started(p123), fact("Cancelled", on="2026-10-25", reason="x")], p123)
    assert cancelled.state == "cancelled"
    late = ck.replay(
        [
            started(p123),
            fact("Expired", on="2026-11-02", days_overdue=2),
            fact("Met", on="2026-11-05"),
        ],
        p123,
    )
    assert late.state == "met" and late.closed_on == d("2026-11-05")


def test_warnings_must_be_new_smaller_thresholds_of_the_clock(p123: cal.Calendar) -> None:
    two = [started(p123), fact("Warned", on="2026-10-24", level=7, days_left=7)]
    assert (
        ck.replay([*two, fact("Warned", on="2026-10-28", level=3, days_left=3)], p123).warned_level
        == 3
    )
    for bad in (7, 5, 9):  # the same level again, a level the clock has not, a larger one
        with pytest.raises(ck.ClockReplayError):
            ck.replay([*two, fact("Warned", on="2026-10-28", level=bad, days_left=1)], p123)


def test_expired_needs_a_date_after_the_due_date(p123: cal.Calendar) -> None:
    with pytest.raises(ck.ClockReplayError, match="not past"):
        ck.replay([started(p123), fact("Expired", on="2026-10-31", days_overdue=0)], p123)
    fig = ck.replay([started(p123), fact("Expired", on="2026-11-01", days_overdue=1)], p123)
    assert fig.state == "expired" and fig.due_on == d("2026-10-31")


@pytest.mark.parametrize(
    "events",
    [
        [],
        [fact("Paused", on="2026-10-20", reason="x")],  # does not start with Started
        [fact("Met", on="2026-10-20")],
    ],
)
def test_a_history_must_begin_with_started(p123: cal.Calendar, events: list[ck.Fact]) -> None:
    with pytest.raises(ck.ClockReplayError):
        ck.replay(events, p123)


def test_events_that_do_not_fit_the_state_are_refused(p123: cal.Calendar) -> None:
    paused = [started(p123), fact("Paused", on="2026-10-20", reason="x")]
    met = [started(p123), fact("Met", on="2026-10-20")]
    cases = [
        [started(p123), fact("Resumed", on="2026-10-20", due_on="2026-10-31")],  # not paused
        [*paused, fact("Paused", on="2026-10-21", reason="y")],  # already paused
        [*paused, fact("Warned", on="2026-10-21", level=7, days_left=1)],  # warns only when running
        [*paused, fact("Expired", on="2026-11-30", days_overdue=3)],
        [*met, fact("Met", on="2026-10-21")],
        [*met, fact("Cancelled", on="2026-10-21", reason="x")],
        [*met, fact("Paused", on="2026-10-21", reason="x")],
        [started(p123), fact("Mystery", on="2026-10-21")],
        [started(p123), started(p123)],
    ]
    for events in cases:
        with pytest.raises(ck.ClockReplayError):
            ck.replay(events, p123)


def test_dates_never_move_backwards(p123: cal.Calendar) -> None:
    with pytest.raises(ck.ClockReplayError, match="before"):
        ck.replay([started(p123), fact("Met", on="2026-10-10")], p123)
    with pytest.raises(ck.ClockReplayError, match="before"):
        ck.replay(
            [
                started(p123),
                fact("Paused", on="2026-10-22", reason="x"),
                fact("Resumed", on="2026-10-21", due_on="2026-10-30"),
            ],
            p123,
        )
    with pytest.raises(ck.ClockReplayError, match="before"):
        ck.replay(
            [
                started(p123),
                fact("Met", on="2026-10-25"),
                fact("Restarted", start_on="2026-10-20", due_on="2026-11-03", reason="x"),
            ],
            p123,
        )


def test_a_stored_due_date_that_the_engine_does_not_compute_is_refused(p123: cal.Calendar) -> None:
    with pytest.raises(ck.ClockReplayError, match="engine computes"):
        ck.replay([started(p123, due_on="2026-11-01")], p123)
    with pytest.raises(ck.ClockReplayError, match="engine computes"):
        ck.replay(
            [
                started(p123),
                fact("Paused", on="2026-10-20", reason="x"),
                fact("Resumed", on="2026-10-23", due_on="2026-11-04"),
            ],
            p123,
        )
    with pytest.raises(ck.ClockReplayError, match="engine computes"):
        ck.replay(
            [
                started(p123),
                fact("Restarted", start_on="2026-10-27", due_on="2026-11-09", reason="x"),
            ],
            p123,
        )


def test_another_calendar_than_the_one_named_is_refused(p123: cal.Calendar) -> None:
    other = cal.parse_calendar(
        'id: O\nversion: 1\nscope: company\nname: o\nrest_days: [sun]\ncovers_from: "2026-01-01"\n'
        'covers_to: "2027-01-01"\nholidays: []\n'
    )
    with pytest.raises(ck.ClockReplayError, match="counts on"):
        ck.replay([started(p123)], other)


def test_a_started_event_with_bad_fields_is_a_replay_error_not_a_crash(p123: cal.Calendar) -> None:
    for change in (
        {"duration_days": 0},
        {"duration_days": "x"},
        {"duration_days": "14"},
        {"duration_days": 14.0},
        {"duration_days": True},
        {"day_type": "weekly"},
        {"start_on": "17/10/2026"},
        {"start_on": None},
        {"warn_days": [99]},
        {"warn_days": "7"},
        {"due_on": 5},
    ):
        payload = dict(started(p123).payload)
        payload.update(change)
        with pytest.raises(ck.ClockReplayError):
            ck.replay([ck.Fact("ResponseClock.Started", payload)], p123)
    payload = dict(started(p123).payload)
    del payload["day_type"]
    with pytest.raises(ck.ClockReplayError):
        ck.replay([ck.Fact("ResponseClock.Started", payload)], p123)


def test_a_working_clock_that_runs_past_the_calendar_is_refused(p123: cal.Calendar) -> None:
    payload = dict(started(p123).payload)
    payload.update(start_on="2028-12-20", duration_days=30, day_type="working", due_on="2029-02-01")
    with pytest.raises(ck.ClockReplayError, match="outside"):
        ck.replay([ck.Fact("ResponseClock.Started", payload)], p123)


def test_too_many_events_are_refused_before_any_is_read(p123: cal.Calendar) -> None:
    many = [started(p123)] + [fact("Warned", on="2026-10-24", level=7)] * MAX_CLOCK_EVENTS
    with pytest.raises(ck.ClockReplayError, match="events"):
        ck.replay(many, p123)


def test_days_left_counts_down_to_zero_and_below(p123: cal.Calendar) -> None:
    fig = ck.replay([started(p123)], p123)
    assert ck.days_left(p123, fig, d("2026-10-17")) == 14
    assert ck.days_left(p123, fig, d("2026-10-31")) == 0
    assert ck.days_left(p123, fig, d("2026-11-02")) == -2
    working = ck.replay([started(p123, "2026-10-19", 5, "working")], p123)
    assert ck.days_left(p123, working, d("2026-10-22")) == 2
    assert ck.days_left(p123, working, d("2026-10-27")) == -1


def test_days_left_of_a_paused_or_closed_clock(p123: cal.Calendar) -> None:
    paused = ck.replay([started(p123), fact("Paused", on="2026-10-20", reason="x")], p123)
    assert ck.days_left(p123, paused, d("2026-12-01")) == 11
    met = ck.replay([started(p123), fact("Met", on="2026-10-20")], p123)
    assert ck.days_left(p123, met, d("2026-12-01")) == 0


def test_effective_state_is_expired_only_for_a_running_clock_past_its_date() -> None:
    assert ck.effective_state("running", d("2026-10-31"), d("2026-10-31")) == "running"
    assert ck.effective_state("running", d("2026-10-31"), d("2026-11-01")) == "expired"
    for state in ("paused", "met", "cancelled", "expired"):
        assert ck.effective_state(state, d("2026-10-31"), d("2027-01-01")) == state


@pytest.mark.parametrize(
    ("left", "warned", "expected"),
    [
        (14, None, None),
        (8, None, None),
        (7, None, 7),
        (5, None, 7),
        (3, None, 3),  # jumped over 7: the smallest crossed is raised
        (0, None, 1),
        (6, 7, None),
        (3, 7, 3),
        (2, 3, None),
        (1, 3, 1),
        (1, 1, None),
        (-1, None, None),  # past due: the sweep expires it instead
    ],
)
def test_the_warning_to_raise_is_the_smallest_new_threshold_crossed(
    p123: cal.Calendar, left: int, warned: int | None, expected: int | None
) -> None:
    fig = ck.replay([started(p123)], p123)
    fig = ck.Figures(**{**fig.__dict__, "warned_level": warned})
    assert ck.warning_to_raise(fig, left) == expected


def test_only_a_running_clock_warns(p123: cal.Calendar) -> None:
    paused = ck.replay([started(p123), fact("Paused", on="2026-10-20", reason="x")], p123)
    assert ck.warning_to_raise(paused, 1) is None
    met = ck.replay([started(p123), fact("Met", on="2026-10-20")], p123)
    assert ck.warning_to_raise(met, 1) is None


def test_the_same_events_always_give_the_same_figures(p123: cal.Calendar) -> None:
    rng = random.Random(7)
    for _ in range(40):
        facts, expected = random_history(rng, p123)
        assert ck.replay(facts, p123) == expected
        assert ck.replay(list(facts), p123) == expected


def random_history(rng: random.Random, calendar: cal.Calendar) -> tuple[list[ck.Fact], ck.Figures]:
    """A valid random history, built with the engine's own helpers, and the figures it implies."""
    day_type = rng.choice(["calendar", "working"])
    n = rng.randint(3, 40)
    start = d("2026-02-02") + timedelta(days=rng.randint(0, 200))
    facts = [started(calendar, start.isoformat(), n, day_type)]
    fig = ck.replay(facts, calendar)
    for _ in range(rng.randint(0, 6)):
        on = fig.last_on + timedelta(days=rng.randint(0, 6))
        if fig.state == "running":
            facts.append(fact("Paused", on=on.isoformat(), reason="r"))
        elif fig.state == "paused":
            due = ck.resume_due(calendar, fig.remaining, on, fig.day_type)
            facts.append(fact("Resumed", on=on.isoformat(), due_on=due.isoformat()))
        else:
            break
        fig = ck.replay(facts, calendar)
    return facts, fig


def test_resuming_never_gives_a_due_date_before_the_resume_day(p123: cal.Calendar) -> None:
    rng = random.Random(11)
    for _ in range(40):
        facts, fig = random_history(rng, p123)
        if fig.state == "running" and fig.restarts == 0 and len(facts) > 1:
            assert fig.due_on >= fig.run_from
