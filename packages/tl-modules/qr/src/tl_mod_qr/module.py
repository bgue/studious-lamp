"""What the QR module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``qr`` names ``spec``. This slice holds the record type
and its projector only: no commands (a later piece adds issue and revoke), no hook fields.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_qr import MODULE
from tl_mod_qr.names import RECORD_TYPES
from tl_mod_qr.projectors import ScanCodeProjector


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [ScanCodeProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        command_words={},
        proposable=(),
    )
