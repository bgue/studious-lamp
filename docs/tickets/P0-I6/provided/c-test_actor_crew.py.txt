"""The crew on an in-memory world (``tl_sim.testing``). Provided by the supervisor."""

from __future__ import annotations

from typing import Any, cast

from tl_sim import groundtruth as gt
from tl_sim.actors.crew import Crew
from tl_sim.scenario import CountRange, CrewParams
from tl_sim.testing import FakeClient, FakeWorld, make_context, seed_lines
from tl_sim.types import GroundTruth

IDENTITY = "user:sim-crew"
PINNED = [
    "Valve V001 4in on 6-CS-1004",
    "Valve V002 4in on 6-CS-1001",
    "Valve V003 4in on 6-CS-1004",
]


def world_with_lines(lines: int = 3) -> FakeWorld:
    world = FakeWorld("r1", "project:sim-r1")
    seed_lines(world, lines)
    return world


def step(world: FakeWorld, *, seed: int = 1, day: int = 0, **params: Any) -> list[GroundTruth]:
    actor = Crew(CrewParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, day=day))


def valves(world: FakeWorld) -> list[dict[str, Any]]:
    return [r for r in world.records() if r["title"].startswith("Valve ")]


def test_identity_and_name_follow_the_contract() -> None:
    actor = Crew(CrewParams())
    assert (actor.name, actor.identity) == ("crew", IDENTITY)


def test_with_no_lines_it_does_nothing_not_even_an_announcement() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    assert step(world, announce="late") == []
    assert world.posts() == []


def test_each_valve_has_data_and_belongs_to_a_line() -> None:
    world = world_with_lines()
    truth = step(world, valves_per_day=2, reject_rate=0.0)
    made = valves(world)
    assert [v["title"][:10] for v in made] == ["Valve V001", "Valve V002"]
    by_key = {r["key"]: r for r in world.records()}
    for valve in made:
        data = valve["psets"]["valve_data"]
        assert data["body_material"] == "CS"
        assert data["size_in"] in (2, 3, 4, 6, 8)
        assert data["manufacturer"] in ("Crane", "Velan", "Emerson")
        assert valve["title"] == (
            f"Valve V{made.index(valve) + 1:03d} {data['size_in']}in on "
            + [
                by_key[v["other_key"]]["title"].removeprefix("Line ")
                for v in world.links(valve["id"])
                if v["direction"] == "out"
            ][0]
        )
        assert [v["relation"] for v in world.links(valve["id"]) if v["direction"] == "out"] == [
            "belongs_to"
        ]
    per_valve = [gt.RECORD_CREATED] + [gt.PSET_SET] * 3 + [gt.LINK_ADDED]
    assert [t.intent for t in truth] == per_valve * 2 + [gt.POST_CREATED]
    sets = [t for t in truth if t.intent == gt.PSET_SET]
    assert {next(iter(t.expect)) for t in sets} == {
        "psets.valve_data.body_material",
        "psets.valve_data.manufacturer",
        "psets.valve_data.size_in",
    }
    assert all(t.actor == IDENTITY for t in truth)


def test_one_progress_post_lists_the_valves_installed() -> None:
    world = world_with_lines()
    step(world, valves_per_day=2, reject_rate=0.0)
    keys = [v["key"] for v in valves(world)]
    (post,) = world.posts()
    assert post["actor"] == IDENTITY
    assert post["body"] == f"Installed 2 valves: #{keys[0]} #{keys[1]}"


def test_one_valve_is_reported_in_the_singular() -> None:
    world = world_with_lines()
    step(world, valves_per_day=1, reject_rate=0.0)
    (key,) = [v["key"] for v in valves(world)]
    assert world.posts()[0]["body"] == f"Installed 1 valve: #{key}"


def test_no_valves_means_no_progress_post_and_no_rejection() -> None:
    world = world_with_lines()
    assert step(world, valves_per_day=0, reject_rate=1.0) == []
    assert world.posts() == []


def test_a_reject_rate_of_one_flags_one_installed_valve_with_a_hold() -> None:
    world = world_with_lines()
    step(world, valves_per_day=3, reject_rate=1.0)
    progress, rejection = world.posts()
    keys = {v["key"] for v in valves(world)}
    assert progress["body"].startswith("Installed 3 valves: ")
    assert rejection["body"].startswith("Inspection failed on #")
    assert rejection["body"].endswith(", needs rework #hold")
    flagged = rejection["body"].removeprefix("Inspection failed on #").split(",")[0]
    assert flagged in keys


def test_a_reject_rate_of_zero_never_flags() -> None:
    world = world_with_lines()
    step(world, valves_per_day=3, reject_rate=0.0)
    assert len(world.posts()) == 1


def test_an_announcement_is_posted_first_as_urgent() -> None:
    world = world_with_lines()
    truth = step(world, valves_per_day=0, reject_rate=0.0, announce="6in flange is late by 21 days")
    assert [t.intent for t in truth] == [gt.POST_CREATED]
    assert world.posts()[0]["body"] == "#urgent 6in flange is late by 21 days"
    step(world, valves_per_day=1, reject_rate=0.0, announce="again", day=1)
    assert [p["body"] for p in world.posts()][1] == "#urgent again"


def test_the_serial_continues_on_the_next_day() -> None:
    world = world_with_lines()
    step(world, valves_per_day=2, reject_rate=0.0)
    step(world, valves_per_day=2, reject_rate=0.0, day=1)
    assert [v["title"][:10] for v in valves(world)] == [
        "Valve V001",
        "Valve V002",
        "Valve V003",
        "Valve V004",
    ]


def test_the_same_seed_gives_the_same_day_and_another_seed_a_different_one() -> None:
    first, second, other = world_with_lines(), world_with_lines(), world_with_lines()
    params: dict[str, Any] = {"valves_per_day": CountRange(min=4, max=4), "reject_rate": 0.5}
    a = step(first, seed=7, **params)
    b = step(second, seed=7, **params)
    c = step(other, seed=8, **params)
    assert [gt.to_line(t) for t in a] == [gt.to_line(t) for t in b]
    assert [gt.to_line(t) for t in a] != [gt.to_line(t) for t in c]


def test_the_draws_happen_in_the_documented_order() -> None:
    """Pinned for seed 7 and five lines: count, then line, size, maker for each valve."""
    world = world_with_lines(5)
    step(world, seed=7, valves_per_day=CountRange(min=3, max=6), reject_rate=0.0)
    assert [v["title"] for v in valves(world)] == PINNED


def test_it_reads_and_writes_only_through_the_client() -> None:
    world = world_with_lines()
    actor = Crew(CrewParams(valves_per_day=1, reject_rate=1.0))
    ctx = make_context(world, actor.identity)
    actor.step(ctx)
    used = {name for name, _ in cast(FakeClient, ctx.client).calls}
    assert used <= {"query", "create_record", "set_psets", "link", "post"}
