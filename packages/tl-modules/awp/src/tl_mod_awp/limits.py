"""The size limits of the awp module's commands (the P1-I1 review rule).

A command arrives from a person over HTTP or the CLI, so every list has a bound and every text a
length before a handler reads it.
"""

from __future__ import annotations

from typing import Final

MAX_WBS_DEPTH: Final = 8  # levels; ``depth`` runs 0..7
MAX_WBS_NODES: Final = 5_000  # nodes in one project
MAX_ALLOCATIONS: Final = 20  # rows of one allocation list
MAX_PATH_STEPS: Final = 500
MAX_CODE: Final = 32  # a WBS or CWA code
MAX_TITLE: Final = 200
MAX_LOCATION: Final = 200
MAX_REASON: Final = 500
MAX_NOTE: Final = 500
MAX_REASON_CODE: Final = 64
MAX_COST_CODE: Final = 64  # cost.CostCode keys (``tl_mod_cost.limits.MAX_CODE``)
MAX_ID: Final = 40  # a record id (ULID) is 26 characters

CODE_PATTERN: Final = r"^[A-Z0-9][A-Z0-9.\-]{0,31}$"
REASON_CODE_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
