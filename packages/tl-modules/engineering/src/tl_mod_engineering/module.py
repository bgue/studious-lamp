"""What the engineering module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``engineering`` in this package's ``pyproject.toml``
names ``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_engineering import MODULE
from tl_mod_engineering.binding import bound_psets
from tl_mod_engineering.names import RECORD_TYPES, TAG
from tl_mod_engineering.patterns import ledger_numbering_patterns
from tl_mod_engineering.projectors import (
    CodeValueProjector,
    StandardProjector,
    TagClassProjector,
    TagProjector,
)

#: The generic commands a person may run on a tag (ADR-0010 addendum). The registry types (code
#: lists, values, mnemonics, patterns, tag classes) allow none: they change through the registry
#: commands, which are admin-only. ``EditRecord`` is the title and psets, so it needs the first two.
TAG_GENERIC_COMMANDS = frozenset(
    {"UpdateRecord", "SetPsetValues", "TransitionWorkflow", "AddLink", "SuggestLink", "AttachFile"}
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [StandardProjector(), CodeValueProjector(), TagClassProjector(), TagProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        bound_psets=bound_psets,
        numbering_patterns=ledger_numbering_patterns,
        generic_commands={TAG: TAG_GENERIC_COMMANDS},
    )
