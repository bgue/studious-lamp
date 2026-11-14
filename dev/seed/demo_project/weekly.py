"""weekly section of P200: a stub (empty build) so the section registers; the ticket fills it."""

from __future__ import annotations

import random

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import World


def build(world: World, rng: random.Random) -> None:
    """Filled by the ticket of this section (docs/tickets/P2-SEED)."""


register("weekly", build, needs=("awp.IWP",))
