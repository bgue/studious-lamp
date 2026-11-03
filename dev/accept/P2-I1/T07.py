"""Acceptance for P2-I1-T07: the simulator's ``AwpDesk`` and the ``workface_planner`` actor.

Run: ``uv run python dev/accept/P2-I1/T07.py`` (no database and no server: ``FakeWorld`` and a stub
MCP caller; nothing goes over a network). Prints one ``PASS <check>`` line per check, then
``T07 ok``. A failed check raises and the script exits non-zero.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from tl_sim import groundtruth as gt
from tl_sim.actors.approver import Approver
from tl_sim.actors.base import BaseActor
from tl_sim.actors.registry import build_actor
from tl_sim.actors.workface_planner import WorkfacePlanner
from tl_sim.client import HttpSimClient, Keys
from tl_sim.clock import SimClock
from tl_sim.mcp_caller import ProposalRefusedError
from tl_sim.orchestrator_names import ASSISTANT
from tl_sim.scenario import ROLE_NAMES, ApproverParams, Scenario, WorkfacePlannerParams
from tl_sim.testing import FakeWorld, make_context

AREAS = ["A1", "A2", "A3"]
PROJECT = "sim-r1"
MOMENT = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


class Failed(Exception):
    pass


def passed(check: str) -> None:
    print(f"PASS {check}")


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def world(areas: list[str] = AREAS) -> FakeWorld:
    made = FakeWorld("r1", f"project:{PROJECT}")
    made.area_codes = list(areas)
    return made


def plan(target: FakeWorld, *, seed: int = 1) -> list[Any]:
    planner = WorkfacePlanner(WorkfacePlannerParams(cwps_per_day=3))
    return planner.step(make_context(target, planner.identity, seed=seed, propose=True))


class StubMcp:
    """Answers ``call_tool`` with a fixed structured result and remembers the call."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return self.answer


def areas_of(answer: dict[str, Any]) -> tuple[list[str], StubMcp]:
    stub = StubMcp(answer)
    desk = HttpSimClient(
        None,  # type: ignore[arg-type]  # areas() never touches the API
        run_id="r1",
        scope=f"project:{PROJECT}",
        clock=SimClock(MOMENT),
        keys=Keys("r1", {}),
        identity=ASSISTANT,
        mcp=stub,
    )
    return desk.areas(), stub


def main() -> None:
    # --- the planner proposes, the approver accepts ---------------------------------------------
    full = world()
    truth = plan(full)
    rows = full.proposals()
    need(
        len(rows) == 3
        and all(row["tool"] == "propose_cwp" and row["status"] == "pending" for row in rows),
        f"proposals: {[(r['tool'], r['status']) for r in rows]}",
    )
    need(full.cwp_rows == [], "a proposal created a CWP before it was accepted")
    need(
        sum(1 for item in truth if item.intent == gt.PROPOSAL_CREATED) == 3,
        f"ground truth: {[item.intent for item in truth]}",
    )
    passed("proposed (3 pending propose_cwp, no CWP yet, 3 PROPOSAL_CREATED)")

    approver = Approver(ApproverParams(accept_rate=1.0))
    approver.step(make_context(full, approver.identity, seed=1, propose=True))
    need(len(full.cwp_rows) == 3, f"{len(full.cwp_rows)} CWPs after accepting")
    need(all(row["cwa"] in AREAS for row in full.cwp_rows), "a CWP outside the areas")
    need(all(row["title"].endswith(row["cwa"]) for row in full.cwp_rows), "a title without area")
    need(all(row["status"] == "accepted" for row in full.proposals()), "not all accepted")
    passed("accepted (3 CWPs, each in an area, titles end with the area)")

    # --- no areas: nothing to propose -----------------------------------------------------------
    empty = world([])
    need(plan(empty) == [] and empty.proposals() == [], "a planner proposed with no areas")
    passed("no areas (no proposal)")

    # --- a refused area ---------------------------------------------------------------------
    refusing = make_context(world(), ASSISTANT, propose=True)
    try:
        refusing.client.propose(
            "propose_cwp",
            {"project": PROJECT, "discipline": "CIV", "title": "Footings Z9", "cwa_code": "Z9"},
        )
    except ProposalRefusedError:
        passed("refused (an area outside the path)")
    else:
        raise Failed("a cwa_code outside the areas was accepted")

    # --- the same seed gives the same proposals -----------------------------------------------
    first, second = world(), world()
    plan(first, seed=1)
    plan(second, seed=1)
    titles = [row["command"]["title"] for row in first.proposals()]
    need(titles and titles == [row["command"]["title"] for row in second.proposals()], "seeds")
    passed(f"same seed ({', '.join(titles)})")

    # --- off unless named; the order and ROLE_NAMES ---------------------------------------------
    base: dict[str, Any] = {"scenario": "t", "seed": 1, "start": date(2026, 11, 2)}
    off = Scenario.model_validate(base).actors.enabled()
    need("workface_planner" not in off, f"enabled by default: {off}")
    on = Scenario.model_validate(
        {**base, "actors": {"workface_planner": {}, "assistant": {}, "approver": {}}}
    ).actors.enabled()
    agents = [name for name in on if name in ("assistant", "workface_planner", "approver")]
    need(agents == ["assistant", "workface_planner", "approver"], f"order: {agents}")
    need(
        ROLE_NAMES
        == (
            "document_controller",
            "planner",
            "crew",
            "tag_clerk",
            "document_registrar",
            "schedule_updater",
            "rfi_author",
            "client_rep",
        ),
        "ROLE_NAMES changed",
    )
    passed("off by default (order assistant, workface_planner, approver; ROLE_NAMES unchanged)")

    # --- the registry ---------------------------------------------------------------------------
    built = build_actor("workface_planner", WorkfacePlannerParams())
    need(isinstance(built, WorkfacePlanner) and isinstance(built, BaseActor), "registry")
    passed("registry (build_actor gives a WorkfacePlanner)")

    # --- the real client's read of the path, wrapped or not (not in the ticket's list) ---------
    steps = [{"cwa": "A1"}, {"cwa": None}, {"cwa": "A2"}]
    wrapped, stub = areas_of({"result": {"steps": steps}})
    need(wrapped == ["A1", "A2"], f"wrapped answer gave {wrapped}")
    need(stub.calls == [("path_of_construction", {"project": PROJECT})], f"calls {stub.calls}")
    need(areas_of({"result": None})[0] == [], "a null path is not no areas")
    need(areas_of({"steps": [{"cwa": "A3"}]})[0] == ["A3"], "a bare PathView")
    passed("areas (path_of_construction via call_tool; result unwrapped; null path gives [])")

    print("T07 ok")


if __name__ == "__main__":
    main()
