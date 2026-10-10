"""The document controller on an in-memory world (tl_sim.testing). Provided by the supervisor."""

from __future__ import annotations

from typing import Any, cast

from tl_sim import groundtruth as gt
from tl_sim.actors.base import Recorder
from tl_sim.actors.document_controller import DocumentController
from tl_sim.scenario import CountRange, DocumentControllerParams
from tl_sim.testing import FakeClient, FakeWorld, make_context, seed_lines
from tl_sim.types import GroundTruth

IDENTITY = "user:sim-document_controller"


def world_with_lines(lines: int = 3) -> FakeWorld:
    world = FakeWorld("r1", "project:sim-r1")
    seed_lines(world, lines)
    return world


def step(world: FakeWorld, *, seed: int = 1, day: int = 0, **params: Any) -> list[GroundTruth]:
    actor = DocumentController(DocumentControllerParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, day=day))


def titles(world: FakeWorld, prefix: str = "Doc ") -> list[str]:
    return [r["title"] for r in world.records() if r["title"].startswith(prefix)]


def test_identity_and_name_follow_the_contract() -> None:
    actor = DocumentController(DocumentControllerParams())
    assert (actor.name, actor.identity) == ("document_controller", IDENTITY)


def test_with_no_lines_it_does_nothing() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    assert step(world) == []
    assert world.records() == [] and world.posts() == []


def test_each_document_is_created_linked_to_a_line_and_submitted() -> None:
    world = world_with_lines()
    truth = step(world, documents_per_day=2, revision_rate=0.0)
    docs = [r for r in world.records() if r["title"].startswith("Doc ")]
    assert len(docs) == 2
    assert all(r["status"] == "Review" for r in docs)
    assert [r["title"][:7] for r in docs] == ["Doc 001", "Doc 002"]
    assert all(r["title"].endswith(" Rev A") for r in docs)
    by_key = {r["key"]: r for r in world.records()}
    for doc in docs:
        out = [v for v in world.links(doc["id"]) if v["direction"] == "out"]
        assert [v["relation"] for v in out] == ["references"]
        assert by_key[out[0]["other_key"]]["title"].startswith("Line ")
    kinds = [(t.intent, t.expect.get("title") or t.expect.get("status")) for t in truth]
    assert [k[0] for k in kinds] == [
        gt.RECORD_CREATED,
        gt.LINK_ADDED,
        gt.WORKFLOW_TRANSITIONED,
        gt.RECORD_CREATED,
        gt.LINK_ADDED,
        gt.WORKFLOW_TRANSITIONED,
        gt.POST_CREATED,
    ]
    assert truth[2].expect == {"status": "Review", "transition": "submit"}
    assert all(t.actor == IDENTITY for t in truth)


def test_one_post_lists_every_document_with_its_key_as_a_tag() -> None:
    world = world_with_lines()
    step(world, documents_per_day=2, revision_rate=0.0)
    keys = [r["key"] for r in world.records() if r["title"].startswith("Doc ")]
    (post,) = world.posts()
    assert post["actor"] == IDENTITY
    assert post["body"] == f"Registered 2 documents: #{keys[0]} #{keys[1]}"


def test_nothing_made_means_no_post() -> None:
    world = world_with_lines()
    assert step(world, documents_per_day=0, revision_rate=0.0) == []
    assert world.posts() == []


def test_the_serial_continues_on_the_next_day() -> None:
    world = world_with_lines()
    step(world, documents_per_day=2, revision_rate=0.0, day=0)
    step(world, documents_per_day=1, revision_rate=0.0, day=1)
    assert [t[:7] for t in titles(world)] == ["Doc 001", "Doc 002", "Doc 003"]


