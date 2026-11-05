"""The materials coordinator: an agent that proposes stock reservations, and reserves none.

The suite does not let an agent move stock: the coordinator reads the project's short take-off
lines and its stock over MCP and files ``propose_reservation`` proposals; a person (the approver)
accepts or rejects them. One working day (``act``), in this order, drawing from ``ctx.rng`` only
where stated:

1. Draw ``n = draw(params.reservations_per_day, ctx.rng)``. If ``n`` is 0, stop.
2. The client must be a ``MaterialsDesk`` (``ProposeUnavailableError`` otherwise). Read the short
   take-off lines (``short_lines``, sorted by key); with none, stop. Read the stock (``stock``) and
   keep the rows with a positive ``available``, sorted by lot and location; with none, stop.
3. For each of the ``n`` proposals, in order: draw a short line ``ctx.rng.choice(lines)``, then a
   stock row ``ctx.rng.choice(rows)``. When the row's item is not the line's item, skip this
   proposal without drawing again. Otherwise propose ``propose_reservation`` for the row's lot and
   location, the line's key, and the smaller of the row's ``available`` and the line's ``short`` as
   a plain decimal string. A proposal the server refuses is not recorded and the day goes on.
"""

from __future__ import annotations

from decimal import Decimal

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.client import MaterialsDesk, ProposeUnavailableError
from tl_sim.mcp_caller import ProposalRefusedError
from tl_sim.orchestrator_names import ASSISTANT
from tl_sim.scenario import MaterialsCoordinatorParams, draw
from tl_sim.types import SimContext


class MaterialsCoordinator(BaseActor):
    name = "materials_coordinator"
    params: MaterialsCoordinatorParams

    def __init__(self, params: MaterialsCoordinatorParams) -> None:
        super().__init__(params)
        self.identity = ASSISTANT  # an agent: it has an MCP caller, as the assistant does

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        count = draw(self.params.reservations_per_day, ctx.rng)
        if count == 0:
            return
        desk = ctx.client
        if not isinstance(desk, MaterialsDesk):
            raise ProposeUnavailableError("this client cannot read the take-off lines and stock")
        lines = sorted(desk.short_lines(), key=lambda line: str(line["key"]))
        if not lines:
            return
        rows = sorted(
            (row for row in desk.stock() if Decimal(str(row["available"])) > 0),
            key=lambda row: (str(row["lot"]), str(row["location"])),
        )
        if not rows:
            return
        project = ctx.scope.removeprefix("project:")
        for _ in range(count):
            line = ctx.rng.choice(lines)
            row = ctx.rng.choice(rows)
            if row["item_code"] != line["item_code"]:
                continue
            qty = min(Decimal(str(row["available"])), Decimal(str(line["short"])))
            try:
                rec.propose(
                    "propose_reservation",
                    {
                        "project": project,
                        "lot": str(row["lot"]),
                        "location": str(row["location"]),
                        "mto_line": str(line["key"]),
                        "qty": format(qty, "f"),
                    },
                )
            except ProposalRefusedError:
                continue
