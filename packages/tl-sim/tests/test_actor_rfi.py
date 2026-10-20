"""The RFI author and the client's representative on an in-memory world (P1-I6).

The world stands in for a project with a few lines; a controller issues the RFIs beside the run
(``FakeWorld.issue_rfi``). ``test_rfi_end_to_end.py`` plays the same on the real suite.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from tl_sim import groundtruth as gt
from tl_sim.actors.client_rep import ClientRep
from tl_sim.actors.rfi_author import DISCIPLINES, SUBJECT_PREFIX, TOPICS, RfiAuthor
from tl_sim.clock import SimClock
from tl_sim.scenario import ClientRepParams, RfiAuthorParams
from tl_sim.testing import FakeWorld, make_context, seed_lines
from tl_sim.types import GroundTruth

AUTHOR = "user:sim-rfi_author"
CLIENT = "user:sim-client_rep"
MONDAY = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


def project(lines: int = 3) -> FakeWorld:
    world = FakeWorld("r1", "project:sim-r1")
    seed_lines(world, lines)
    return world


def author(
    world: FakeWorld, *, seed: int = 1, day: int = 0, now: datetime = MONDAY, **params: Any
) -> list[GroundTruth]:
    actor = RfiAuthor(RfiAuthorParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, day=day, now=now))


def client(
    world: FakeWorld, *, seed: int = 1, day: int = 0, now: datetime = MONDAY, **params: Any
) -> list[GroundTruth]:
    actor = ClientRep(ClientRepParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, day=day, now=now))


def states(world: FakeWorld) -> dict[str, str | None]:
    return {r["key"]: r["status"] for r in world.record_rows if "RFI" in r["key"]}


def test_identity_and_name_follow_the_contract() -> None:
    assert (RfiAuthor(RfiAuthorParams()).name, RfiAuthor(RfiAuthorParams()).identity) == (
        "rfi_author",
        AUTHOR,
    )
    assert ClientRep(ClientRepParams()).identity == CLIENT


def test_the_author_raises_the_drawn_number_of_rfis_and_sends_them_to_review() -> None:
    world = project()
    truth = author(world, rfis_per_day=2)
    assert [t.intent for t in truth] == [gt.RECORD_CREATED, gt.RECORD_CREATED]
    assert [t.ref for t in truth] == ["SIMR1-RFI-0001", "SIMR1-RFI-0002"]
    for item in truth:
        assert item.actor == AUTHOR
        assert item.expect["record_type"] == "correspondence.TechnicalItem"
        assert (
            item.expect["title"].startswith(SUBJECT_PREFIX) and " at 6-CS-" in item.expect["title"]
        )
        assert any(topic in item.expect["title"] for topic in TOPICS)
    assert set(states(world).values()) == {"Internal review"}  # a controller issues them


def test_the_discipline_and_the_date_needed_are_sent_and_the_date_is_in_the_future() -> None:
    world = project()
    actor = RfiAuthor(RfiAuthorParams(rfis_per_day=1, answer_within_days=10))
    ctx = make_context(world, actor.identity, seed=3)
    actor.step(ctx)
    [raised] = [c for c in ctx.client.calls if c[0] == "raise_rfi"]  # type: ignore[attr-defined]
    subject, question, discipline, needed = raised[1]
    assert subject.startswith(SUBJECT_PREFIX) and subject.removeprefix(SUBJECT_PREFIX) in question
    assert discipline in DISCIPLINES
    assert date.fromisoformat(needed) == max(MONDAY.date(), date.today()) + timedelta(days=10)


def test_without_lines_the_subject_names_no_line() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    [item] = author(world, rfis_per_day=1)
    assert " at " not in item.expect["title"]


def test_zero_draws_write_nothing() -> None:
    world = project()
    actor = RfiAuthor(RfiAuthorParams(rfis_per_day=0))
    ctx = make_context(world, actor.identity, seed=4)
    assert actor.step(ctx) == [] and not [c for c in ctx.client.calls if c[0] == "raise_rfi"]  # type: ignore[attr-defined]
    assert states(world) == {}


def test_the_author_accepts_the_answers_and_leaves_other_peoples_rfis_alone() -> None:
    world = project()
    [first] = author(world, rfis_per_day=1)
    world.issue_rfi(first.ref)
    [answered] = client(world, answers_per_day=1)
    assert (answered.intent, answered.actor, answered.expect) == (
        gt.WORKFLOW_TRANSITIONED,
        CLIENT,
        {"status": "Answered", "transition": "answer"},
    )
    stranger = world.client("user:someone", SimClock(MONDAY)).raise_rfi(
        "Not ours", "q", "Civil", "2027-01-01"
    )
    world.client("user:someone", SimClock(MONDAY)).submit_rfi(stranger["id"])
    truth = author(world, rfis_per_day=0, day=1)
    assert [(t.ref, t.expect) for t in truth] == [
        (first.ref, {"status": "Accepted", "transition": "accept"})
    ]
    assert (
        states(world)[first.ref] == "Accepted"
        and states(world)[stranger["key"]] == "Internal review"
    )


def test_an_accept_rate_of_zero_leaves_the_answers_alone() -> None:
    world = project()
    [first] = author(world, rfis_per_day=1)
    world.issue_rfi(first.ref)
    client(world, answers_per_day=1)
    assert author(world, rfis_per_day=0, accept_rate=0, day=1) == []
    assert states(world)[first.ref] == "Answered"


def test_the_client_answers_only_what_was_issued_in_number_order_up_to_the_draw() -> None:
    world = project()
    raised = author(world, rfis_per_day=3, seed=2)
    assert len(raised) == 3
    assert client(world, answers_per_day=3) == []  # nothing is issued yet
    for item in raised[1:]:
        world.issue_rfi(item.ref)
    truth = client(world, answers_per_day=1)
    assert [t.ref for t in truth] == [raised[1].ref]  # the first issued one, by number
    assert [t.ref for t in client(world, answers_per_day=5, day=1)] == [raised[2].ref]
    assert states(world)[raised[0].ref] == "Internal review"


def test_the_impact_rate_decides_the_cost_statement() -> None:
    for rate, expected in ((1.0, "yes"), (0.0, "no")):
        world = project()
        [item] = author(world, rfis_per_day=1)
        world.issue_rfi(item.ref)
        ctx = make_context(world, CLIENT)
        ClientRep(ClientRepParams(answers_per_day=1, impact_rate=rate)).step(ctx)
        [call] = [c for c in ctx.client.calls if c[0] == "answer_rfi"]  # type: ignore[attr-defined]
        assert call[1][2:] == (expected, "no")


def test_the_same_seed_gives_the_same_rfis_and_a_different_one_does_not() -> None:
    def titles(seed: int) -> list[str]:
        return [t.expect["title"] for t in author(project(), seed=seed, rfis_per_day=3)]

    assert titles(5) == titles(5)
    assert titles(5) != titles(6)


def test_the_parameters_are_checked() -> None:
    bad: list[dict[str, Any]] = [{"accept_rate": 1.5}, {"answer_within_days": 0}, {"surprise": 1}]
    for params in bad:
        with pytest.raises(ValidationError):
            RfiAuthorParams(**params)
    with pytest.raises(ValidationError):
        ClientRepParams(impact_rate=-0.1)
