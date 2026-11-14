"""scope helper of P200 (P2-SEED-T11): scope items for an IWP while it is Draft.

Scope is not a section of its own. The constraints section creates the IWPs (``CreateIwp``) and
calls ``add_scope`` right after each one, while the IWP is still Draft: a frozen IWP (Issued and
later) takes no scope, and the IWPs do not exist before constraints. ``add_scope`` creates 3-6
scope items with ``CreateScopeItem`` (by the project engineer, who edits IWPs), each with a
commodity of the company's list, a quantity, a unit of the UnitOfMeasure list
(``data/standards.yaml``), the estimated hours and the work package of its IWP; then the items are
added to the IWP in one ``AddIwpScope`` command.

Commodities are the demo list (``data/awp/standards.yaml``). Only ``piping`` has its own rules of
credit with a ``manual`` step; the other commodities of the list use the piping steps (rule 2 of
the engine: a commodity without an entry uses ``piping``), so each item has a hand-entered step.

Scope does not change the status of an IWP. The caller passes a stream of its own (so the
constraint draws do not shift) and makes the call inside its ``world.on(day)`` block. No raw SQL
writes.
"""

from __future__ import annotations

import random

from tl_mod_awp.commands import AddIwpScope, CreateScopeItem
from tl_mod_awp.handlers.scope import handle_add_iwp_scope, handle_create_scope_item

from dev.seed.demo_project.world import World

#: the editor of the IWPs (awp.iwp.edit): the project engineer, an awp superuser in the roster
EDITOR = "lhartmann"
#: commodities of the demo list (``data/awp/standards.yaml``, ``Commodity``), each with a unit of
#: the UnitOfMeasure list (``data/standards.yaml``)
UNIT_OF = {
    "piping": "m",
    "structural-steel": "kg",
    "insulation": "m3",
    "electrical": "m",
    "mechanical-equipment": "kg",
}
COMMODITIES = tuple(UNIT_OF)
ITEMS_MIN = 3
ITEMS_MAX = 6


def add_scope(world: World, iwp: str, label: str, cwp: str | None, rng: random.Random) -> int:
    """Create 3-6 scope items for the Draft IWP ``iwp`` and add them; returns how many.

    ``label`` names the IWP in the item descriptions (for example ``"03"``); ``cwp`` is the
    work package of the IWP, copied onto each item.
    """
    count = rng.randint(ITEMS_MIN, ITEMS_MAX)
    items: list[str] = []
    for n in range(1, count + 1):
        commodity = rng.choice(COMMODITIES)
        hours = rng.randrange(20, 400) / 10  # one decimal, 2.0 to 39.9
        made = world.run(
            handle_create_scope_item,
            CreateScopeItem,
            by=EDITOR,
            commodity=commodity,
            description=f"{commodity.replace('-', ' ')} line {n:02d} of IWP {label}",
            qty=str(rng.randrange(10, 400)),
            uom=UNIT_OF[commodity],
            est_hours=f"{hours:.1f}",
            cwp_id=cwp,
        )
        items.append(str(made.stream_id))
    world.run(handle_add_iwp_scope, AddIwpScope, by=EDITOR, iwp=iwp, items=items)
    return count
