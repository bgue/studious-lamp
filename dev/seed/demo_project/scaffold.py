"""scaffold section: scaffolds of P200, built through the real scaffold commands (P2-I4B-T11a).

One scaffold per approved scaffold requisition of the requisitions section, in key order: the
1st stays Designed, the 2nd is Erecting, the 3rd is In Use (tagged green, released), the 4th is
Modify (green, released, then a failed inspection). With fewer approved requests, the first states
only; with none, the section says so in one line. ``lhartmann`` registers, designs, erects,
releases and inspects (``user`` words); the administrator ``mokafor`` tags green (controller
word). No ``requires`` links: the readiness of the IWPs does not move. Draws: none; every event
falls on its day through ``world.on(day)``, from the requisitions' ``BASE`` and never after TODAY.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from tl_adapters.db import open_uow
from tl_core.confidentiality import use_viewer, viewer_for_actor
from tl_mod_scaffold.commands import (
    DesignScaffold,
    ErectScaffold,
    InspectScaffold,
    RegisterScaffold,
    ReleaseScaffold,
    TagScaffoldGreen,
)
from tl_mod_scaffold.handlers.scaffold import (
    handle_design_scaffold,
    handle_erect_scaffold,
    handle_inspect_scaffold,
    handle_register_scaffold,
    handle_release_scaffold,
    handle_tag_scaffold_green,
)

from dev.seed.demo_project.core import ADMIN
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.requisitions import BASE
from dev.seed.demo_project.world import PROJECT, TODAY, World, actor_of

FIELD = "lhartmann"  # registers, designs, erects, releases, inspects
CONTROLLER = ADMIN  # the green tag is a controller word; the administrator holds every word
#: Commands after the register, by position of the request: the final state is the last one.
STEPS: tuple[tuple[str, ...], ...] = (
    (),  # stays Designed
    ("erect",),
    ("erect", "green", "release"),
    ("erect", "green", "release", "fail"),
)
NO_REQUESTS_NOTE = "scaffold: no approved scaffold requisitions"
_REQUESTS_SQL = (
    "SELECT r.id AS id, r.title AS title FROM cur_core_record r "
    "WHERE r.scope = :s AND r.type = 'requisitions.ScaffoldRequest' "
    "AND r.status IN ('Approved', 'Scheduled', 'In progress', 'Done', 'Closed') ORDER BY r.key"
)


def _run(world: World, who: str, day: date, handler: Any, model: Any, **fields: Any) -> Any:
    """One command as ``who`` on ``day``, read through ``who``'s own viewer (ADR-0016)."""
    with open_uow(world.target, readonly=True) as uow:
        viewer = viewer_for_actor(uow.conn(), actor_of(who))
    with world.on(day), use_viewer(viewer):
        return world.run(handler, model, by=who, **fields)


def build(world: World, rng: random.Random) -> None:
    requests = world.rows(_REQUESTS_SQL, s=PROJECT)
    if not requests:
        print(NO_REQUESTS_NOTE)
        return
    for index, request in enumerate(requests[: len(STEPS)]):
        day = min(BASE + timedelta(days=14 + 3 * index), TODAY - timedelta(days=8))

        def step(who: str, handler: Any, model: Any, **fields: Any) -> None:
            nonlocal day
            _run(world, who, min(day, TODAY), handler, model, **fields)
            day += timedelta(days=1)

        made = _run(
            world,
            FIELD,
            day,
            handle_register_scaffold,
            RegisterScaffold,
            request_id=str(request["id"]),
            title=str(request["title"]),
            location_text=None,
        )
        day += timedelta(days=1)
        sid = str(made.stream_id)
        step(FIELD, handle_design_scaffold, DesignScaffold, scaffold=sid)
        for word in STEPS[index]:
            if word == "erect":
                step(FIELD, handle_erect_scaffold, ErectScaffold, scaffold=sid)
            elif word == "green":
                step(CONTROLLER, handle_tag_scaffold_green, TagScaffoldGreen, scaffold=sid)
            elif word == "release":
                step(FIELD, handle_release_scaffold, ReleaseScaffold, scaffold=sid)
            elif word == "fail":
                step(
                    FIELD,
                    handle_inspect_scaffold,
                    InspectScaffold,
                    scaffold=sid,
                    result="fail",
                )


register("scaffold", build, needs=("scaffold.Scaffold", "requisitions.ScaffoldRequest"))
