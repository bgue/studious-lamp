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

from tl_sim.actors.base import BaseActor, Rec, Recorder
from tl_sim.clock import WEEKDAYS
from tl_sim.scenario import PlannerParams, draw
from tl_sim.types import SimContext


class Planner(BaseActor):
    name = "planner"
    params: PlannerParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        waiting = self._review(ctx, rec)
        created = self._plan(ctx, rec)
        if self._is_lookahead_day(ctx):
            rec.post(self._lookahead(created, waiting))

    def _review(self, ctx: SimContext, rec: Recorder) -> list[Rec]:
        """Step 1: approve the first ``k`` documents in review; return those still waiting."""
        in_review = rec.records("status:Review", title_prefix="Doc ")
        k = draw(self.params.approvals_per_day, ctx.rng)
        waiting: list[Rec] = []
        for index, doc in enumerate(in_review):
            approved = index < k and rec.transition(doc, "approve", "Approved")
            if not approved:
                waiting.append(doc)
        return waiting

    def _plan(self, ctx: SimContext, rec: Recorder) -> list[Rec]:
        """Step 2: create ``m`` installation activities on lines; return them in creation order."""
        m = draw(self.params.activities_per_day, ctx.rng)
        lines = rec.records("", title_prefix="Line ")
        if not lines:
            return []
        existing = len(rec.records("", title_prefix="Activity "))
        approved = rec.records("status:Approved", title_prefix="Doc ")
        created: list[Rec] = []
        for _ in range(m):
            line = ctx.rng.choice(lines)
            serial = existing + len(created) + 1
            designation = line.title.removeprefix("Line ")
            activity = rec.create(f"Activity {serial:03d} Install spools on {designation}")
            rec.link(activity, line, "belongs_to")
            if approved:
                rec.link(activity, ctx.rng.choice(approved), "requires")
            created.append(activity)
        return created

    def _is_lookahead_day(self, ctx: SimContext) -> bool:
        return (
            self.params.lookahead_day is not None
            and WEEKDAYS[ctx.now.weekday()] == self.params.lookahead_day
        )

    @staticmethod
    def _lookahead(created: list[Rec], waiting: list[Rec]) -> str:
        """The look-ahead text: the first three activities, then the first document on hold."""
        body = (
            f"Look-ahead: {len(created)} activities planned, "
            f"{len(waiting)} documents waiting for approval."
        )
        body += "".join(f" #{activity.key}" for activity in created[:3])
        if waiting:
            body += f" #hold #{waiting[0].key}"
        return body
