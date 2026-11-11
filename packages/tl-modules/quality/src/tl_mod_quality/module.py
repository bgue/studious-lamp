"""What the quality module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``quality`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process. ``PunchItem`` is ``draft_only``: a walkdown raises
items offline; the offline drafts are declared when S2 adds the raise command.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_quality import MODULE
from tl_mod_quality.names import RECORD_TYPES
from tl_mod_quality.projectors import PunchItemProjector

#: The module's commands: P2-PUNCH S2 fills this.
PUNCH_COMMANDS: tuple[()] = ()


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [PunchItemProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        command_words={},
        offline_drafts={},
    )
