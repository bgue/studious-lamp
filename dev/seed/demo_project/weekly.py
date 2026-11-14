"""weekly section of P200 (P2-SEED-T10): five weekly plans from Monday 2026-10-05, built with the
real awp week handlers (``tl_mod_awp.handlers.week``) through ``world.run``.

Weeks 1-3 are committed (4 to 8 of the 12 released IWPs, hours as text), judged, and closed (the PPC
is written). Week 1 is judged under 70 percent. Week 4 is committed with outcomes for part of its
commitments only. Week 5 is opened and holds no commitment (see the report of P2-SEED-T10: a commit
moves a Draft plan to Committed, so a Draft plan with a commitment is not reachable).

Words: the plan, the commitments and the outcomes are made by the project engineer (an awp
superuser, so the ``user`` word); the closing is made by the administrator (``controller``).
Every command runs inside ``world.on(day)`` on a day in, or just before, its week, never after
TODAY. The section draws from its own ``rng`` only. No raw SQL writes.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from tl_mod_awp.commands import CloseWeek, CommitIwpToWeek, OpenWeeklyPlan, RecordWeekOutcome
from tl_mod_awp.handlers.week import (
    handle_close_week,
    handle_commit_iwp_to_week,
    handle_open_weekly_plan,
    handle_record_week_outcome,
)

from dev.seed.demo_project.core import ADMIN
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import TODAY, World

FIRST_MONDAY = date(2026, 10, 5)
WEEK_COUNT = 5
CLOSED_WEEKS = 3  # weeks 1-3 are closed; week 4 is committed; week 5 is opened only
COMMIT_MIN = 4
COMMIT_MAX = 8
#: the project engineer: awp superuser, so the ``user`` word for plan, commit and outcome
PLANNER = "lhartmann"
#: the administrator: the ``controller`` word for the close
CLOSER = ADMIN
HOURS = ("16", "24", "32", "40")
#: the codes of the code list MissReason (data/awp/standards.yaml)
MISS_REASONS = (
    "Constraint",
    "Material",
    "Labour",
    "Weather",
    "Rework",
    "Access",
    "Equipment",
    "Other",
)

Pair = tuple[str, str]  # (IWP record id, IWP key)


def _released(world: World) -> list[Pair]:
    """The IWPs released to the field (Issued or In progress), by key."""
    return [
        (str(r["id"]), str(r["key"]))
        for r in world.rows(
            "SELECT r.id AS id, r.key AS key FROM cur_core_record r "
            "WHERE r.type = 'awp.IWP' AND r.status IN ('Issued', 'In progress') ORDER BY r.key"
        )
    ]


def _judge(
    world: World,
    rng: random.Random,
    plan: str,
    picked: list[Pair],
    judged: int,
    done: int,
    day: date,
) -> None:
    """Record outcomes for ``judged`` of the commitments (in a random order): the first ``done`` are
    done, the rest missed with a reason from the code list."""
    order = rng.sample(picked, len(picked))
    with world.on(day):
        for index, (iwp, _key) in enumerate(order[:judged]):
            if index < done:
                outcome, reason = "done", None
            else:
                outcome, reason = "missed", rng.choice(MISS_REASONS)
            world.run(
                handle_record_week_outcome,
                RecordWeekOutcome,
                by=PLANNER,
                plan_id=plan,
                iwp_id=iwp,
                outcome=outcome,
                miss_reason=reason,
                expected_version=world.version(plan),
            )


def _close(world: World, plan: str, day: date) -> None:
    with world.on(day):
        world.run(
            handle_close_week,
            CloseWeek,
            by=CLOSER,
            plan_id=plan,
            expected_version=world.version(plan),
        )


def _week(world: World, rng: random.Random, number: int, released: list[Pair]) -> None:
    monday = FIRST_MONDAY + timedelta(weeks=number - 1)
    friday = monday + timedelta(days=4)
    with world.on(monday):
        opened = world.run(handle_open_weekly_plan, OpenWeeklyPlan, by=PLANNER, week_start=monday)
    plan = str(opened.stream_id)
    if number > CLOSED_WEEKS + 1:
        return  # week 5 is opened and holds no commitment

    picked = sorted(rng.sample(released, rng.randint(COMMIT_MIN, COMMIT_MAX)), key=lambda p: p[1])
    with world.on(monday):
        for iwp, _key in picked:
            world.run(
                handle_commit_iwp_to_week,
                CommitIwpToWeek,
                by=PLANNER,
                plan_id=plan,
                iwp_id=iwp,
                committed_hours=rng.choice(HOURS),
                expected_version=world.version(plan),
            )

    count = len(picked)
    if number <= CLOSED_WEEKS:
        if number == 1:
            done = (count * 6) // 10  # under 70 percent
        else:
            done = rng.randint((7 * count + 9) // 10, count)  # at least 70 percent
        _judge(world, rng, plan, picked, count, done, friday)
        _close(world, plan, friday)
    else:
        judged = max(1, count // 2)  # week 4: part of the commitments are judged
        _judge(world, rng, plan, picked, judged, judged // 2, friday)


def build(world: World, rng: random.Random) -> None:
    released = _released(world)
    if len(released) < COMMIT_MAX:
        raise RuntimeError(f"too few IWPs are released to commit a week: {len(released)}")
    for number in range(1, WEEK_COUNT + 1):
        if FIRST_MONDAY + timedelta(weeks=number - 1) > TODAY:
            raise RuntimeError(f"week {number} starts after TODAY")
        _week(world, rng, number, released)


register("weekly", build, needs=("awp.IWP",))
