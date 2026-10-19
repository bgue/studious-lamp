"""The schedule updater: sends the weekly P6 export and links records to its activities.

A planner who works on the project's schedule (ADR-0015). The schedule (``params.schedule``) was
defined and its first snapshot published by a controller before the run, and a worker builds what
is sent, because a simulated person holds the `user` role only (ADR-0009 section 9): neither
defining, publishing nor building is this actor's act. Without the schedule the actor does nothing
and draws nothing. One working day (``act``), in this order, drawing from ``ctx.rng`` only where
stated:

1. Read the schedules, ``rec.schedules()``, and take the one whose code is ``params.schedule``.
2. If ``ctx.now`` falls on ``params.update_day``, send the next weekly file: ``n`` is the number of
   snapshots the schedule has (whatever their state); the file is the ``n``-th of
   ``tl_xer.synth.series(params.series_seed, n + 1)`` (the first of the series when there is no
   snapshot), called ``update-<n + 1:02d>.xer``, with ``rec.send_update``. After 52 snapshots no
   more are sent. No draw.
3. Draw ``k = draw(params.links_per_day, ctx.rng)`` (always, even when nothing follows). When the
   schedule has a published snapshot, take its activities (``rec.activities``, in P6 id order) and
   the records whose title starts ``Activity `` (the planner's, in key order); when both exist, do
   ``k`` times: draw ``record = ctx.rng.choice(records)`` and then ``activity =
   ctx.rng.choice(activities)`` and link them with ``rec.link_activity``. A record already linked
   to that activity is refused and the pair is passed over (both draws are spent).
"""

from __future__ import annotations

from tl_xer.synth import make_xer, series

from tl_sim.actors.base import BaseActor, Recorder, Sched
from tl_sim.clock import WEEKDAYS
from tl_sim.scenario import ScheduleUpdaterParams, draw
from tl_sim.types import SimContext

MAX_SNAPSHOTS = 52  # the longest series ``tl_xer.synth.series`` makes
WORK_RECORDS = "Activity "  # the title prefix of the planner's activity records


class ScheduleUpdater(BaseActor):
    name = "schedule_updater"
    params: ScheduleUpdaterParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        sched = next((s for s in rec.schedules() if s.code == self.params.schedule), None)
        if sched is None:
            return
        if (
            self.params.update_day is not None
            and WEEKDAYS[ctx.now.weekday()] == self.params.update_day
        ):
            self._send(rec, sched)
        self._link(ctx, rec, sched)

    def _send(self, rec: Recorder, sched: Sched) -> None:
        """Step 2: the next file of the series, unless the series is used up."""
        count = sched.snapshots
        if count >= MAX_SNAPSHOTS:
            return
        data = series(self.params.series_seed, count + 1)[count]
        rec.send_update(sched, f"update-{count + 1:02d}.xer", make_xer(data))

    def _link(self, ctx: SimContext, rec: Recorder, sched: Sched) -> None:
        """Step 3: ``k`` records linked to activities of the published snapshot."""
        k = draw(self.params.links_per_day, ctx.rng)
        if sched.current is None or k == 0:
            return
        activities = rec.activities(sched)
        records = rec.records("", title_prefix=WORK_RECORDS)
        if not activities or not records:
            return
        for _ in range(k):
            record = ctx.rng.choice(records)
            activity = ctx.rng.choice(activities)
            rec.link_activity(record, sched, activity)
