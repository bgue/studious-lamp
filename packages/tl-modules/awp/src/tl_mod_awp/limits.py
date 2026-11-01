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

MAX_QUANTITIES: Final = 50  # rows of a CWP's quantities
MAX_CONTRACTOR: Final = 120  # characters of a CWP's contractor text
MAX_STATUS_TEXT: Final = 40  # an owner package's status text
MAX_SOURCE_SYSTEM: Final = 40
MAX_PACKAGE_NO: Final = 64  # an owner package number
MAX_LIST_CODE: Final = 64  # a code of a code list (discipline, commodity, unit)
MAX_QUANTITY_TEXT: Final = 20  # a quantity as text
MAX_BUDGET_TEXT: Final = 16  # "10000000.0"

DATE_PATTERN: Final = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
