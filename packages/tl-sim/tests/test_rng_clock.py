"""Seeded randomness and the simulated clock."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, date, datetime

import pytest
from tl_sim.clock import STEP, SimClock, day_start, seed_time, working_date
from tl_sim.rng import actor_rng

MON_TO_FRI = ("mon", "tue", "wed", "thu", "fri")


def draws(seed: int, actor: str, day: int) -> list[float]:
    rng = actor_rng(seed, actor, day)
    return [rng.random() for _ in range(5)]


def test_the_same_seed_actor_and_day_give_the_same_numbers() -> None:
    assert draws(4711, "crew", 3) == draws(4711, "crew", 3)


@pytest.mark.parametrize(
    ("other", "label"),
    [((4712, "crew", 3), "seed"), ((4711, "planner", 3), "actor"), ((4711, "crew", 4), "day")],
)
def test_changing_the_seed_the_actor_or_the_day_changes_the_numbers(
    other: tuple[int, str, int], label: str
) -> None:
    assert draws(*other) != draws(4711, "crew", 3), label


def test_the_numbers_do_not_depend_on_the_process_hash_seed() -> None:
    code = (
        "from tl_sim.rng import actor_rng; r = actor_rng(4711, 'crew', 3); "
        "print([r.random() for _ in range(3)])"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": hash_seed, "PATH": "/usr/bin"},
            cwd="/",
        ).stdout
        for hash_seed in ("0", "1", "random")
    }
    assert len(outputs) == 1


def test_working_dates_skip_weekends() -> None:
    friday = date(2026, 11, 6)
    assert working_date(friday, 0, MON_TO_FRI) == friday
    assert working_date(friday, 1, MON_TO_FRI) == date(2026, 11, 9)  # the Monday after
    assert working_date(date(2026, 11, 7), 0, MON_TO_FRI) == date(2026, 11, 9)  # Saturday start
    assert working_date(date(2026, 11, 2), 9, MON_TO_FRI) == date(2026, 11, 13)


def test_working_dates_follow_the_scenario_calendar() -> None:
    assert working_date(date(2026, 11, 2), 1, ("mon", "wed")) == date(2026, 11, 4)
    with pytest.raises(ValueError, match="empty"):
        working_date(date(2026, 11, 2), 0, ())
    with pytest.raises(ValueError, match="0 or more"):
        working_date(date(2026, 11, 2), -1, MON_TO_FRI)


def test_the_clock_ticks_and_stamps_utc() -> None:
    clock = SimClock(datetime(2026, 11, 2, 7, 0, tzinfo=UTC))
    assert clock.stamp() == "2026-11-02T07:00:00+00:00"
    assert clock.tick() == datetime(2026, 11, 2, 7, 0, tzinfo=UTC) + STEP
    clock.set(datetime(2026, 11, 3, 9, 30, tzinfo=UTC))
    assert clock.stamp() == "2026-11-03T09:30:00+00:00"


def test_the_clock_refuses_a_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SimClock(datetime(2026, 11, 2, 7, 0))


def test_each_slot_starts_later_and_the_seed_comes_first() -> None:
    day = date(2026, 11, 2)
    assert seed_time(day) < day_start(day, 0) < day_start(day, 1) < day_start(day, 2)
