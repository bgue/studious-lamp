"""What the correspondence module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``correspondence`` in this package's ``pyproject.toml``
names ``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ChildSource, ConfidentialSource, ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_correspondence import MODULE
from tl_mod_correspondence.names import (
    CLEARANCE_TABLE,
    CLOCK,
    CLOCK_TABLE,
    CORRESPONDENCE,
    CORRESPONDENCE_TABLE,
    RECORD_TYPES,
    THREAD,
    THREAD_TABLE,
)
from tl_mod_correspondence.projectors import (
    ClauseProjector,
    ClockProjector,
    CorrespondenceProjector,
    PartyProjector,
    ThreadProjector,
)

#: The class of an item is its `confidentiality` column; a `privileged` item is read by the accounts
#: named in the clearance table (ADR-0016). A thread hangs on its governing item and a clock on its
#: item, so they are readable only when that item is.
CONFIDENTIAL = (
    ConfidentialSource(
        record_types=frozenset({CORRESPONDENCE}),
        table=CORRESPONDENCE_TABLE,
        id_column="id",
        class_column="confidentiality",
        clearance_table=CLEARANCE_TABLE,
        children=(
            ChildSource(frozenset({THREAD}), THREAD_TABLE, "id", "governing_item_id"),
            ChildSource(frozenset({CLOCK}), CLOCK_TABLE, "id", "item_id"),
        ),
    ),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [
        CorrespondenceProjector(),
        ThreadProjector(),
        ClockProjector(),
        ClauseProjector(),
        PartyProjector(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE, record_types=RECORD_TYPES, projectors=projectors, confidential=CONFIDENTIAL
    )
