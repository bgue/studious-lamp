"""What the legacy loaders module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``legacy`` in this package's ``pyproject.toml`` names
``spec``. A load run is the job record of a load: its state moves only through the stages of
:class:`tl_mod_legacy.service.LoadService`, its files are written by the module, and it takes no
generic command (no link, no attachment, no update) and has no API command.
"""

from __future__ import annotations

from tl_core.modules import ConfidentialSource, ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_legacy import MODULE
from tl_mod_legacy.names import LOAD_RUN, RECORD_TYPES, RUN_TABLE
from tl_mod_legacy.projectors import LoadRunProjector

#: The class of a run is its `confidentiality` column (ADR-0016); NULL is `internal`. A run holds
#: the file of an incumbent system and the ids of what it created, so it is as readable as that
#: class says: its record, its files, its events and the ids in them follow it.
CONFIDENTIAL = (
    ConfidentialSource(
        record_types=RECORD_TYPES,
        table=RUN_TABLE,
        id_column="id",
        class_column="confidentiality",
        null_class="internal",
    ),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [LoadRunProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={LOAD_RUN: frozenset()},
        confidential=CONFIDENTIAL,
    )
