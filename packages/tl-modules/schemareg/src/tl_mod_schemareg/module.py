"""What the schema registry module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``schemareg`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process. ``schema_source`` is the module's contribution to
the effective schema: the process attaches it to the schema provider where it opens its ledger.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_schemareg import MODULE
from tl_mod_schemareg.names import ADOPTION, RECORD_TYPES, SCHEMA_PACKAGE, WAIVER
from tl_mod_schemareg.projectors import AdoptionProjector, SchemaPackageProjector, WaiverProjector
from tl_mod_schemareg.source import schema_source

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A package takes links (a ticket, an RFI or a document may point at it). Its content, state and
#: reports change only through the module's commands; adoptions and waivers take nothing.
PACKAGE_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [SchemaPackageProjector(), AdoptionProjector(), WaiverProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={
            SCHEMA_PACKAGE: PACKAGE_GENERIC_COMMANDS,
            ADOPTION: frozenset(),
            WAIVER: frozenset(),
        },
        schema_source=schema_source,
    )
