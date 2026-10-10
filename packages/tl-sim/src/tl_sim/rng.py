"""Seeded randomness: one generator per (run seed, actor, day), never shared (brief 29.5).

``Random(int)`` is deterministic for a given Python version, and the seed is derived with SHA-256,
not ``hash()``, so it does not depend on ``PYTHONHASHSEED`` or on the process. An actor that draws
the same numbers in the same order on the same day gets the same day, whatever ran before it.
"""

from __future__ import annotations

import hashlib
from random import Random


def actor_rng(seed: int, actor: str, day: int) -> Random:
    """The generator for ``actor`` on simulated working day ``day`` (0 is the first day)."""
    material = f"tl-sim\x1f{seed}\x1f{actor}\x1f{day}".encode()
    return Random(int.from_bytes(hashlib.sha256(material).digest(), "big"))
