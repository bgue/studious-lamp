"""The approver: a person who works the review queue.

The assistant (an agent) can only propose; the approver decides. One working day (``act``):

1. Read the pending proposals of the project, oldest first (``rec.pending()``).
2. For each one draw ``ctx.rng.random()``. Below ``params.accept_rate`` it is accepted
   (``rec.decide(..., accept=True)``), otherwise rejected with the reason ``Not needed``.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.scenario import ApproverParams
from tl_sim.types import SimContext

REJECTION = "Not needed"


class Approver(BaseActor):
    name = "approver"
    params: ApproverParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        for proposal in rec.pending():
            accept = ctx.rng.random() < self.params.accept_rate
            rec.decide(proposal, accept=accept, reason="" if accept else REJECTION)
