"""What the cost module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``cost`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_cost import MODULE
from tl_mod_cost.names import COST_CODE, COST_SNAPSHOT, RECORD_TYPES
from tl_mod_cost.projectors import CostCodeProjector, CostSnapshotProjector

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A cost code takes links (a person may relate it to other records). Its title, parent, unit and
#: figures change only through ``ImportCostSnapshot``; a snapshot takes nothing: it is never edited.
COST_CODE_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [CostCodeProjector(), CostSnapshotProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={COST_CODE: COST_CODE_GENERIC_COMMANDS, COST_SNAPSHOT: frozenset()},
    )
