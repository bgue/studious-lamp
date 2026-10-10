"""``sim_assert``: a faithful world passes, and each kind of drift is named."""

from __future__ import annotations

from datetime import date

import pytest
from tl_sim import groundtruth as gt
from tl_sim.actors.base import Rec, Recorder
from tl_sim.assertions import AssertionReport, run_assertions
from tl_sim.testing import FakeWorld, make_context
from tl_sim.types import GroundTruth

IDENTITY = "user:sim-crew"
PLAYED = {date(2026, 11, 2)}


def play() -> tuple[FakeWorld, list[GroundTruth]]:
    """Two records, a pset, a link, two transitions, a post and a proposal."""
    world = FakeWorld("r1", "project:sim-r1")
    world.keys.counters.clear()
    rec = Recorder(make_context(world, IDENTITY), IDENTITY)
    line = rec.create("Line 6-CS-1001")
    valve = rec.create("Valve V001 6in on 6-CS-1001")
    rec.set_psets(valve, {"valve_data": {"size_in": 6, "manufacturer": "Crane"}})
    rec.link(valve, line, "belongs_to")
    rec.link(valve, line, "references")
    rec.transition(valve, "submit", "Review")
    rec.transition(valve, "approve", "Approved")
    rec.post(f"Installed #{valve.key}")
    rec.post("Same words")
    rec.post("Same words")
    return world, rec.truth


def check(world: FakeWorld, truth: list[GroundTruth]) -> AssertionReport:
    return run_assertions(truth, world, run_id="r1", played=PLAYED)


def failures(report: AssertionReport) -> set[tuple[str, str]]:
    return {(f.check, f.field) for f in report.failures}


def test_a_faithful_world_passes() -> None:
    world, truth = play()
    report = check(world, truth)
    assert report.ok, [f.line() for f in report.failures]
    assert report.checked > 15
    assert report.counts[gt.POST_CREATED] == 3


def test_a_missing_record_is_reported() -> None:
    world, truth = play()
    del world.record_rows[1]
    assert ("record.created", "exists") in failures(check(world, truth))


@pytest.mark.parametrize(
    ("field", "value", "expected_check"),
    [
        ("title", "Renamed", "record.created"),
        ("voided", True, "record.created"),
        ("type", "other.Type", "record.created"),
    ],
)
def test_a_record_that_differs_is_reported(field: str, value: object, expected_check: str) -> None:
    world, truth = play()
    world.record_rows[0][field] = value
    report = check(world, truth)
    assert not report.ok and expected_check in {f.check for f in report.failures}


def test_a_wrong_pset_value_is_reported_and_a_number_compares_as_a_number() -> None:
    world, truth = play()
    world.record_rows[1]["psets"]["valve_data"]["size_in"] = 6.0
    assert check(world, truth).ok  # 6 and 6.0 are the same size
    world.record_rows[1]["psets"]["valve_data"]["size_in"] = 8
    assert ("pset.set", "psets.valve_data.size_in") in failures(check(world, truth))


def test_only_the_latest_intent_for_a_field_is_checked() -> None:
    world, truth = play()
    rec = Recorder(make_context(world, IDENTITY), IDENTITY)
    valve = Rec.of([r for r in world.records() if r["title"].startswith("Valve")][0])
    rec.set_psets(valve, {"valve_data": {"size_in": 8}})  # the world now holds 8, the log 6 then 8
    assert check(world, truth + rec.truth).ok
    world.record_rows[1]["psets"]["valve_data"]["size_in"] = 6  # the earlier value is not enough
    assert ("pset.set", "psets.valve_data.size_in") in failures(check(world, truth + rec.truth))


def test_a_wrong_workflow_state_is_reported() -> None:
    world, truth = play()
    world.record_rows[1]["status"] = "Review"  # the log says Approved
    assert ("workflow.transitioned", "status") in failures(check(world, truth))


