"""awp section: CWPs, WBS, CWAs, path of construction (a stub here; piece T01 fills it)."""

from __future__ import annotations

import random

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import World


def build(world: World, rng: random.Random) -> None:
    print("awp: not built yet")


register("awp", build, needs=("awp.CWP",))
