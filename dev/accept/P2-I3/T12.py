"""Acceptance for P2-I3-T12: the simulator's ``MaterialsDesk`` and the materials coordinator.

Run: ``uv run python dev/accept/P2-I3/T12.py`` (no database, no server: a fake MCP caller stands in
for the suite's MCP server, and nothing goes over a network). Prints one ``PASS <check>`` line per
check.
A failed check raises and the script exits non-zero.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tl_sim import groundtruth as gt
from tl_sim.actors.materials_coordinator import MaterialsCoordinator
from tl_sim.client import HttpSimClient, Keys, ProposeUnavailableError
from tl_sim.clock import SimClock
from tl_sim.mcp_caller import ProposalRefusedError
from tl_sim.orchestrator_names import ASSISTANT
from tl_sim.rng import actor_rng
from tl_sim.scenario import CountRange, MaterialsCoordinatorParams
from tl_sim.types import SimContext

RUN = "r1"
PROJECT = "sim-r1"
MOMENT = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
SEED = 7

FLANGE = "FLG-2"
PIPE = "PIPE-6"
LINE_FLANGE = {"key": "ISO-1@A/MTO/001", "item_code": FLANGE, "short": "4"}
LINE_PIPE = {"key": "ISO-1@A/MTO/002", "item_code": PIPE, "short": "12"}
ROW_FLANGE = {"lot": "LOT-1", "location": "R-01", "item_code": FLANGE, "available": "10"}
ROW_PIPE = {"lot": "LOT-2", "location": "R-02", "item_code": PIPE, "available": "5"}
ROW_EMPTY = {"lot": "LOT-3", "location": "R-03", "item_code": FLANGE, "available": "0"}


class Failed(Exception):
    pass


def passed(check: str) -> None:
    print(f"PASS {check}")


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


class FakeMcp:
    """Answers the three tools the desk calls, as the MCP server does (a list under ``result``)."""

    def __init__(
        self,
        lines: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        *,
        refuse: bool = False,
    ) -> None:
        self.lines = lines
        self.rows = rows
        self.refuse = refuse
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        if name == "list_mto_lines":
            return {"result": list(self.lines)}
        if name == "list_material_stock":
            return {"result": list(self.rows)}
        if name == "propose_reservation":
            if self.refuse:
                raise ProposalRefusedError("the server refused the reservation")
            return {"result": {"status": "pending"}}
        raise AssertionError(f"unexpected tool {name}")

    def proposals(self) -> list[dict[str, Any]]:
        return [args for name, args in self.calls if name == "propose_reservation"]


def context(mcp: FakeMcp | None, *, seed: int = SEED, client: object | None = None) -> SimContext:
    desk = (
        client
        if client is not None
        else HttpSimClient(
            None,  # type: ignore[arg-type]  # the materials reads and proposals never touch the API
            run_id=RUN,
            scope=f"project:{PROJECT}",
            clock=SimClock(MOMENT),
            keys=Keys(RUN, {}),
            identity=ASSISTANT,
            mcp=mcp,
        )
    )
    return SimContext(
        run_id=RUN,
        scope=f"project:{PROJECT}",
        now=MOMENT,
        rng=actor_rng(seed, ASSISTANT, 0),
        client=desk,  # type: ignore[arg-type]
    )


def coordinator(reservations: int | CountRange) -> MaterialsCoordinator:
    return MaterialsCoordinator(MaterialsCoordinatorParams(reservations_per_day=reservations))


def check_no_short_lines() -> None:
    mcp = FakeMcp(lines=[], rows=[ROW_FLANGE])
    truth = coordinator(2).step(context(mcp))
    need(truth == [], f"ground truth without lines: {truth}")
    need(mcp.proposals() == [], f"proposal without short lines: {mcp.calls}")
    passed("no short lines: no call to propose_reservation")


def check_one_matching_proposal() -> None:
    mcp = FakeMcp(lines=[LINE_FLANGE], rows=[ROW_FLANGE])
    truth = coordinator(1).step(context(mcp))
    need(len(mcp.proposals()) == 1, f"proposals: {mcp.proposals()}")
    args = mcp.proposals()[0]
    need(args["lot"] == "LOT-1", f"lot: {args}")
    need(args["location"] == "R-01", f"location: {args}")
    need(args["mto_line"] == LINE_FLANGE["key"], f"line: {args}")
    need(args["qty"] == "4", f"quantity is the smaller of 10 and 4: {args}")
    need(args["project"] == PROJECT, f"project: {args}")
    need(len(truth) == 1 and truth[0].intent == gt.PROPOSAL_CREATED, f"truth: {truth}")
    need(truth[0].actor == ASSISTANT, f"actor of the proposal: {truth[0].actor}")
    passed("one short line, one matching row: one proposal (lot, location, line, quantity 4)")


def check_quantity_is_the_available() -> None:
    row = {**ROW_FLANGE, "available": "3"}
    mcp = FakeMcp(lines=[LINE_FLANGE], rows=[row])
    coordinator(1).step(context(mcp))
    need(mcp.proposals()[0]["qty"] == "3", f"quantity: {mcp.proposals()}")
    passed("quantity is the available when it is the smaller")


def check_other_item_no_proposal_same_draws() -> None:
    mcp = FakeMcp(lines=[LINE_FLANGE], rows=[ROW_PIPE])
    ctx = context(mcp)
    truth = coordinator(CountRange(min=1, max=1)).step(ctx)
    need(truth == [] and mcp.proposals() == [], f"proposal for another item: {mcp.calls}")
    # The reference draws what the day draws: the count, one line, one stock row, nothing more.
    reference = actor_rng(SEED, ASSISTANT, 0)
    reference.randint(1, 1)
    reference.choice([LINE_FLANGE])
    reference.choice([ROW_PIPE])
    need(ctx.rng.getstate() == reference.getstate(), "rng state differs from two draws")
    passed("stock row of another item: no proposal, no extra draw")


def check_zero_draws_once() -> None:
    mcp = FakeMcp(lines=[LINE_FLANGE], rows=[ROW_FLANGE])
    ctx = context(mcp)
    truth = coordinator(CountRange(min=0, max=0)).step(ctx)
    need(truth == [] and mcp.calls == [], f"a day with n=0 called {mcp.calls}")
    reference = actor_rng(SEED, ASSISTANT, 0)
    reference.randint(0, 0)
    need(ctx.rng.getstate() == reference.getstate(), "n=0 drew other than once")
    passed("n=0: one draw and no call")


def check_same_seed_same_proposals() -> None:
    lines = [LINE_FLANGE, LINE_PIPE]
    rows = [ROW_FLANGE, ROW_PIPE, ROW_EMPTY]
    first, second = FakeMcp(lines, rows), FakeMcp(lines, rows)
    coordinator(3).step(context(first))
    coordinator(3).step(context(second))
    need(first.proposals() == second.proposals(), "same seed, other proposals")
    need(len(first.proposals()) > 0, "no proposal at all")
    need(all(p["lot"] != "LOT-3" for p in first.proposals()), "an empty lot was proposed")
    passed("same seed gives the same proposals twice; an empty lot is never proposed")


def check_refused_proposal_day_goes_on() -> None:
    mcp = FakeMcp(lines=[LINE_FLANGE], rows=[ROW_FLANGE], refuse=True)
    truth = coordinator(2).step(context(mcp))
    need(truth == [], f"a refused proposal was recorded: {truth}")
    need(len(mcp.proposals()) == 2, f"the day stopped after a refusal: {mcp.calls}")
    passed("a refused proposal is not recorded and the day goes on")


def check_not_a_materials_desk() -> None:
    try:
        coordinator(1).step(context(None, client=object()))
    except ProposeUnavailableError:
        passed("a client that is not a MaterialsDesk raises ProposeUnavailableError")
        return
    raise Failed("no ProposeUnavailableError for a client that is not a MaterialsDesk")


def main() -> None:
    check_no_short_lines()
    check_one_matching_proposal()
    check_quantity_is_the_available()
    check_other_item_no_proposal_same_draws()
    check_zero_draws_once()
    check_same_seed_same_proposals()
    check_refused_proposal_day_goes_on()
    check_not_a_materials_desk()
    print("T12 ok")


if __name__ == "__main__":
    main()
