"""The orchestrator loop: create, advance, inject, status, assert, and determinism.

The actors are replaced by a scripted one (``actors_of`` is patched), so these tests do not depend
on the three real actors; they are tested on their own and together in ``test_end_to_end.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from tl_sim import orchestrator as orch
from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.injections import Poster, injected_actor
from tl_sim.orchestrator import ORCHESTRATOR, Simulation, default_run_id
from tl_sim.scenario import (
    ActorsConfig,
    AreaSpec,
    CrewParams,
    DocumentControllerParams,
    InjectSpec,
    Scenario,
    Template,
)
from tl_sim.state import RunError, RunInterruptedError, RunStore
from tl_sim.testing import FakeConnector
from tl_sim.types import SimContext

TEMPLATE = Template(
    template="t", areas=[AreaSpec(name="North", lines=["6-CS-1001", "4-CS-1002", "2-CS-1003"])]
)
FRIDAY = date(2026, 11, 6)


class Scripted(BaseActor):
    """Two or three valves a day on random lines, and a post."""

    name = "crew"

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        lines = rec.records(title_prefix="Line ")
        count = ctx.rng.randint(2, 3)
        for _ in range(count):
            valve = rec.create(f"Valve {ctx.rng.randint(0, 99999)}")
            rec.link(valve, ctx.rng.choice(lines), "belongs_to")
        rec.post(f"installed {count}")


@pytest.fixture(autouse=True)
def scripted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch, "actors_of", lambda scenario: [Scripted(None)])


def scenario(seed: int = 4711, start: date = date(2026, 11, 2), **extra: object) -> Scenario:
    return Scenario.model_validate({"scenario": "t", "seed": seed, "start": start, **extra})


def make(tmp_path: Path, sc: Scenario | None = None) -> tuple[Simulation, FakeConnector]:
    sc = sc or scenario()
    connector = FakeConnector(default_run_id(sc))
    sim = Simulation.create(sc, TEMPLATE, store=RunStore(tmp_path), connector=connector)
    return sim, connector


def test_create_makes_the_run_provisions_actors_and_seeds_the_template(tmp_path: Path) -> None:
    sim, connector = make(tmp_path)
    assert sim.state.run_id == default_run_id(scenario())
    assert sim.state.scope == f"project:sim-{sim.state.run_id}"
    assert connector.provisioned == [
        ORCHESTRATOR,
        "agent:sim-document_controller",
        "agent:sim-planner",
        "agent:sim-crew",
    ]
    assert sim.state.seeded and sim.state.in_progress is None and sim.state.day == 0
    titles = [r["title"] for r in connector.world.records()]
    assert titles == ["Area North", "Line 6-CS-1001", "Line 4-CS-1002", "Line 2-CS-1003"]
    assert [t.intent for t in sim.truth()] == [
        "record.created",
        "record.created",
        "link.added",
    ] * 1 + [
        "record.created",
        "link.added",
        "record.created",
        "link.added",
    ]
    assert all(t.actor == ORCHESTRATOR for t in sim.truth())
    assert {e["effective_at"][:16] for e in connector.world.events()} <= {
        f"2026-11-02T06:0{n}" for n in range(10)
    }


def test_the_default_run_id_is_stable_and_names_the_scenario_and_seed() -> None:
    assert default_run_id(scenario()) == default_run_id(scenario())
    assert default_run_id(scenario()) != default_run_id(scenario(seed=1))
    assert default_run_id(scenario())[0] == "r" and len(default_run_id(scenario())) == 7


def test_a_second_run_with_the_same_id_is_refused(tmp_path: Path) -> None:
    sim, connector = make(tmp_path)
    with pytest.raises(RunError, match="already exists"):
        Simulation.create(
            scenario(),
            TEMPLATE,
            store=RunStore(tmp_path),
            connector=FakeConnector(sim.state.run_id),
        )


def test_advance_plays_working_days_and_stamps_them_on_the_calendar(tmp_path: Path) -> None:
    sim, connector = make(tmp_path, scenario(start=FRIDAY))
    result = sim.advance(2)
    assert result.days == [FRIDAY, date(2026, 11, 9)]  # Friday, then Monday
    assert result.steps == 2 and sim.state.day == 2
    days = {e["effective_at"][:10] for e in connector.world.events()}
    assert days == {"2026-11-06", "2026-11-09"}
    assert sim.played_dates() == [FRIDAY, date(2026, 11, 9)]
    posted = [p["body"] for p in connector.world.posts()]
    assert len(posted) == 2 and all(b.startswith("installed ") for b in posted)


def test_each_actor_starts_later_than_the_one_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Second(Scripted):
        name = "planner"

    monkeypatch.setattr(orch, "actors_of", lambda sc: [Scripted(None), Second(None)])
    sim, connector = make(tmp_path)
    sim.advance(1)
    by_actor: dict[str, str] = {}
    for event in connector.world.events():
        by_actor.setdefault(event["actor"], event["effective_at"])
    assert by_actor["agent:sim-crew"] < by_actor["agent:sim-planner"]
    assert by_actor["agent:sim-crew"].startswith("2026-11-02T07:0")
    assert by_actor["agent:sim-planner"].startswith("2026-11-02T07:3")


def test_the_same_seed_gives_the_same_ground_truth_and_world(tmp_path: Path) -> None:
    first, one = make(tmp_path / "a")
    second, two = make(tmp_path / "b")
    first.advance(4)
    second.advance(4)
    assert first.status().digest == second.status().digest
    assert first.truth() == second.truth()
    assert [r["title"] for r in one.world.records()] == [r["title"] for r in two.world.records()]


def test_another_seed_gives_other_ground_truth(tmp_path: Path) -> None:
    first, _ = make(tmp_path / "a", scenario(seed=1))
    second, _ = make(tmp_path / "b", scenario(seed=2))
    first.advance(3)
    second.advance(3)
    assert first.status().digest != second.status().digest


def test_advancing_in_pieces_equals_advancing_at_once(tmp_path: Path) -> None:
    whole, _ = make(tmp_path / "a")
    pieces, _ = make(tmp_path / "b")
    whole.advance(4)
    for _ in range(4):
        pieces.advance(1)
    assert whole.status().digest == pieces.status().digest


def test_a_run_reopened_from_disk_carries_on_with_its_keys_and_day(tmp_path: Path) -> None:
    sim, connector = make(tmp_path)
    sim.advance(2)
    reopened = Simulation.open(sim.state.run_id, store=RunStore(tmp_path), connector=connector)
    assert reopened.state.day == 2
    reopened.advance(2)
    keys = [r["key"] for r in connector.world.records()]
    assert len(keys) == len(set(keys))  # no key was handed out twice
    straight, _ = make(tmp_path / "other")
    straight.advance(4)
    assert reopened.status().digest == straight.status().digest


def test_advance_needs_at_least_one_day(tmp_path: Path) -> None:
    sim, _ = make(tmp_path)
    with pytest.raises(RunError, match="at least 1"):
        sim.advance(0)


def test_assert_passes_on_the_world_the_run_made_and_fails_when_it_is_tampered_with(
    tmp_path: Path,
) -> None:
    sim, connector = make(tmp_path)
    sim.advance(3)
    report = sim.assert_()
    assert report.ok, [f.line() for f in report.failures]
    connector.world.record_rows[5]["title"] = "tampered"
    assert not sim.assert_().ok


def test_status_reports_the_day_the_counts_and_the_digest(tmp_path: Path) -> None:
    sim, _ = make(tmp_path, scenario(start=FRIDAY))
    before = sim.status()
    assert (before.day, before.last_date, before.next_date) == (0, None, FRIDAY)
    sim.advance(1)
    status = sim.status()
    assert (status.day, status.last_date, status.next_date) == (1, FRIDAY, date(2026, 11, 9))
    assert status.ground_truth["post.created"] == 1
    assert status.scenario == "t" and status.seed == 4711 and not status.interrupted
    assert len(status.digest) == 64 and status.digest != before.digest


def test_an_injection_is_queued_and_played_after_the_regular_actors(tmp_path: Path) -> None:
    sim, connector = make(tmp_path)
    sim.inject("post", actor="planner", body="Heads up: crane booked")
    assert [s["event"] for s in sim.status().pending] == ["post"]
    sim.advance(1)
    posts = connector.world.posts()
    assert [(p["actor"], p["body"]) for p in posts][-1] == (
        "agent:sim-planner",
        "Heads up: crane booked",
    )
    assert posts[0]["actor"] == "agent:sim-crew"
    assert sim.status().pending == []
    later = [e for e in connector.world.events() if e["actor"] == "agent:sim-planner"]
    # one regular actor takes slot 0 (07:00), so the injection is in slot 1 (07:30)
    assert later[0]["effective_at"].startswith("2026-11-02T07:3")
    sim.advance(1)
    assert sum(1 for p in connector.world.posts() if p["actor"] == "agent:sim-planner") == 1


def test_a_scenario_injection_plays_on_its_day_only(tmp_path: Path) -> None:
    sc = scenario(inject=[{"day": 1, "event": "post", "actor": "crew", "body": "Crane arrived"}])
    sim, connector = make(tmp_path, sc)
    sim.advance(3)
    bodies = [p["body"] for p in connector.world.posts()]
    assert bodies.count("Crane arrived") == 1
    assert bodies.index("Crane arrived") == 2  # day 0 post, day 1 post, then the injection


def test_an_invalid_injection_is_refused_and_not_queued(tmp_path: Path) -> None:
    sim, _ = make(tmp_path)
    for bad in (("flood", {}), ("material_late", {}), ("post", {"actor": "welder", "body": "x"})):
        with pytest.raises(ValueError):
            sim.inject(bad[0], **bad[1])
    assert sim.status().pending == []


def test_injected_events_map_to_one_step_of_an_actor_with_one_off_parameters() -> None:
    sc = scenario(actors=ActorsConfig(crew=CrewParams(valves_per_day=9, reject_rate=0.9)))
    late = injected_actor(
        InjectSpec.model_validate(
            {"day": 0, "event": "material_late", "item": "6in flange", "days": 21}
        ),
        sc,
    )
    assert late.name == "crew"
    params = late.params  # type: ignore[attr-defined]
    assert (params.valves_per_day, params.reject_rate) == (0, 0.0)
    assert params.announce == "6in flange is late by 21 days"
    revision = injected_actor(
        InjectSpec.model_validate({"day": 0, "event": "design_revision", "count": 2}),
        scenario(actors=ActorsConfig(document_controller=DocumentControllerParams())),
    )
    assert revision.name == "document_controller"
    assert (revision.params.documents_per_day, revision.params.forced_revisions) == (0, 2)  # type: ignore[attr-defined]
    said = injected_actor(
        InjectSpec.model_validate({"day": 0, "event": "post", "actor": "planner", "body": "x"}),
        sc,
    )
    assert isinstance(said, Poster) and said.identity == "agent:sim-planner"


def test_a_step_that_dies_leaves_the_run_flagged_and_it_refuses_to_go_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Dies(Scripted):
        def act(self, ctx: SimContext, rec: Recorder) -> None:
            rec.create("half done")
            raise RuntimeError("the network went away")

    sim, connector = make(tmp_path)
    monkeypatch.setattr(orch, "actors_of", lambda sc: [Dies(None)])
    with pytest.raises(RuntimeError, match="network"):
        sim.advance(1)
    assert sim.status().interrupted
    reopened = Simulation.open(sim.state.run_id, store=RunStore(tmp_path), connector=connector)
    with pytest.raises(RunInterruptedError, match="create a new run"):
        reopened.advance(1)


def test_a_scenario_with_every_actor_off_still_counts_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()
    sc = scenario(actors=ActorsConfig(document_controller=None, planner=None, crew=None))
    sim, connector = make(tmp_path, sc)
    before = len(sim.truth())
    result = sim.advance(3)
    assert (sim.state.day, result.steps, len(sim.truth())) == (3, 0, before)
    assert connector.world.posts() == []
