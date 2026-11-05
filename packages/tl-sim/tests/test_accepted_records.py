"""An accepted proposal's record is an intended record: the ground truth names it (P2-I1-T15)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

from tl_sim import groundtruth as gt
from tl_sim.actors.base import Recorder
from tl_sim.assertions import AssertionReport, Expected, run_assertions
from tl_sim.clock import SimClock
from tl_sim.testing import OPERATOR, REAL_TIME, FakeClient, FakeWorld, make_context
from tl_sim.types import GroundTruth

PROJECT = "sim-r1"
PLANNER = "agent:workface-planner"
APPROVER = "user:sim-approver"
PLAYED = {date(2026, 11, 2)}
CWP_ARGS = {"project": PROJECT, "discipline": "CIV", "title": "Form and pour", "cwa_code": "A1"}


class ApiLikeDesk(FakeClient):
    """The fake desk, answering as the API does on an accept of ``propose_cwp``.

    The API names the record an accept made by stream id (``result_stream_id``) and that record
    can be read back by id. The shared fake does neither, so this test double adds both.
    """

    def accept_proposal(self, proposal_id: str) -> dict[str, Any]:
        decided = super().accept_proposal(proposal_id)
        if decided["tool"] != "propose_cwp":
            return decided
        cwp = self.world.cwp_rows[-1]
        made = f"cwp-stream-{len(self.world.cwp_rows)}"
        self.world.record_rows.append(
            self.world._row(made, str(cwp["number"]), "awp.CWP", str(cwp["title"]), None)
        )
        self.world.emit("Record.Created", self.identity, "api", REAL_TIME, made)
        return {**decided, "result_stream_id": made}


def approver_recorder(world: FakeWorld) -> Recorder:
    base = make_context(world, APPROVER, propose=True)
    desk = ApiLikeDesk(world, APPROVER, SimClock(base.now), world.keys, (), True)
    return Recorder(replace(base, client=desk), APPROVER)


def file_cwp(world: FakeWorld) -> Recorder:
    planner = Recorder(make_context(world, PLANNER, propose=True), PLANNER)
    assert planner.propose("propose_cwp", dict(CWP_ARGS)) is not None
    return planner


def world() -> FakeWorld:
    made = FakeWorld("r1", f"project:{PROJECT}")
    made.area_codes = ["A1"]
    return made


def check(target: FakeWorld, truth: list[GroundTruth]) -> AssertionReport:
    return run_assertions(
        truth,
        target,
        run_id="r1",
        played=PLAYED,
        expected=Expected(operators=frozenset({OPERATOR})),
    )


def failed(report: AssertionReport) -> set[str]:
    return {f.check for f in report.failures}


def test_an_accepted_propose_cwp_notes_the_record_it_created() -> None:
    target = world()
    planner = file_cwp(target)
    approver = approver_recorder(target)
    (proposal,) = approver.pending()
    assert approver.decide(proposal, accept=True) is not None
    created = [item for item in approver.truth if item.intent == gt.RECORD_CREATED]
    assert len(created) == 1
    (item,) = created
    assert item.ref == f"{PROJECT}-CWP-CIV-0001"
    assert item.actor == APPROVER
    assert item.expect == {"title": "Form and pour", "record_type": "awp.CWP", "voided": False}
    assert [i.intent for i in approver.truth] == [gt.PROPOSAL_ACCEPTED, gt.RECORD_CREATED]
    assert [i.intent for i in planner.truth] == [gt.PROPOSAL_CREATED]


def test_the_accepted_cwp_is_no_unexpected_record() -> None:
    target = world()
    planner = file_cwp(target)
    approver = approver_recorder(target)
    (proposal,) = approver.pending()
    approver.decide(proposal, accept=True)
    report = check(target, planner.truth + approver.truth)
    assert "unexpected_record" not in failed(report), [f.line() for f in report.failures]


def test_a_rejected_propose_cwp_notes_no_record() -> None:
    target = world()
    file_cwp(target)
    approver = approver_recorder(target)
    (proposal,) = approver.pending()
    assert approver.decide(proposal, accept=False, reason="not this area") is not None
    assert all(item.intent != gt.RECORD_CREATED for item in approver.truth)
    assert target.cwp_rows == []
