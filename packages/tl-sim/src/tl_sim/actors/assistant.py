"""The assistant: the one simulated agent. It proposes cross-references over MCP, nothing else.

The suite does not let an agent change a record directly (FANOUT D4): the assistant files proposals
through the MCP tool ``link_records`` and a person (the approver) accepts or rejects them. One
working day (``act``), in this order, drawing from ``ctx.rng`` only where stated:

1. Draw ``n = draw(params.proposals_per_day, ctx.rng)``. If ``n`` is 0, stop.
2. Read the valves (title starts ``Valve ``) and the documents (title starts ``Doc ``) in key
   order. Without both, stop.
3. Draw ``k = min(n, len(valves) * len(documents))`` distinct pairs with
   ``ctx.rng.sample(range(len(valves) * len(documents)), k)`` (pair ``i`` is valve
   ``i // len(documents)`` and document ``i % len(documents)``, so a day never proposes the same
   pair twice). For each pair, in the order drawn, propose ``link_records`` with ``scope``,
   ``from_record`` the valve key, ``to_record`` the document key, ``relation`` ``references`` and
   ``note`` ``Valve data sheet reference``. When the server refuses because the link already
   exists, nothing is recorded and the day goes on; any other refusal is raised.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.orchestrator_names import ASSISTANT
from tl_sim.scenario import AssistantParams, draw
from tl_sim.types import SimContext


class Assistant(BaseActor):
    name = "assistant"
    params: AssistantParams

    def __init__(self, params: AssistantParams) -> None:
        super().__init__(params)
        self.identity = ASSISTANT

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        count = draw(self.params.proposals_per_day, ctx.rng)
        if count == 0:
            return
        valves = rec.records(title_prefix="Valve ")
        documents = rec.records(title_prefix="Doc ")
        if not valves or not documents:
            return
        pairs = ctx.rng.sample(
            range(len(valves) * len(documents)), min(count, len(valves) * len(documents))
        )
        for index in pairs:
            valve, document = valves[index // len(documents)], documents[index % len(documents)]
            rec.propose(
                "link_records",
                {
                    "scope": ctx.scope,
                    "from_record": valve.key,
                    "to_record": document.key,
                    "relation": "references",
                    "note": "Valve data sheet reference",
                },
            )
