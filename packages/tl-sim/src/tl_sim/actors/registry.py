"""Builds an actor from its name and parameters. The three actors of simulator v0."""

from __future__ import annotations

from typing import Any

from tl_sim.actors.approver import Approver
from tl_sim.actors.assistant import Assistant
from tl_sim.actors.base import BaseActor
from tl_sim.actors.client_rep import ClientRep
from tl_sim.actors.crew import Crew
from tl_sim.actors.document_controller import DocumentController
from tl_sim.actors.document_registrar import DocumentRegistrar
from tl_sim.actors.planner import Planner
from tl_sim.actors.rfi_author import RfiAuthor
from tl_sim.actors.schedule_updater import ScheduleUpdater
from tl_sim.actors.tag_clerk import TagClerk
from tl_sim.scenario import Scenario

ACTOR_CLASSES: dict[str, type[BaseActor]] = {
    "document_controller": DocumentController,
    "planner": Planner,
    "crew": Crew,
    "tag_clerk": TagClerk,
    "document_registrar": DocumentRegistrar,
    "schedule_updater": ScheduleUpdater,
    "rfi_author": RfiAuthor,
    "client_rep": ClientRep,
    "assistant": Assistant,
    "approver": Approver,
}


def build_actor(name: str, params: Any) -> BaseActor:
    return ACTOR_CLASSES[name](params)


def actors_of(scenario: Scenario) -> list[BaseActor]:
    """The scenario's enabled actors in the order they act each day."""
    return [build_actor(name, getattr(scenario.actors, name)) for name in scenario.actors.enabled()]
