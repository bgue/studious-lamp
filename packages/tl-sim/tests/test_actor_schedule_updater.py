"""The schedule updater on an in-memory world (``tl_sim.testing``) (P1-I4).

The world stands in for a project whose schedule a controller defined and published before the run
(``FakeWorld.define_schedule``); the actor sends the weekly P6 file and links the planner's
records to activities. ``test_schedule_updater_end_to_end.py`` plays the same on the real suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from tl_sim import groundtruth as gt
from tl_sim.actors.base import Recorder
from tl_sim.actors.schedule_updater import MAX_SNAPSHOTS, ScheduleUpdater
from tl_sim.rng import actor_rng
from tl_sim.scenario import CountRange, ScheduleUpdaterParams, draw
from tl_sim.testing import ACTIVITIES, FakeWorld, make_context
from tl_sim.types import GroundTruth
from tl_xer.synth import make_xer, series

IDENTITY = "user:sim-schedule_updater"
MONDAY = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
TUESDAY = datetime(2026, 11, 3, 7, 0, tzinfo=UTC)


def planned(world: FakeWorld, count: int = 3) -> None:
    """Activity records of the planner, as the planner actor writes them."""
    recorder = Recorder(make_context(world, "user:sim-planner"), "user:sim-planner")
    for number in range(1, count + 1):
        recorder.create(f"Activity {number:03d} Install spools on 6-CS-100{number}")


def project(*, records: int = 3, **schedule: Any) -> FakeWorld:
    world = FakeWorld("r1", "project:sim-r1")
    world.define_schedule(**schedule)
    planned(world, records)
    return world


def step(
    world: FakeWorld, *, seed: int = 1, day: int = 0, now: datetime = MONDAY, **params: Any
) -> list[GroundTruth]:
    actor = ScheduleUpdater(ScheduleUpdaterParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, day=day, now=now))


def snapshots(world: FakeWorld) -> list[dict[str, Any]]:
    return world.schedule_rows[0]["snapshots"]


def test_identity_and_name_follow_the_contract() -> None:
    actor = ScheduleUpdater(ScheduleUpdaterParams())
    assert (actor.name, actor.identity) == ("schedule_updater", IDENTITY)


# --- step 1: the schedule -----------------------------------------------------------------------


def test_without_the_schedule_nothing_is_written_and_nothing_is_drawn() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    planned(world)
    before = len(world.event_rows)
    actor = ScheduleUpdater(ScheduleUpdaterParams(links_per_day=2))
    ctx = make_context(world, actor.identity, seed=4)
    assert actor.step(ctx) == []
    assert len(world.event_rows) == before
    assert ctx.rng.getstate() == actor_rng(4, actor.identity, 0).getstate()


def test_only_the_schedule_named_in_the_parameters_is_worked() -> None:
    world = project(code="OTHER")
    assert step(world, links_per_day=2) == [] and len(snapshots(world)) == 1
    assert [t.ref for t in step(world, schedule="OTHER", update_day="mon", links_per_day=0)][
        :1
    ] == ["OTHER#2"]


# --- step 2: the weekly file --------------------------------------------------------------------


def test_on_the_update_day_the_next_file_of_the_series_is_sent() -> None:
    world = project()
    truth = step(world, links_per_day=0)
    assert [(t.intent, t.ref) for t in truth] == [
        (gt.RECORD_CREATED, "MAIN#2"),
        (gt.SNAPSHOT_QUEUED, "MAIN#2"),
    ]
    assert all(t.actor == IDENTITY for t in truth)
    assert truth[0].expect == {
        "title": "Main schedule snapshot 2",
        "record_type": "schedule.ScheduleSnapshot",
        "voided": False,
    }
    assert truth[1].expect == {"file": "update-02.xer"}
    sent = snapshots(world)[1]
    assert (sent["key"], sent["state"], sent["filename"]) == ("MAIN#2", "Uploaded", "update-02.xer")
    assert sent["file"] == make_xer(series(1, 2)[1])
    [uploaded] = [e for e in world.event_rows if e["event_type"] == "File.Uploaded"][-1:]
    assert (uploaded["actor"], uploaded["source"]) == (IDENTITY, "api")
    queued = [e for e in world.event_rows if e["event_type"] == "ScheduleSnapshot.Queued"]
    assert [(e["actor"], e["stream_id"]) for e in queued] == [(IDENTITY, "id-MAIN#2")]


def test_on_other_days_no_file_is_sent() -> None:
    world = project()
    assert step(world, now=TUESDAY, links_per_day=0) == []
    assert len(snapshots(world)) == 1


@pytest.mark.parametrize(
    ("update_day", "now", "sends"),
    [("tue", TUESDAY, True), ("tue", MONDAY, False), (None, MONDAY, False), ("mon", MONDAY, True)],
)
def test_the_update_day_is_a_weekday_or_never(
    update_day: str | None, now: datetime, sends: bool
) -> None:
    world = project()
    step(world, now=now, update_day=update_day, links_per_day=0)
    assert (len(snapshots(world)) == 2) is sends


def test_each_week_sends_the_next_file_whatever_the_state_of_the_earlier_ones() -> None:
    world = project()
    step(world, links_per_day=0, day=0)
    step(world, links_per_day=0, day=5, now=datetime(2026, 11, 9, 7, 0, tzinfo=UTC))
    third = snapshots(world)[2]
    assert (third["key"], third["filename"]) == ("MAIN#3", "update-03.xer")
    assert third["file"] == make_xer(series(1, 3)[2])


def test_a_schedule_with_no_snapshot_gets_the_first_file_of_the_series() -> None:
    world = project(published=False)
    truth = step(world, links_per_day=0)
    assert [(t.intent, t.ref) for t in truth] == [
        (gt.RECORD_CREATED, "MAIN#1"),
        (gt.SNAPSHOT_QUEUED, "MAIN#1"),
    ]
    assert snapshots(world)[0]["file"] == make_xer(series(1, 1)[0])
    assert snapshots(world)[0]["filename"] == "update-01.xer"


def test_the_series_seed_picks_the_series() -> None:
    one, two = project(), project()
    step(one, links_per_day=0, series_seed=1)
    step(two, links_per_day=0, series_seed=2)
    assert snapshots(one)[1]["file"] == make_xer(series(1, 2)[1])
    assert snapshots(two)[1]["file"] == make_xer(series(2, 2)[1])
    assert snapshots(one)[1]["file"] != snapshots(two)[1]["file"]


def test_a_series_that_is_used_up_sends_nothing() -> None:
    world = project()
    for number in range(2, MAX_SNAPSHOTS):
        snapshots(world).append(
            {"id": f"dummy-{number}", "number": number, "state": "Void", "file": None}
        )
    assert len(snapshots(world)) == MAX_SNAPSHOTS - 1
    assert len(step(world, links_per_day=0)) == 2  # the 52nd
    assert len(snapshots(world)) == MAX_SNAPSHOTS
    assert step(world, links_per_day=0, day=1) == []
    assert len(snapshots(world)) == MAX_SNAPSHOTS


# --- step 3: links to activities ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        (
            1,
            [
                (gt.RECORD_CREATED, "MAIN/A1990"),
                (gt.LINK_ADDED, "SIMR1-REC-0003 references MAIN/A1990"),
                (gt.LINK_ADDED, "SIMR1-REC-0001 references MAIN/A1990"),
            ],
        ),
        (
            2,
            [
                (gt.RECORD_CREATED, "MAIN/A1100"),
                (gt.LINK_ADDED, "SIMR1-REC-0001 references MAIN/A1100"),
                (gt.RECORD_CREATED, "MAIN/A1990"),
                (gt.LINK_ADDED, "SIMR1-REC-0001 references MAIN/A1990"),
            ],
        ),
        (  # the second pick is the same pair: refused as a duplicate and passed over
            3,
            [
                (gt.RECORD_CREATED, "MAIN/A1230"),
                (gt.LINK_ADDED, "SIMR1-REC-0001 references MAIN/A1230"),
            ],
        ),
    ],
)
def test_the_first_draws_are_pinned(seed: int, expected: list[tuple[str, str]]) -> None:
    world = project()
    truth = step(world, seed=seed, update_day=None, links_per_day=2)
    assert [(t.intent, t.ref) for t in truth] == expected


def test_the_reference_record_and_the_link_are_what_the_log_says() -> None:
    world = project()
    truth = step(world, seed=1, update_day=None, links_per_day=2)
    ref, first, second = truth
    assert ref.expect == {
        "title": "A1990 Hydrotest",
        "record_type": "schedule.ActivityRef",
        "voided": False,
    }
    assert first.expect == {"from": "SIMR1-REC-0003", "to": "MAIN/A1990", "relation": "references"}
    assert second.expect["to"] == "MAIN/A1990"
    keys = {r["key"] for r in world.records()}
    assert "MAIN/A1990" in keys
    refs = [r for r in world.records() if r["type"] == "schedule.ActivityRef"]
    assert len(refs) == 1  # the second link found the reference already made


def test_a_record_already_linked_to_the_activity_is_passed_over() -> None:
    world = project(records=1, activities=(("A1000", "Issue P&IDs IFC"),))
    truth = step(world, update_day=None, links_per_day=3)
    assert [t.intent for t in truth] == [gt.RECORD_CREATED, gt.LINK_ADDED]
    assert len(world.link_rows) == 1


@pytest.mark.parametrize("kind", ["no snapshot", "no records", "no activities"])
def test_the_draw_is_spent_even_when_there_is_nothing_to_link(kind: str) -> None:
    world = project(
        published=kind != "no snapshot",
        records=0 if kind == "no records" else 2,
        activities=() if kind == "no activities" else ACTIVITIES,
    )
    count = CountRange(min=1, max=3)
    actor = ScheduleUpdater(ScheduleUpdaterParams(update_day=None, links_per_day=count))
    ctx = make_context(world, actor.identity, seed=5)
    assert actor.step(ctx) == []
    fresh = actor_rng(5, actor.identity, 0)
    draw(count, fresh)  # a range takes a number from the generator; an integer would not
    assert ctx.rng.random() == fresh.random()


def test_a_range_of_links_per_day_is_drawn_from_the_rng() -> None:
    world = project(records=5)
    truth = step(world, seed=9, update_day=None, links_per_day=CountRange(min=0, max=3))
    expected = draw(CountRange(min=0, max=3), actor_rng(9, IDENTITY, 0))
    assert 1 <= len([t for t in truth if t.intent == gt.LINK_ADDED]) <= expected


def test_only_the_planners_activity_records_are_linked() -> None:
    world = project(records=0)
    other = Recorder(make_context(world, "user:sim-crew"), "user:sim-crew")
    other.create("Valve V001 6in on 6-CS-1001")
    other.create("Line 6-CS-1001")
    assert step(world, update_day=None, links_per_day=3) == []
    assert not world.link_rows


def test_the_file_is_sent_before_the_links_and_is_not_yet_current() -> None:
    world = project()
    truth = step(world, seed=1, links_per_day=1)
    intents = [t.intent for t in truth]
    assert intents[:2] == [gt.RECORD_CREATED, gt.SNAPSHOT_QUEUED]
    assert gt.LINK_ADDED in intents
    assert snapshots(world)[1]["state"] == "Uploaded"  # a controller publishes it after a build


# --- the whole day is a function of the seed ----------------------------------------------------


def test_the_same_seed_gives_the_same_day() -> None:
    a = step(project(), seed=7, links_per_day=CountRange(min=1, max=3))
    b = step(project(), seed=7, links_per_day=CountRange(min=1, max=3))
    assert [(t.intent, t.ref) for t in a] == [(t.intent, t.ref) for t in b]
    others = [
        [t.ref for t in step(project(), seed=s, links_per_day=CountRange(min=1, max=3))]
        for s in (8, 9, 10, 11)
    ]
    assert any(refs != [t.ref for t in a] for refs in others)


def test_a_client_that_cannot_send_updates_is_refused_loudly() -> None:
    from tl_sim.client import ProposeUnavailableError

    class Bare:
        def query(self, q: str, *, limit: int = 100) -> list[dict[str, Any]]:
            return []

    actor = ScheduleUpdater(ScheduleUpdaterParams())
    world = FakeWorld("r1", "project:sim-r1")
    ctx = make_context(world, actor.identity)
    bare = type(ctx)(
        run_id=ctx.run_id,
        scope=ctx.scope,
        now=ctx.now,
        rng=ctx.rng,
        client=Bare(),  # type: ignore[arg-type]
    )
    with pytest.raises(ProposeUnavailableError):
        actor.step(bare)


# --- the parameters -----------------------------------------------------------------------------


def test_the_defaults() -> None:
    params = ScheduleUpdaterParams()
    assert (params.schedule, params.update_day, params.series_seed) == ("MAIN", "mon", 1)
    assert params.links_per_day == CountRange(min=0, max=2)


@pytest.mark.parametrize(
    "bad",
    [
        {"schedule": ""},
        {"schedule": "x" * 41},
        {"update_day": "someday"},
        {"series_seed": -1},
        {"unknown": 1},
    ],
)
def test_bad_parameters_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ScheduleUpdaterParams.model_validate(bad)


# --- what the recorder reads is in a stable order, and writes only what it did --------------------


def recorder(world: FakeWorld) -> Recorder:
    return Recorder(make_context(world, IDENTITY), IDENTITY)


def test_schedules_and_activities_are_read_in_code_and_id_order() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    world.define_schedule("ZED", "Zed schedule", activities=(("A9", "last"), ("A1", "first")))
    world.define_schedule("ALP", "Alpha schedule", activities=(("B2", "x"), ("B1", "y")))
    rec = recorder(world)
    found = rec.schedules()
    assert [s.code for s in found] == ["ALP", "ZED"]
    assert [a.id for a in rec.activities(found[0])] == ["B1", "B2"]
    assert [a.id for a in rec.activities(found[1])] == ["A1", "A9"]
    assert (found[0].current, found[0].snapshots, found[0].title) == (1, 1, "Alpha schedule")


def test_the_activities_are_cut_to_the_limit_in_id_order() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    world.define_schedule(activities=tuple((f"A{n}", f"n{n}") for n in (3, 1, 2)))
    rec = recorder(world)
    [sched] = rec.schedules()
    assert [a.id for a in rec.activities(sched, limit=2)] == ["A1", "A3"]  # the client cuts first


def test_a_schedule_without_a_published_snapshot_has_no_current_number() -> None:
    world = project(published=False)
    [sched] = recorder(world).schedules()
    assert (sched.current, sched.snapshots) == (None, 0)


def test_the_title_of_an_activity_reference_is_cut_where_the_module_cuts_it() -> None:
    world = project(activities=(("A1", "x" * 300),))
    rec = recorder(world)
    [sched] = rec.schedules()
    [activity] = rec.activities(sched)
    [record] = rec.records("", title_prefix="Activity ")[:1]
    assert rec.link_activity(record, sched, activity)
    [ref, _] = rec.truth
    assert ref.expect["title"] == "A1 " + "x" * 197
    [made] = [r for r in world.records() if r["type"] == "schedule.ActivityRef"]
    assert made["title"] == ref.expect["title"]  # the fake world cuts it as the module does


def test_the_snapshot_key_and_title_come_from_the_answer() -> None:
    world = project()
    rec = recorder(world)
    [sched] = rec.schedules()
    snapshot = rec.send_update(sched, "u.xer", b"bytes")
    assert (snapshot.key, snapshot.title) == ("MAIN#2", "Main schedule snapshot 2")
    assert [t.intent for t in rec.truth] == [gt.RECORD_CREATED, gt.SNAPSHOT_QUEUED]
    assert rec.truth[1].ref == "MAIN#2"


def test_linking_again_says_so_and_records_nothing() -> None:
    world = project(records=1)
    rec = recorder(world)
    [sched] = rec.schedules()
    [activity, *_] = rec.activities(sched)
    [record] = rec.records("", title_prefix="Activity ")
    assert rec.link_activity(record, sched, activity) is True
    made = len(rec.truth)
    assert rec.link_activity(record, sched, activity) is False
    assert len(rec.truth) == made
