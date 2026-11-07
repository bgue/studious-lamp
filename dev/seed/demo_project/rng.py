"""One random generator per section, so a section's output does not change when another changes."""

from __future__ import annotations

import random


def section_rng(seed: int | str, section: str) -> random.Random:
    """``random.Random(f"{seed}:{section}")``: one seed and section always draw the same."""
    return random.Random(f"{seed}:{section}")
