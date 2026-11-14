"""scope section of P200 (P2-SEED-T11): scope items for the IWPs that are Ready, before release.

Every IWP in the Ready state gets 3-6 scope items: each item is created (``CreateScopeItem``, by the
project engineer, who edits IWPs) with a commodity of the company's list, a quantity, a unit, the
estimated hours and the work package of its IWP; then they are added to the IWP in one
``AddIwpScope`` command. Scope is added before release, because a frozen IWP (Issued and later)
takes no scope.

Commodities are the demo list (``data/awp/standards.yaml``). Only ``piping`` has its own rules of
credit with a ``manual`` step; the other commodities of the list use the piping steps (rule 2 of
the engine: a commodity without an entry uses ``piping``), so each item has a hand-entered step.

Scope does not change readiness and does not change the status of an IWP, so the release section
still draws its twelve packages from the same Ready IWPs. The section draws only from its own
``rng``; every date is ``world.on(day)`` before TODAY. No raw SQL writes.
"""

from __future__ import annotations

import random
from datetime import timedelta

from tl_mod_awp.commands import AddIwpScope, CreateScopeItem
from tl_mod_awp.handlers.scope import handle_add_iwp_scope, handle_create_scope_item

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import TODAY, World

#: the editor of the IWPs (awp.iwp.edit): the project engineer, an awp superuser in the roster
EDITOR = "lhartmann"
#: commodities of the demo list (``data/awp/standards.yaml``, ``Commodity``)
COMMODITIES = ("piping", "structural-steel", "insulation", "electrical", "mechanical-equipment")
UNIT = "m"  # a unit of the company list
ITEMS_MIN = 3
ITEMS_MAX = 6
SCOPE_DAY_OFFSET = 6  # the scope is entered six days before TODAY, before the sign-offs

Iwp = tuple[str, str, str | None]  # (IWP record id, IWP key, the IWP's work package id)


def _ready_iwps(world: World) -> list[Iwp]:
    return [
        (str(r["id"]), str(r["key"]), None if r["cwp"] is None else str(r["cwp"]))
        for r in world.rows(
            "SELECT r.id AS id, r.key AS key, i.cwp_id AS cwp FROM cur_core_record r "
            "JOIN cur_awp_iwp i ON i.id = r.id "
            "WHERE r.type = 'awp.IWP' AND r.status = 'Ready' ORDER BY r.key"
        )
    ]


def build(world: World, rng: random.Random) -> None:
    day = TODAY - timedelta(days=SCOPE_DAY_OFFSET)
    for iwp, key, cwp in _ready_iwps(world):
        count = rng.randint(ITEMS_MIN, ITEMS_MAX)
        items: list[str] = []
        with world.on(day):
            for n in range(1, count + 1):
                commodity = rng.choice(COMMODITIES)
                hours = rng.randrange(20, 400) / 10  # one decimal, 2.0 to 39.9
                made = world.run(
                    handle_create_scope_item,
                    CreateScopeItem,
                    by=EDITOR,
                    commodity=commodity,
                    description=f"{commodity.replace('-', ' ')} line {n:02d} of {key}",
                    qty=str(rng.randrange(10, 400)),
                    uom=UNIT,
                    est_hours=f"{hours:.1f}",
                    cwp_id=cwp,
                )
                items.append(str(made.stream_id))
            world.run(
                handle_add_iwp_scope,
                AddIwpScope,
                by=EDITOR,
                iwp=iwp,
                items=items,
            )


register("scope", build, needs=("awp.IWP",))
