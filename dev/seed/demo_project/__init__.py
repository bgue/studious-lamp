"""The demo project generator: one deterministic industrial project, P200 (docs/tickets/P2-SEED).

Run: ``uv run python -m dev.seed.demo_project --db <path|url> [--seed 2026] [--sections a,b]``
(``just demo-project [db]``). Importing the package registers every section in ``SECTIONS``.
"""

from __future__ import annotations

from dev.seed.demo_project import (  # noqa: F401  (each module registers its section)
    awp,
    constraints,
    core,
    correspondence,
    documents,
    engineering,
    materials,
    quality,
    release,
    requisitions,
    schedule,
)
from dev.seed.demo_project.registry import ORDER, SECTIONS

__all__ = ["ORDER", "SECTIONS"]
