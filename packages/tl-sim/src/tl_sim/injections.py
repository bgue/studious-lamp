"""Injected events: one-off steps played by an actor, after the day's regular actors.

| Event | Actor and effect |
|---|---|
| ``material_late{item, days}`` | the crew posts an urgent notice: the item is late by ``days`` |
| ``design_revision{count}`` | the document controller revises ``count`` documents (default 1) |
| ``post{actor, body}`` | the named actor posts ``body`` |

An injection reuses the actor classes with parameters overridden for one step (the one-off fields
``CrewParams.announce`` and ``DocumentControllerParams.forced_revisions``), so what it does is
recorded as ground truth like any other step. Injected steps use later time slots than the three
regular actors and their own random stream (``<actor>+inject``).
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.actors.registry import build_actor
from tl_sim.scenario import CrewParams, DocumentControllerParams, InjectSpec, Scenario
from tl_sim.types import Actor, SimContext

NO_WORK = {"valves_per_day": 0, "reject_rate": 0.0}


class Poster(BaseActor):
    """Posts one text as the actor it stands in for."""

    def __init__(self, name: str, body: str) -> None:
        self.name = name
        super().__init__(None)
        self.body = body

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        rec.post(self.body)


def injected_actor(spec: InjectSpec, scenario: Scenario) -> Actor:
    """The actor that plays ``spec``, configured for a single, otherwise idle step."""
    if spec.event == "material_late":
        days = int(spec.args.get("days", 0))
        text = f"{spec.args['item']} is late by {days} days"
        crew = scenario.actors.crew or CrewParams()
        return build_actor("crew", crew.model_copy(update={**NO_WORK, "announce": text}))
    if spec.event == "design_revision":
        count = int(spec.args.get("count", 1))
        controller = scenario.actors.document_controller or DocumentControllerParams()
        idle = {"documents_per_day": 0, "revision_rate": 0.0, "forced_revisions": count}
        return build_actor("document_controller", controller.model_copy(update=idle))
    return Poster(str(spec.args["actor"]), str(spec.args["body"]))
