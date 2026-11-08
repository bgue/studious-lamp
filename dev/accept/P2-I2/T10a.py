"""Acceptance for P2-I2-T10a: the simulator's IWP planner on an in-memory world (no server).

Exit 0, one ``PASS <check>`` line per check, then ``T10a ok``. Exits 1 on the first failure.

Run: ``uv run python dev/accept/P2-I2/T10a.py``.
"""

from __future__ import annotations

import sys
from datetime import date

from tl_sim import groundtruth as gt
from tl_sim.actors.iwp_planner import CATEGORIES, IwpPlanner
from tl_sim.actors.registry import ACTOR_CLASSES
from tl_sim.orchestrator import all_identities
from tl_sim.scenario import ACTOR_NAMES, ROLE_NAMES, IwpPlannerParams, Scenario
from tl_sim.testing import FakeWorld, make_context
from tl_sim.types import GroundTruth

SEED = 1
PARAMS = IwpPlannerParams(iwps_per_day=2, scope_items=3, constraint_rate=1.0, clears_per_day=1)
ASSISTANT = "agent:sim-assistant"
BASE = {"scenario": "t", "seed": SEED, "start": date(2026, 11, 2)}


def fail(name: str) -> None:
    sys.exit(f"FAIL {name}")


def check(name: str, cond: bool) -> None:
    if not cond:
        fail(name)
    print(f"PASS {name}")


def run_day(world: FakeWorld, actor: IwpPlanner, day: int) -> list[GroundTruth]:
    return actor.step(make_context(world, actor.identity, seed=SEED, day=day))


def main() -> None:
    world = FakeWorld("t10a", "project:sim-t10a")
    actor = IwpPlanner(PARAMS)

    truth = run_day(world, actor, 0)
    iwps = sorted(world.iwp_rows, key=lambda r: r["number"])
    items = [r for r in world.record_rows if r["type"] == "awp.ScopeItem"]
    links_per_iwp = [sum(1 for s in world.scope_rows if s["iwp_id"] == r["id"]) for r in iwps]
    notes = [t for t in truth if t.intent == gt.RECORD_CREATED]
    check(
        "built",
        len(iwps) == 2
        and len(items) == 6
        and all(r["state"] == "In development" for r in iwps)
        and links_per_iwp == [3, 3]
        and len(notes) == 2 + 6 + 1,
    )

    (constraint,) = world.constraint_rows
    newest = max(world.iwp_rows, key=lambda r: r["number"])
    check(
        "raised",
        constraint["subject_id"] == newest["id"]
        and constraint["category"] in CATEGORIES
        and constraint["state"] == "Open",
    )
    day1_key = constraint["key"]

    run_day(world, actor, 1)
    states = {c["key"]: c["state"] for c in world.constraint_rows}
    day2_open = [c for c in world.constraint_rows if c["state"] == "Open"]
    check(
        "cleared",
        states[day1_key] == "Cleared" and len(day2_open) == 1 and day2_open[0]["key"] != day1_key,
    )

    first, second = FakeWorld("t10a", "project:sim-t10a"), FakeWorld("t10a", "project:sim-t10a")
    for world_run in (first, second):
        run_day(world_run, IwpPlanner(PARAMS), 0)
    same = [(r["key"], r["title"]) for r in first.record_rows] == [
        (r["key"], r["title"]) for r in second.record_rows
    ]
    check("same seed", same and bool(first.record_rows))

    off = Scenario.model_validate(BASE).actors.enabled()
    on = Scenario.model_validate(
        {**BASE, "actors": {"workface_planner": {}, "iwp_planner": {}, "approver": {}}}
    ).actors.enabled()
    check(
        "off by default",
        "iwp_planner" not in off
        and [n for n in on if n in ("workface_planner", "iwp_planner")]
        == ["workface_planner", "iwp_planner"]
        and "iwp_planner" not in ROLE_NAMES,
    )

    check(
        "registry",
        ACTOR_CLASSES["iwp_planner"] is IwpPlanner
        and ACTOR_NAMES.index("iwp_planner") == ACTOR_NAMES.index("workface_planner") + 1,
    )

    identities = all_identities()
    check("identities", identities[-2:] == ["user:sim-iwp_planner", ASSISTANT])
    print("T10a ok")


if __name__ == "__main__":
    main()
