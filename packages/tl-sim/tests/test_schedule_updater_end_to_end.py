"""The schedule updater against the real API app, and the fake world held to it (P1-I4).

A controller (here ``ScheduleWorld``, which writes as ``user:u``) defines the schedule MAIN in the
run's scope and publishes its first snapshot; the worker (``svc:schedule``) builds what is sent.
The scenario names both as operators, so ``sim_assert`` holds the rest of the run to the rules.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from suite import SCOPE, START, Suite, build_suite, close_suite
from tl_core.services.errors import DuplicateLinkError
from tl_mod_schedule import testing as schedule_testing
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    DuplicateSnapshotError,
    NoCurrentSnapshotError,
    SourceFileError,
)
from tl_mod_schedule.testing import ScheduleWorld
from tl_sim.client import HttpSimClient, Keys
from tl_sim.clock import SimClock
from tl_sim.orchestrator import ORCHESTRATOR, Simulation
from tl_sim.reader import HttpReader, SimReader
from tl_sim.scenario import AreaSpec, Scenario, Template
from tl_sim.state import RunStore
from tl_sim.testing import FakeClient, FakeWorld
from tl_sim.types import SimClient
from tl_xer.synth import make_xer, series

RUN_ID = "rt1"
UPDATER = "user:sim-schedule_updater"
OPERATORS = ["user:u", "svc:schedule"]
TEMPLATE = Template(template="t", areas=[AreaSpec(name="North", lines=["6-CS-1001"])])


class Connector:
    def __init__(self, suite: Suite) -> None:
        self.suite = suite

    def check(self, scenario: Scenario) -> None:
        return None

    def provision(self, identities: Sequence[str]) -> dict[str, str]:
        return {identity: self.suite.tokens[identity] for identity in identities}

    def client(
        self, identity: str, clock: SimClock, keys: Keys, tokens: dict[str, str]
    ) -> SimClient:
        return HttpSimClient(
            self.suite.api(identity, clock),
            run_id=RUN_ID,
            scope=SCOPE,
            clock=clock,
            keys=keys,
            identity=identity,
        )

    def reader(self, tokens: dict[str, str]) -> SimReader:
        return HttpReader(self.suite.api(ORCHESTRATOR), SCOPE)


def build_world(root: Path) -> ScheduleWorld:
    """A suite with file storage, and MAIN defined and published in the run's scope."""
    suite = build_suite(root, objects=True)
    made = ScheduleWorld(suite.db, root / "objects")
    made.__dict__["suite"] = suite
    made.define(owner="Planning")
    made.publish(made.upload(make_xer(series(1, 1)[0])))
    return made


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScheduleWorld]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.setattr(
        schedule_testing, "PROJECT", SCOPE
    )  # ScheduleWorld writes in the run's scope
    monkeypatch.setitem(schedule_testing.BASE, "scope", SCOPE)
    made = build_world(tmp_path / "suite")
    try:
        yield made
    finally:
        close_suite(suite_of(made))


def suite_of(world: ScheduleWorld) -> Suite:
    return world.__dict__["suite"]


def scenario(*, operators: list[str] | None = None, **updater: Any) -> Scenario:
    return Scenario.model_validate(
        {
            "scenario": "schedule",
            "seed": 11,
            "start": date(2026, 11, 2),
            "operators": OPERATORS if operators is None else operators,
            "actors": {
                "document_controller": None,
                "planner": {"approvals_per_day": 0, "activities_per_day": 2, "lookahead_day": None},
                "crew": None,
                "schedule_updater": {"links_per_day": 2, **updater},
            },
        }
    )


def play(world: ScheduleWorld, tmp_path: Path, days: int, **kw: Any) -> Simulation:
    sim = Simulation.create(
        scenario(**kw),
        TEMPLATE,
        store=RunStore(tmp_path / "runs"),
        connector=Connector(suite_of(world)),
        run_id=RUN_ID,
    )
    sim.advance(days)
    return sim


def test_a_week_of_the_updater_passes_sim_assert(world: ScheduleWorld, tmp_path: Path) -> None:
    sim = play(world, tmp_path, 6)  # Monday to Monday: two files
    report = sim.assert_()
    assert report.ok, [f.line() for f in report.failures]
    assert report.counts.get("snapshot.queued") == 2
    assert report.counts.get("link.added", 0) >= 1
    assert [(s.number, s.state) for s in reversed(world.snapshots())] == [
        (1, "Published"),
        (2, "Uploaded"),
        (3, "Uploaded"),
    ]
    assert next(s for s in world.snapshots() if s.number == 2).source_name == "update-02.xer"


