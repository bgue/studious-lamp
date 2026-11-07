"""materials section: items, locations, receipts, lots, movements, take-off.

A stub here; piece T02 fills it.
"""

from __future__ import annotations

import random

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import World


def build(world: World, rng: random.Random) -> None:
    print("materials: not built yet")


register("materials", build, needs=("materials.ItemMaster",))
