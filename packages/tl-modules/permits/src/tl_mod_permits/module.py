"""The permits module spec: three record types and their projectors.

S1 declares no commands, no proposable command, no generic-command rows and no hook fields;
S2 adds the commands and the hooks.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_permits import MODULE
from tl_mod_permits.names import RECORD_TYPES
from tl_mod_permits.projectors import GasTestProjector, IsolationProjector, PermitProjector


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [PermitProjector(), IsolationProjector(), GasTestProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        command_words={},
        proposable=(),
    )