def test_what_the_worker_builds_afterwards_is_not_held_against_the_run(
    world: ScheduleWorld, tmp_path: Path
) -> None:
    sim = play(world, tmp_path, 1)
    world.work()  # the worker builds MAIN#2 (a service writes in the run's scope)
    assert [s.state for s in world.snapshots()][:1] == ["Valid"]
    report = sim.assert_()
    assert report.ok, [f.line() for f in report.failures]


def test_the_links_are_made_to_the_current_snapshot_and_survive_a_publish(
    world: ScheduleWorld, tmp_path: Path
) -> None:
    sim = play(world, tmp_path, 3)
    refs = [
        r["key"]
        for r in suite_of(world).api(ORCHESTRATOR).list_records(SCOPE)
        if r["type"] == "schedule.ActivityRef"
    ]
    assert refs and all(key.startswith("MAIN/A") for key in refs)
    world.work()
    second = next(s for s in world.snapshots() if s.number == 2)
    world.publish(second.id)  # a controller publishes MAIN#2
    assert world.schedule().current_snapshot_number == 2
    assert sim.assert_().ok


def test_without_naming_the_operators_the_run_does_not_pass(
    world: ScheduleWorld, tmp_path: Path
) -> None:
    sim = play(world, tmp_path, 1, operators=[])
    checks = {f.check for f in sim.assert_().failures}
    assert {"unexpected_record", "event_source", "event_actor"} <= checks


def test_naming_only_the_controller_leaves_the_worker_unexplained(
    world: ScheduleWorld, tmp_path: Path
) -> None:
    sim = play(world, tmp_path, 1, operators=["user:u"])
    failures = sim.assert_().failures
    assert {f.check for f in failures} == {"event_source", "event_actor"}
    assert {f.actual for f in failures if f.check == "event_actor"} == {"svc:schedule"}


def test_the_same_seed_gives_the_same_week(world: ScheduleWorld, tmp_path: Path) -> None:
    first = play(world, tmp_path / "a", 6)
    other = build_world(tmp_path / "other")
    try:
        again = play(other, tmp_path / "b", 6)
        assert again.status().digest == first.status().digest
        mine = [
            (s.key, s.source_sha256)
            for s in suite_of(world).api(UPDATER).get_schedule("sim-rt1", "MAIN").snapshots
        ]
        theirs = [
            (s.key, s.source_sha256)
            for s in suite_of(other).api(UPDATER).get_schedule("sim-rt1", "MAIN").snapshots
        ]
        assert mine == theirs and len(mine) == 3
    finally:
        close_suite(suite_of(other))


# --- the fake world is held to the real suite ----------------------------------------------------


def calls(client: Any, schedule_id: str, planner: Any) -> list[tuple[str, str]]:
    """The same story against any ``ScheduleDesk``: what happens, as (step, outcome) pairs."""
    story: list[tuple[str, str]] = []

    def attempt(name: str, call: Any) -> Any:
        try:
            result = call()
        except (
            ActivityNotFoundError,
            DuplicateLinkError,
            DuplicateSnapshotError,
            NoCurrentSnapshotError,
            SourceFileError,
        ) as error:
            story.append((name, type(error).__name__))
            return None
        story.append((name, "ok"))
        return result

    empty = attempt("open", lambda: client.open_snapshot(schedule_id))
    attempt("start without a file", lambda: client.start_snapshot(empty["id"]))
    attempt(
        "attach",
        lambda: client.attach_snapshot_file(empty["id"], "u.xer", make_xer(series(1, 2)[1])),
    )
    attempt("start", lambda: client.start_snapshot(empty["id"]))
    twin = attempt("open again", lambda: client.open_snapshot(schedule_id))
    attempt(
        "attach the same",
        lambda: client.attach_snapshot_file(twin["id"], "u.xer", make_xer(series(1, 2)[1])),
    )
    attempt("start the same", lambda: client.start_snapshot(twin["id"]))
    one, two = planner[0], planner[1]
    activity = client.current_activities("MAIN")[0]["activity_id"]
    attempt("link", lambda: client.link_activity(one, schedule_id, activity))
    attempt("link another", lambda: client.link_activity(two, schedule_id, activity))
    attempt("link again", lambda: client.link_activity(one, schedule_id, activity))
    other = client.current_activities("MAIN")[1]["activity_id"]
    attempt("link a second activity", lambda: client.link_activity(two, schedule_id, other))
    attempt("link it to the first record", lambda: client.link_activity(one, schedule_id, other))
    attempt("link a missing one", lambda: client.link_activity(one, schedule_id, "NOPE"))
    return story


