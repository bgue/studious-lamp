"""The planner on an in-memory world (``tl_sim.testing``). Provided by the supervisor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from tl_sim import groundtruth as gt
from tl_sim.actors.base import Recorder
from tl_sim.actors.planner import Planner
from tl_sim.scenario import CountRange, PlannerParams
from tl_sim.testing import FakeClient, FakeWorld, make_context, seed_lines
from tl_sim.types import GroundTruth

IDENTITY = "user:sim-planner"
PINNED = [
    "Activity 001 Install spools on 6-CS-1002",
    "Activity 002 Install spools on 6-CS-1003",
    "Activity 003 Install spools on 6-CS-1002",
    "Activity 004 Install spools on 6-CS-1002",
]
MONDAY = datetime(2026, 11, 2, 7, 30, tzinfo=UTC)
TUESDAY = datetime(2026, 11, 3, 7, 30, tzinfo=UTC)


def world_with_documents(documents: int = 3, lines: int = 3, *, linked: bool = True) -> FakeWorld:
    """Lines plus ``documents`` records ``Doc 00n ...`` submitted for review."""
    world = FakeWorld("r1", "project:sim-r1")
    found = seed_lines(world, lines)
    ctx = make_context(world, "user:sim-document_controller")
    maker = Recorder(ctx, "user:sim-document_controller")
    for n in range(1, documents + 1):
        doc = maker.create(f"Doc {n:03d} Piping isometric Rev A")
        if linked:
            maker.link(doc, found[0], "references")
        maker.transition(doc, "submit", "Review")
    return world


def step(
    world: FakeWorld, *, seed: int = 1, now: datetime = TUESDAY, **params: Any
) -> list[GroundTruth]:
    actor = Planner(PlannerParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, now=now))


def statuses(world: FakeWorld) -> dict[str, str | None]:
    return {r["title"][:7]: r["status"] for r in world.records() if r["title"].startswith("Doc ")}


def test_identity_and_name_follow_the_contract() -> None:
    actor = Planner(PlannerParams())
    assert (actor.name, actor.identity) == ("planner", IDENTITY)


def test_it_approves_the_first_documents_in_review_in_key_order() -> None:
    world = world_with_documents(3)
    truth = step(world, approvals_per_day=2, activities_per_day=0, lookahead_day=None)
    assert statuses(world) == {"Doc 001": "Approved", "Doc 002": "Approved", "Doc 003": "Review"}
    assert [(t.intent, t.expect) for t in truth] == [
        (gt.WORKFLOW_TRANSITIONED, {"status": "Approved", "transition": "approve"})
    ] * 2
    assert all(t.actor == IDENTITY for t in truth)


def test_a_refused_approval_leaves_the_document_waiting_and_records_nothing() -> None:
    world = world_with_documents(2, linked=False)  # the approve guard needs a references link
    truth = step(world, approvals_per_day=2, activities_per_day=0, lookahead_day=None)
    assert truth == []
    assert set(statuses(world).values()) == {"Review"}


def test_each_activity_belongs_to_a_line_and_requires_an_approved_document() -> None:
    world = world_with_documents(1)
    truth = step(world, approvals_per_day=1, activities_per_day=2, lookahead_day=None)
    activities = [r for r in world.records() if r["title"].startswith("Activity ")]
    assert [a["title"][:12] for a in activities] == ["Activity 001", "Activity 002"]
    assert all(" Install spools on 6-CS-100" in a["title"] for a in activities)
    by_key = {r["key"]: r for r in world.records()}
    for activity in activities:
        out = {
            (v["relation"], by_key[v["other_key"]]["title"][:4])
            for v in world.links(activity["id"])
            if v["direction"] == "out"
        }
        assert out == {("belongs_to", "Line"), ("requires", "Doc ")}
    assert [t.intent for t in truth].count(gt.RECORD_CREATED) == 2


def test_with_no_approved_document_an_activity_only_belongs_to_a_line() -> None:
    world = world_with_documents(0)
    step(world, approvals_per_day=0, activities_per_day=1, lookahead_day=None)
    (activity,) = [r for r in world.records() if r["title"].startswith("Activity ")]
    assert [v["relation"] for v in world.links(activity["id"])] == ["belongs_to"]


def test_the_serial_of_activities_continues() -> None:
    world = world_with_documents(0)
    step(world, approvals_per_day=0, activities_per_day=2, lookahead_day=None)
    step(world, approvals_per_day=0, activities_per_day=1, lookahead_day=None, seed=2)
    titles = [r["title"][:12] for r in world.records() if r["title"].startswith("Activity ")]
    assert titles == ["Activity 001", "Activity 002", "Activity 003"]


def test_with_no_lines_nothing_is_planned() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    assert step(world, approvals_per_day=1, activities_per_day=3, lookahead_day=None) == []


def test_the_look_ahead_is_posted_on_the_configured_weekday_only() -> None:
    world = world_with_documents(0)
    step(world, activities_per_day=0, lookahead_day="mon", now=TUESDAY)
    assert world.posts() == []
    step(world, activities_per_day=0, lookahead_day=None, now=MONDAY)
    assert world.posts() == []
    truth = step(world, activities_per_day=0, lookahead_day="mon", now=MONDAY)
    assert [t.intent for t in truth] == [gt.POST_CREATED]
    assert (
        world.posts()[0]["body"]
        == "Look-ahead: 0 activities planned, 0 documents waiting for approval."
    )


def test_one_activity_and_one_waiting_document_are_singular() -> None:
    world = world_with_documents(2)
    step(world, approvals_per_day=1, activities_per_day=1, lookahead_day="mon", now=MONDAY)
    (post,) = world.posts()
    assert post["body"].startswith(
        "Look-ahead: 1 activity planned, 1 document waiting for approval."
    )


def test_the_look_ahead_names_up_to_three_activities_and_holds_on_waiting_documents() -> None:
    world = world_with_documents(3)
    step(
        world,
        approvals_per_day=1,
        activities_per_day=CountRange(min=4, max=4),
        lookahead_day="mon",
        now=MONDAY,
    )
    (post,) = world.posts()
    keys = {
        r["title"][:12]: r["key"] for r in world.records() if r["title"].startswith("Activity ")
    }
    waiting = [r for r in world.records() if r["title"].startswith("Doc 002")][0]
    assert post["body"] == (
        "Look-ahead: 4 activities planned, 2 documents waiting for approval."
        f" #{keys['Activity 001']} #{keys['Activity 002']} #{keys['Activity 003']}"
        f" #hold #{waiting['key']}"
    )


def test_the_same_seed_gives_the_same_day() -> None:
    a, b = world_with_documents(3), world_with_documents(3)
    params: dict[str, Any] = {
        "approvals_per_day": 1,
        "activities_per_day": CountRange(min=1, max=3),
    }
    assert [gt.to_line(t) for t in step(a, seed=5, **params)] == [
        gt.to_line(t) for t in step(b, seed=5, **params)
    ]


def test_the_draws_happen_in_the_documented_order() -> None:
    """Pinned for seed 7: approvals count, activities count, then one line per activity."""
    world = world_with_documents(0, lines=5)
    step(
        world,
        seed=7,
        approvals_per_day=CountRange(min=0, max=0),
        activities_per_day=CountRange(min=3, max=6),
        lookahead_day=None,
    )
    assert [r["title"] for r in world.records() if r["title"].startswith("Activity ")] == PINNED


def test_it_reads_and_writes_only_through_the_client() -> None:
    world = world_with_documents(2)
    actor = Planner(PlannerParams(activities_per_day=1, lookahead_day="mon"))
    ctx = make_context(world, actor.identity, now=MONDAY)
    actor.step(ctx)
    used = {name for name, _ in cast(FakeClient, ctx.client).calls}
    assert used <= {"query", "create_record", "link", "transition", "post"}
