"""requisitions section: stub, P2-SEED."""

from __future__ import annotations

import random

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import World


def build(world: World, rng: random.Random) -> None:
    """Nothing yet."""


register("requisitions", build, needs=("requisitions.LaborRequisition",))
