"""What the correspondence module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``correspondence`` in this package's ``pyproject.toml``
names ``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_correspondence import MODULE
from tl_mod_correspondence.names import RECORD_TYPES
from tl_mod_correspondence.projectors import (
    ClauseProjector,
    ClockProjector,
    CorrespondenceProjector,
    PartyProjector,
    ThreadProjector,
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
    return ModuleSpec(name=MODULE, record_types=RECORD_TYPES, projectors=projectors)
