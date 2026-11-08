"""What the requisitions module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``requisitions`` in this package's ``pyproject.toml``
names ``spec``. The module registers its record types and projectors; it has no command yet
(``REQUISITIONS_COMMANDS`` is the placeholder P2-I4A S2 fills). The four requisition kinds are
``draft_only`` offline and the work order is ``none`` (``schema/modules/requisitions``); the
drafts a foreman captures are listed with the commands."""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_requisitions import MODULE
from tl_mod_requisitions.names import RECORD_TYPES
from tl_mod_requisitions.projectors import RequisitionProjector, WorkOrderProjector

#: Placeholder: the commands are built by P2-I4A S2.
REQUISITIONS_COMMANDS: tuple[object, ...] = ()


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [RequisitionProjector(), WorkOrderProjector()]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        company_roles=False,
    )
