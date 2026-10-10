"""The planner: approves documents in review, plans activities, writes the weekly look-ahead.

One working day (``act``), in this order, drawing from ``ctx.rng`` only where stated:

1. Read the documents in review: records with ``status:Review`` whose title starts ``Doc ``, in key
   order. Draw ``k = draw(params.approvals_per_day, ctx.rng)``. For the first ``k`` of them run
   ``approve`` (``Approved`` expected). The suite may refuse (the guard needs a ``references``
   link), which ``Recorder.transition`` reports as ``False``; a refused document stays waiting.
2. Draw ``m = draw(params.activities_per_day, ctx.rng)``. Read the lines (title starts ``Line ``);
   with no lines, plan nothing. For each of the ``m`` activities draw ``ctx.rng.choice(lines)``,
   create ``Activity <serial:03d> Install spools on <designation>`` (``serial`` is the number of
   existing activities plus one for each created so far; ``designation`` is the line title
   without ``Line ``), and link it ``belongs_to`` the line. Then read the approved documents
   (``status:Approved``, title starts ``Doc ``); if there are any, draw ``ctx.rng.choice`` of them
   (key order) and link the activity ``requires`` that document.
3. If ``params.lookahead_day`` is set and ``ctx.now`` falls on that weekday, post
   ``Look-ahead: <a> activities planned, <w> documents waiting for approval.`` where ``a`` is the
   number of activities this step created and ``w`` the number still in review after step 1. For
   each of the first three activities created add `` #<key>``; when ``w`` is above 0 append
   `` #hold`` and `` #<key>`` of the first document still waiting.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.scenario import PlannerParams
from tl_sim.types import SimContext


class Planner(BaseActor):
    name = "planner"
    params: PlannerParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        raise NotImplementedError("STUB (P0-I6-T41)")