def test_a_forced_revision_supersedes_the_latest_document_and_is_submitted() -> None:
    world = world_with_lines()
    step(world, documents_per_day=1, revision_rate=0.0)
    truth = step(world, documents_per_day=0, forced_revisions=1, day=1)
    docs = [r for r in world.records() if r["title"].startswith("Doc ")]
    assert [r["title"][-5:] for r in docs] == ["Rev A", "Rev B"]
    old, new = docs
    assert old["title"][:-5] == new["title"][:-5]
    assert new["status"] == "Review"
    out = {
        (v["relation"], v["other_key"]) for v in world.links(new["id"]) if v["direction"] == "out"
    }
    assert ("supersedes", old["key"]) in out
    assert any(rel == "references" for rel, _ in out)
    assert [t.intent for t in truth] == [
        gt.RECORD_CREATED,
        gt.LINK_ADDED,
        gt.LINK_ADDED,
        gt.WORKFLOW_TRANSITIONED,
        gt.POST_CREATED,
    ]
    assert world.posts()[-1]["body"] == f"Registered 1 document: #{new['key']}"


def test_a_second_revision_goes_to_the_newest_letter() -> None:
    world = world_with_lines()
    step(world, documents_per_day=1, revision_rate=0.0)
    step(world, documents_per_day=0, forced_revisions=1, day=1)
    step(world, documents_per_day=0, forced_revisions=1, day=2)
    assert [t[-5:] for t in titles(world)] == ["Rev A", "Rev B", "Rev C"]


def test_rev_z_is_the_last_revision_and_is_never_revised() -> None:
    world = world_with_lines()
    ctx = make_context(world, "user:sim-document_controller")
    maker = Recorder(ctx, "user:sim-document_controller")
    doc = maker.create("Doc 001 Piping isometric Rev Z")
    maker.link(doc, maker.records(title_prefix="Line ")[0], "references")
    maker.transition(doc, "submit", "Review")
    assert step(world, documents_per_day=0, forced_revisions=3, day=1) == []
    assert titles(world) == ["Doc 001 Piping isometric Rev Z"]


def test_a_revision_needs_a_document_in_review_or_approved() -> None:
    world = world_with_lines()
    assert step(world, documents_per_day=0, forced_revisions=2) == []
    assert titles(world) == []


def test_a_revision_rate_of_one_revises_once_a_day() -> None:
    world = world_with_lines()
    step(world, documents_per_day=1, revision_rate=0.0)
    step(world, documents_per_day=0, revision_rate=1.0, day=1)
    assert len(titles(world)) == 2


def test_the_same_seed_gives_the_same_day_and_another_seed_a_different_one() -> None:
    first, second, other = world_with_lines(), world_with_lines(), world_with_lines()
    params: dict[str, Any] = {"documents_per_day": CountRange(min=2, max=2), "revision_rate": 0.0}
    a = step(first, seed=7, **params)
    b = step(second, seed=7, **params)
    c = step(other, seed=8, **params)
    assert [gt.to_line(t) for t in a] == [gt.to_line(t) for t in b]
    assert [gt.to_line(t) for t in a] != [gt.to_line(t) for t in c]


def test_the_draws_happen_in_the_documented_order() -> None:
    """Pinned for seed 3 and three lines: a different order of draws gives different documents."""
    world = world_with_lines()
    step(world, seed=3, documents_per_day=2, revision_rate=0.0)
    assert titles(world) == [
        "Doc 001 Civil procedure Rev A",
        "Doc 002 Mechanical isometric Rev A",
    ]
    by_key = {r["key"]: r["title"] for r in world.records()}
    lines = [
        by_key[v["other_key"]]
        for r in world.records()
        if r["title"].startswith("Doc ")
        for v in world.links(r["id"])
        if v["direction"] == "out"
    ]
    assert lines == ["Line 6-CS-1002", "Line 6-CS-1003"]


def test_it_reads_and_writes_only_through_the_client() -> None:
    world = world_with_lines()
    actor = DocumentController(DocumentControllerParams(documents_per_day=1, revision_rate=0.0))
    ctx = make_context(world, actor.identity)
    actor.step(ctx)
    assert {name for name, _ in cast(FakeClient, ctx.client).calls} <= {
        "query",
        "create_record",
        "link",
        "transition",
        "post",
    }
