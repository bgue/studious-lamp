"""The RFI author: a site engineer who raises requests for information and accepts the answers.

A person on the contractor's side (P1-I6). Raising an RFI and sending it to internal review, and
accepting an answer, are any signed-in person's acts; issuing the RFI is a document controller's
(ADR-0019) and a simulated person holds the `user` role only (ADR-0009 section 9), so a controller
issues what the author sends, beside the run (``Scenario.operators``). An RFI nobody issues stays
in internal review. One working day (``act``), in this order, drawing from ``ctx.rng`` only where
stated:

1. Read the RFIs whose subject starts ``RFI: `` (the author's) and take those in the state
   Answered, in number order. For each, draw ``ctx.rng.random() < params.accept_rate`` and, when
   true, accept the answer with ``rec.accept_answer``.
2. Draw ``k = draw(params.rfis_per_day, ctx.rng)`` (always). Read the records whose title starts
   ``Line `` (the orchestrator's, in key order). Do ``k`` times: draw ``topic =
   ctx.rng.choice(TOPICS)``, ``discipline = ctx.rng.choice(DISCIPLINES)`` and, when there are
   lines, ``line = ctx.rng.choice(lines)``; raise the RFI ``RFI: <topic> at <line designation>``
   (or ``RFI: <topic>`` without lines) with ``rec.raise_rfi``. The date an answer is needed is
   ``params.answer_within_days`` after today (the real day when it is later than the simulated one:
   the suite refuses a date that has passed, and it counts time on its own clock); it is not part
   of the ground truth.
"""

from __future__ import annotations

from datetime import date, timedelta

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.scenario import RfiAuthorParams, draw
from tl_sim.types import SimContext

SUBJECT_PREFIX = "RFI: "
LINE_PREFIX = "Line "
TOPICS = ("clash with support", "valve access", "weld map", "insulation specification")
DISCIPLINES = ("Piping", "Mechanical", "Civil", "Instrumentation")


class RfiAuthor(BaseActor):
    name = "rfi_author"
    params: RfiAuthorParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        self._accept(ctx, rec)
        self._raise(ctx, rec)

    def _accept(self, ctx: SimContext, rec: Recorder) -> None:
        """Step 1: accept some of the answers that came in."""
        for rfi in rec.rfis(subject_prefix=SUBJECT_PREFIX):
            if rfi.state == "Answered" and ctx.rng.random() < self.params.accept_rate:
                rec.accept_answer(rfi)

    def _raise(self, ctx: SimContext, rec: Recorder) -> None:
        """Step 2: ``k`` new RFIs, sent to review."""
        k = draw(self.params.rfis_per_day, ctx.rng)
        if k == 0:
            return
        lines = rec.records("", title_prefix=LINE_PREFIX)
        needed = max(ctx.now.date(), date.today()) + timedelta(days=self.params.answer_within_days)
        for _ in range(k):
            topic = ctx.rng.choice(TOPICS)
            discipline = ctx.rng.choice(DISCIPLINES)
            where = ""
            if lines:
                where = " at " + ctx.rng.choice(lines).title.removeprefix(LINE_PREFIX)
            subject = f"{SUBJECT_PREFIX}{topic}{where}"
            rec.raise_rfi(
                subject,
                f"Please confirm the intent: {topic}{where}. See the isometric of the line.",
                discipline,
                needed.isoformat(),
            )