def test_a_missing_or_inactive_link_is_reported() -> None:
    world, truth = play()
    world.link_rows[1]["view"]["status"] = "suggested"
    assert ("link.added", "active link") in failures(check(world, truth))
    world.link_rows.clear()
    assert len([f for f in check(world, truth).failures if f.check == "link.added"]) == 2


def test_a_link_in_the_wrong_direction_or_relation_does_not_count() -> None:
    world, truth = play()
    world.link_rows[0]["from_id"], world.link_rows[0]["to_id"] = (
        world.link_rows[0]["to_id"],
        world.link_rows[0]["from_id"],
    )
    assert ("link.added", "active link") in failures(check(world, truth))


def test_every_intended_post_needs_its_own_post() -> None:
    world, truth = play()
    world.post_rows.pop()  # one of the two identical posts is gone
    report = check(world, truth)
    assert [f.check for f in report.failures] == ["post.created"]


def test_a_retracted_post_does_not_count() -> None:
    world, truth = play()
    world.post_rows[0]["retracted"] = True
    assert ("post.created", "post") in failures(check(world, truth))


def test_a_record_nobody_intended_is_reported() -> None:
    world, truth = play()
    stray = Recorder(make_context(world, "user:sim-planner"), "user:sim-planner")
    stray.create("Stray")
    report = check(world, truth)
    assert ("unexpected_record", "key") in failures(report)


def test_an_event_from_another_source_is_reported() -> None:
    world, truth = play()
    world.event_rows[0]["source"] = "api"
    assert ("event_source", "source") in failures(check(world, truth))
    world.event_rows[0]["source"] = "mcp:agent:sim-assistant"
    assert check(world, truth).ok  # a proposal made over MCP is the simulator too


def test_an_event_by_an_actor_that_is_not_simulated_is_reported() -> None:
    world, truth = play()
    world.event_rows[0]["actor"] = "user:alice"
    assert ("event_actor", "actor") in failures(check(world, truth))
    world.event_rows[0]["actor"] = (
        "agent:sim-assistant"  # a simulated actor, but not the one logged
    )
    seen = failures(check(world, truth))
    assert ("event_actor", "actor") not in seen
    assert ("actor_mismatch", "record.created by") in seen


def test_a_record_written_by_the_wrong_simulated_actor_fails() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    wrong = Recorder(make_context(world, "user:sim-planner"), "user:sim-crew")  # writes as planner
    wrong.create("Valve V001")
    report = check(world, wrong.truth)  # the log says the crew did it
    assert [(f.check, f.expected, f.actual) for f in report.failures] == [
        ("actor_mismatch", "user:sim-crew", ["user:sim-planner"])
    ]


@pytest.mark.parametrize("intent", ["pset", "link", "transition", "post"])
def test_every_kind_of_write_is_checked_against_the_actor_of_its_event(intent: str) -> None:
    world, truth = play()
    wanted = {
        "pset": "Pset.ValuesSet",
        "link": "Link.Added",
        "transition": "Workflow.Transitioned",
        "post": "Feed.Posted",
    }[intent]
    for event in world.event_rows:
        if event["event_type"] == wanted:
            event["actor"] = "user:sim-planner"
    report = check(world, truth)
    assert {f.check for f in report.failures} == {"actor_mismatch"}, intent
    assert report.failures


def test_an_empty_log_fails_closed() -> None:
    world, _ = play()
    report = check(world, [])
    assert not report.ok and [f.check for f in report.failures] == ["empty_ground_truth"]


def test_an_event_on_a_day_that_was_not_played_is_reported() -> None:
    world, truth = play()
    world.event_rows[2]["effective_at"] = "2026-12-25T07:00:00+00:00"
    assert ("event_time", "effective_at") in failures(check(world, truth))


def test_proposals_are_matched_one_to_one() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    rec = Recorder(make_context(world, IDENTITY, propose=True), IDENTITY)
    rec.propose("link_records", {"a": 1})
    assert check(world, rec.truth).ok
    world.proposal_rows.clear()
    assert ("proposal.created", "proposal") in failures(check(world, rec.truth))
