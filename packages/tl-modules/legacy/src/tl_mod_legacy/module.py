"""What the legacy loaders module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``legacy`` in this package's ``pyproject.toml`` names
``spec``. A load run is the job record of a load: its state moves only through the stages of
:class:`tl_mod_legacy.service.LoadService`, its files are written by the module, and it takes no
generic command (no link, no attachment, no update) and has no API command.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_legacy import MODULE
from tl_mod_legacy.names import LOAD_RUN, RECORD_TYPES
from tl_mod_legacy.projectors import LoadRunProjector


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [LoadRunProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={LOAD_RUN: frozenset()},
    )
