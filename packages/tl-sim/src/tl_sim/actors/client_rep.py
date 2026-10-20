"""The client's representative: answers the RFIs that were issued and wait for an answer.

A person on the client's side (P1-I6). Answering is any signed-in person's act. Some answers say
that cost is affected, which is what leads a controller to a Commercial item. One working day
(``act``), drawing from ``ctx.rng`` only where stated:

1. Draw ``k = draw(params.answers_per_day, ctx.rng)`` (always).
2. Read the RFIs whose subject starts ``RFI: `` and take those in the state Awaiting response, in
   number order; for the first ``k`` of them draw ``ctx.rng.random() < params.impact_rate`` (cost
   impact ``yes`` when true, else ``no``; the schedule is always ``no``) and answer with
   ``rec.answer_rfi``.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.actors.rfi_author import SUBJECT_PREFIX
from tl_sim.scenario import ClientRepParams, draw
from tl_sim.types import SimContext


class ClientRep(BaseActor):
    name = "client_rep"
    params: ClientRepParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        k = draw(self.params.answers_per_day, ctx.rng)
        waiting = [
            x for x in rec.rfis(subject_prefix=SUBJECT_PREFIX) if x.state == "Awaiting response"
        ]
        for rfi in waiting[:k]:
            costly = ctx.rng.random() < self.params.impact_rate
            rec.answer_rfi(
                rfi,
                f"Answered on {ctx.now:%d %B}: follow the revised isometric.",
                "yes" if costly else "no",
                "no",
            )
