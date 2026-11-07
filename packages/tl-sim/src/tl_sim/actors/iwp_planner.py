"""The IWP planner: builds interim work packages from scope items and works their constraints.

A person (``user:sim-iwp_planner``), not the agent ``workface_planner``. One working day (``act``),
in this order, drawing from ``ctx.rng`` only where stated:

1. Read the IWPs once: ``existing`` is how many the project holds before today.
2. Draw ``n = draw(params.iwps_per_day, ctx.rng)``. For each new IWP, in turn, draw
   ``discipline, title = ctx.rng.choice(TEMPLATES)`` and create the IWP titled
   ``<title> <existing + i + 1>``. Then, for each of ``params.scope_items``, draw
   ``commodity, description, qty, uom, hours = ctx.rng.choice(ITEMS)`` and create the scope item.
   Add the items to the IWP in creation order, then start its development.
3. Read the open constraints (open or assigned), before anything below is raised, so a constraint
   raised today is not cleared the day it is raised.
4. Draw ``roll = ctx.rng.random()`` (always). When ``roll < params.constraint_rate`` and the
   project holds an IWP, the newest one is the last by number: draw
   ``category = ctx.rng.choice(CATEGORIES)`` and raise a manual constraint on it, titled
   ``<category> needed for <number>``.
5. Clear the first ``min(params.clears_per_day, len(open))`` of the constraints read in step 3, in
   key order, each with the reason ``cleared by planner``. No draws.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Rec, Recorder
from tl_sim.scenario import IwpPlannerParams, draw
from tl_sim.types import SimContext

#: (discipline, the title every IWP of that kind starts with)
TEMPLATES = (
    ("PIP", "Spool set"),
    ("PIP", "Valve install"),
    ("CIV", "Footings"),
    ("ELE", "Cable pull"),
)
#: (commodity, description, quantity, unit of measure, estimated hours)
ITEMS = (
    ("PIPE-SPOOL", "Pipe spool", "1", "EA", "12"),
    ("VALVE", "Valve", "1", "EA", "6"),
    ("SUPPORT", "Pipe support", "4", "EA", "3"),
)
CATEGORIES = ("materials", "engineering", "permit", "labour")
CLEARED_BY = "cleared by planner"


class IwpPlanner(BaseActor):
    name = "iwp_planner"
    params: IwpPlannerParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        existing = len(rec.iwps())
        for i in range(draw(self.params.iwps_per_day, ctx.rng)):
            self._build(ctx, rec, existing + i)
        open_before = rec.open_constraints()
        roll = ctx.rng.random()
        iwps = rec.iwps()
        if roll < self.params.constraint_rate and iwps:
            newest = iwps[-1]
            category = ctx.rng.choice(CATEGORIES)
            rec.raise_constraint(
                str(newest["id"]), category, f"{category} needed for {newest['number']}"
            )
        for constraint in open_before[: self.params.clears_per_day]:
            rec.clear_constraint(str(constraint["id"]), CLEARED_BY)

    def _build(self, ctx: SimContext, rec: Recorder, earlier: int) -> None:
        """Create one IWP with its scope items, add the items and start its development."""
        discipline, title = ctx.rng.choice(TEMPLATES)
        iwp = rec.create_iwp(discipline, f"{title} {earlier + 1}")
        items: list[Rec] = []
        for _ in range(self.params.scope_items):
            commodity, description, qty, uom, hours = ctx.rng.choice(ITEMS)
            items.append(rec.create_scope_item(commodity, description, qty, uom, hours))
        rec.add_scope(iwp, items)
        rec.start_development(iwp)
