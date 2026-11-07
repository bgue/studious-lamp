"""The workface planner actor and the simulator's AwpDesk (P2-I1-T07, D43-D45)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from tl_sim import groundtruth as gt
from tl_sim.actors.approver import Approver
from tl_sim.actors.base import BaseActor
from tl_sim.actors.registry import build_actor
from tl_sim.actors.workface_planner import WorkfacePlanner
from tl_sim.client import HttpSimClient, Keys
from tl_sim.clock import SimClock
from tl_sim.mcp_caller import McpUnavailableError, ProposalRefusedError
from tl_sim.orchestrator import all_identities
from tl_sim.orchestrator_names import ASSISTANT, ORCHESTRATOR
from tl_sim.scenario import (
    ACTOR_NAMES,
    ROLE_NAMES,
    ApproverParams,
    Scenario,
    WorkfacePlannerParams,
)
from tl_sim.testing import FakeWorld, make_context

AREAS = ["A1", "A2", "A3"]
PROJECT = "sim-r1"
MOMENT = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
BASE: dict[str, Any] = {"scenario": "t", "seed": 1, "start": date(2026, 11, 2)}


def world(areas: list[str] = AREAS) -> FakeWorld:
    made = FakeWorld("r1", f"project:{PROJECT}")
    made.area_codes = list(areas)
    return made


def plan(target: FakeWorld, *, seed: int = 1) -> list[Any]:
    planner = WorkfacePlanner(WorkfacePlannerParams(cwps_per_day=3))
    return planner.step(make_context(target, planner.identity, seed=seed, propose=True))


def test_the_planner_files_three_pending_proposals_and_creates_no_cwp() -> None:
    target = world()
    truth = plan(target)
    rows = target.proposals()
    assert len(rows) == 3
    assert all(row["tool"] == "propose_cwp" and row["status"] == "pending" for row in rows)
    assert target.cwp_rows == []  # a proposal creates nothing until it is accepted
    assert sum(1 for item in truth if item.intent == gt.PROPOSAL_CREATED) == 3


def test_the_approver_accepts_all_three_and_each_cwp_lands_in_an_area() -> None:
    target = world()
    plan(target)
    approver = Approver(ApproverParams(accept_rate=1.0))
    approver.step(make_context(target, approver.identity, seed=1, propose=True))
    assert len(target.cwp_rows) == 3
    assert all(row["cwa"] in AREAS for row in target.cwp_rows)
    assert all(row["title"].endswith(row["cwa"]) for row in target.cwp_rows)
    assert all(row["status"] == "accepted" for row in target.proposals())


def test_the_draws_come_in_a_fixed_order_for_a_seed() -> None:
    first, second, other = world(), world(), world()
    plan(first, seed=1)
    plan(second, seed=1)
    plan(other, seed=2)
    titles = [row["command"]["title"] for row in first.proposals()]
    assert len(titles) == 3
    assert titles == [row["command"]["title"] for row in second.proposals()]
    assert titles != [row["command"]["title"] for row in other.proposals()]


def test_with_no_areas_nothing_is_proposed() -> None:
    empty = world([])
    assert plan(empty) == []
    assert empty.proposals() == []


def test_an_area_outside_the_path_is_refused() -> None:
    context = make_context(world(), ASSISTANT, propose=True)
    with pytest.raises(ProposalRefusedError):
        context.client.propose(
            "propose_cwp",
            {"project": PROJECT, "discipline": "CIV", "title": "Footings Z9", "cwa_code": "Z9"},
        )


def test_the_actor_order_is_assistant_planner_approver_and_off_by_default() -> None:
    assert ACTOR_NAMES[-5:] == (
        "assistant",
        "workface_planner",
        "iwp_planner",
        "materials_coordinator",
        "approver",
    )
    assert ACTOR_NAMES[:-5] == ROLE_NAMES
    assert "workface_planner" not in Scenario.model_validate(BASE).actors.enabled()
    on = Scenario.model_validate(
        {**BASE, "actors": {"workface_planner": {}, "assistant": {}, "approver": {}}}
    ).actors.enabled()
    assert [n for n in on if n in ACTOR_NAMES[-5:]] == [
        "assistant",
        "workface_planner",
        "approver",
    ]


def test_the_role_names_and_the_provisioned_identities_are_unchanged() -> None:
    """D45: the planner is the assistant's agent identity; no new account is provisioned."""
    assert ROLE_NAMES == (
        "document_controller",
        "planner",
        "crew",
        "tag_clerk",
        "document_registrar",
        "schedule_updater",
        "rfi_author",
        "client_rep",
    )
    assert all_identities() == [
        ORCHESTRATOR,
        "user:sim-document_controller",
        "user:sim-planner",
        "user:sim-crew",
        "user:sim-tag_clerk",
        "user:sim-document_registrar",
        "user:sim-schedule_updater",
        "user:sim-rfi_author",
        "user:sim-client_rep",
        "user:sim-approver",
        "user:sim-iwp_planner",
        ASSISTANT,
    ]
    assert WorkfacePlanner(WorkfacePlannerParams()).identity == ASSISTANT


def test_the_registry_builds_the_planner() -> None:
    built = build_actor("workface_planner", WorkfacePlannerParams())
    assert isinstance(built, WorkfacePlanner)
    assert isinstance(built, BaseActor)


class StubMcp:
    """Answers ``call_tool`` with a fixed structured result and remembers the call."""

    def __init__(self, answer: dict[str, Any] | None = None, fail: bool = False) -> None:
        self.answer = answer
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if self.fail or self.answer is None:
            raise McpUnavailableError("no MCP")
        return self.answer


def desk(stub: StubMcp | None, scope: str = f"project:{PROJECT}") -> HttpSimClient:
    return HttpSimClient(
        None,  # type: ignore[arg-type]  # areas() never touches the API
        run_id="r1",
        scope=scope,
        clock=SimClock(MOMENT),
        keys=Keys("r1", {}),
        identity=ASSISTANT,
        mcp=stub,  # type: ignore[arg-type]
    )


def test_areas_reads_the_path_through_the_tool_and_skips_a_step_without_an_area() -> None:
    """T07 report: HttpSimClient has no ``_project``; the project comes from ``_scope``."""
    stub = StubMcp({"result": {"steps": [{"cwa": "A1"}, {"cwa": None}, {"cwa": "A2"}]}})
    assert desk(stub).areas() == ["A1", "A2"]
    assert stub.calls == [("path_of_construction", {"project": PROJECT})]


def test_areas_takes_a_wrapped_a_null_and_a_bare_answer() -> None:
    assert desk(StubMcp({"result": None})).areas() == []
    assert desk(StubMcp({"steps": [{"cwa": "A3"}]})).areas() == ["A3"]


def test_areas_without_an_mcp_caller_raises_mcp_unavailable() -> None:
    with pytest.raises(McpUnavailableError):
        desk(None).areas()
    with pytest.raises(McpUnavailableError):
        desk(StubMcp(fail=True)).areas()
