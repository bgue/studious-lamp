"""The crew: installs valves on lines, records their data, reports progress, flags problems.

One working day (``act``), in this order, drawing from ``ctx.rng`` only where stated:

1. Read the lines (title starts ``Line ``). No lines: do nothing.
2. If ``params.announce`` is set, post ``#urgent <announce>``.
3. Draw ``n = draw(params.valves_per_day, ctx.rng)``. For each valve draw, in this order,
   ``ctx.rng.choice(lines)``, ``ctx.rng.choice(SIZES_IN)`` and ``ctx.rng.choice(MAKERS)``. Create
   ``Valve V<serial:03d> <size>in on <designation>`` (``serial`` is the number of existing records
   whose title starts ``Valve `` plus one for each created so far; ``size`` is the integer;
   ``designation`` is the line title without ``Line ``). Set the pset
   ``valve_data`` to ``{"size_in": size, "body_material": "CS", "manufacturer": maker}`` and link
   the valve ``belongs_to`` the line.
4. If valves were installed, post ``Installed <n> valves: #<key> #<key> ...`` (creation order).
5. Draw ``roll = ctx.rng.random()`` (always). When valves were installed and
   ``roll < params.reject_rate``, draw ``ctx.rng.choice(installed)`` and post
   ``Inspection failed on #<key>, needs rework #hold``.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.scenario import CrewParams
from tl_sim.types import SimContext

SIZES_IN = (2, 3, 4, 6, 8)
MAKERS = ("Crane", "Velan", "Emerson")


class Crew(BaseActor):
    name = "crew"
    params: CrewParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        raise NotImplementedError("STUB (P0-I6-T42)")
