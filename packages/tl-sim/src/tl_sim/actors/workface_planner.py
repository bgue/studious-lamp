"""The workface planner: an agent that proposes construction work packages, and creates none.

The suite does not let an agent create a CWP: the planner files ``propose_cwp`` proposals over MCP
and a person (the approver) accepts or rejects them. One working day (``act``), in this order,
drawing from ``ctx.rng`` only where stated:

1. Draw ``n = draw(params.cwps_per_day, ctx.rng)``. If ``n`` is 0, stop.
2. Read the areas of the current path of construction (``AwpDesk.areas``, in path order). The
   client must be one (``ProposeUnavailableError`` otherwise). With no areas, stop.
3. For each of the ``n`` CWPs, in order: draw a template ``ctx.rng.choice(TEMPLATES)`` (discipline,
   title, budget hours), then an area ``ctx.rng.choice(areas)``, and propose ``propose_cwp`` for
   the project of the scope, the discipline, the title followed by the area's code, the area as
   ``cwa_code`` and the budget hours.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.client import AwpDesk, ProposeUnavailableError
from tl_sim.orchestrator_names import ASSISTANT
from tl_sim.scenario import WorkfacePlannerParams, draw
from tl_sim.types import SimContext

# (discipline, title, budget hours) of the work a planner packages
TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("CIV", "Footings", "320"),
    ("MEC", "Pipe spools", "180"),
    ("ELE", "Cable pull", "240"),
    ("INS", "Loop checks", "96"),
)


class WorkfacePlanner(BaseActor):
    name = "workface_planner"
    params: WorkfacePlannerParams

    def __init__(self, params: WorkfacePlannerParams) -> None:
        super().__init__(params)
        self.identity = ASSISTANT  # an agent: it has an MCP caller, as the assistant does

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        count = draw(self.params.cwps_per_day, ctx.rng)
        if count == 0:
            return
        desk = ctx.client
        if not isinstance(desk, AwpDesk):
            raise ProposeUnavailableError("this client cannot read the path of construction")
        areas = desk.areas()
        if not areas:
            return
        project = ctx.scope.removeprefix("project:")
        for _ in range(count):
            discipline, title, budget_hours = ctx.rng.choice(TEMPLATES)
            area = ctx.rng.choice(areas)
            rec.propose(
                "propose_cwp",
                {
                    "project": project,
                    "discipline": discipline,
                    "title": f"{title} {area}",
                    "cwa_code": area,
                    "budget_hours": budget_hours,
                },
            )
