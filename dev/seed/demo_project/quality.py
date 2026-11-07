"""quality section: punch items (a stub here; the punch slice fills it).

It is skipped, not built, until the record type exists: ``quality: skipped, quality.PunchItem not
installed``.
"""

from __future__ import annotations

import random

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import World


def build(world: World, rng: random.Random) -> None:
    print("quality: not built yet")


register("quality", build, needs=("quality.PunchItem",))