def test_the_fake_world_does_what_the_suite_does(world: ScheduleWorld) -> None:
    suite = suite_of(world)
    clock = SimClock(START)
    real = suite.client(UPDATER, clock)
    planner = suite.client("user:sim-planner", SimClock(START))
    real_records = [
        planner.create_record(record_type="core.Record", title=f"Activity {n:03d} x")["id"]
        for n in (1, 2)
    ]
    schedule_id = real.schedules()[0]["id"]
    activities = [(a["activity_id"], a["name"]) for a in real.current_activities("MAIN")]
    seen_before = len(HttpReader(suite.api(UPDATER), SCOPE).events())
    real_story = calls(real, schedule_id, real_records)

    fake_world = FakeWorld(RUN_ID, SCOPE)
    fake_world.define_schedule(activities=activities)
    fake_world.schedule_rows[0]["snapshots"][0]["file"] = make_xer(series(1, 1)[0])
    fake: FakeClient = fake_world.client(UPDATER, SimClock(START))
    helper = fake_world.client("user:sim-planner", SimClock(START))
    fake_records = [
        helper.create_record(record_type="core.Record", title=f"Activity {n:03d} x")["id"]
        for n in (1, 2)
    ]
    fake_story = calls(fake, fake_world.schedule_rows[0]["id"], fake_records)
    assert fake_story == real_story
    assert ("start without a file", "SourceFileError") in real_story
    assert ("start the same", "DuplicateSnapshotError") in real_story
    assert ("link again", "DuplicateLinkError") in real_story
    assert ("link it to the first record", "ok") in real_story
    assert ("link a missing one", "ActivityNotFoundError") in real_story

    def types(events: list[dict[str, Any]]) -> list[tuple[str, str]]:
        return [
            (e["event_type"], e["actor"]) for e in events if e["source"] in (f"sim:{RUN_ID}", "api")
        ]

    real_events = HttpReader(suite.api(UPDATER), SCOPE).events()[seen_before:]
    assert types(fake_world.events()[-len(types(real_events)) :]) == types(real_events)
    mine = {r["key"]: r for r in fake_world.records() if r["type"].startswith("schedule.")}
    theirs = {r["key"]: r for r in HttpReader(suite.api(UPDATER), SCOPE).records()}
    for key, row in mine.items():
        if key in theirs and key != "MAIN":
            assert (row["title"], row["type"], row["status"]) == (
                theirs[key]["title"],
                theirs[key]["type"],
                theirs[key]["status"],
            ), key


def unpublished(client: Any) -> list[str]:
    """What a schedule with no published snapshot answers a person, as text."""
    schedule = client.schedules()[0]
    seen = [str(schedule["current_snapshot_number"]), str(schedule["snapshot_count"])]
    seen.append(str(client.snapshots_of("MAIN")))
    record = client.open_snapshot(schedule["id"])
    for call in (
        client.current_activities,
        lambda code: client.link_activity(record["id"], schedule["id"], "A1000"),
    ):
        try:
            call("MAIN")
        except NoCurrentSnapshotError as error:
            seen.append(type(error).__name__)
    return seen


def test_a_schedule_with_no_published_snapshot_answers_alike_in_both_worlds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.setattr(schedule_testing, "PROJECT", SCOPE)
    monkeypatch.setitem(schedule_testing.BASE, "scope", SCOPE)
    suite = build_suite(tmp_path / "suite", objects=True)
    try:
        ScheduleWorld(suite.db, tmp_path / "suite" / "objects").define()
        fake_world = FakeWorld(RUN_ID, SCOPE)
        fake_world.define_schedule(published=False)
        real = unpublished(suite.client(UPDATER, SimClock(START)))
        fake = unpublished(fake_world.client(UPDATER, SimClock(START)))
        assert real == fake == ["None", "0", "[]", *["NoCurrentSnapshotError"] * 2]
    finally:
        close_suite(suite)
