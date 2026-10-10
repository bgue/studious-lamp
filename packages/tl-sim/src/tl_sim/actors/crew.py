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
4. If valves were installed, post ``Installed <n> valves: #<key> #<key> ...`` in creation order
   (``Installed 1 valve: #<key>`` for one).
5. Draw ``roll = ctx.rng.random()`` (always). When valves were installed and
   ``roll < params.reject_rate``, draw ``ctx.rng.choice(installed)`` and post
   ``Inspection failed on #<key>, needs rework #hold``.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Rec, Recorder, plural
from tl_sim.scenario import CrewParams, draw
from tl_sim.types import SimContext

SIZES_IN = (2, 3, 4, 6, 8)
MAKERS = ("Crane", "Velan", "Emerson")


class Crew(BaseActor):
    name = "crew"
    params: CrewParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        lines = rec.records(title_prefix="Line ")
        if not lines:
            return
        if self.params.announce is not None:
            rec.post(f"#urgent {self.params.announce}")
        count = draw(self.params.valves_per_day, ctx.rng)
        serial_base = len(rec.records(title_prefix="Valve "))
        installed = self._install(ctx, rec, lines, count, serial_base)
        if installed:
            refs = " ".join(f"#{valve.key}" for valve in installed)
            rec.post(f"Installed {plural(len(installed), 'valve')}: {refs}")
        roll = ctx.rng.random()
        if installed and roll < self.params.reject_rate:
            flagged = ctx.rng.choice(installed)
            rec.post(f"Inspection failed on #{flagged.key}, needs rework #hold")

    def _install(
        self,
        ctx: SimContext,
        rec: Recorder,
        lines: list[Rec],
        count: int,
        serial_base: int,
    ) -> list[Rec]:
        """Create, data and link one valve per draw, in creation order."""
        installed: list[Rec] = []
        for _ in range(count):
            line = ctx.rng.choice(lines)
            size = ctx.rng.choice(SIZES_IN)
            maker = ctx.rng.choice(MAKERS)
            serial = serial_base + len(installed) + 1
            designation = line.title.removeprefix("Line ")
            valve = rec.create(f"Valve V{serial:03d} {size}in on {designation}")
            rec.set_psets(
                valve,
                {"valve_data": {"size_in": size, "body_material": "CS", "manufacturer": maker}},
            )
            rec.link(valve, line, "belongs_to")
            installed.append(valve)
        return installed
