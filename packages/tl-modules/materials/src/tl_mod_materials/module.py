"""What the materials module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``materials`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process. The module declares ``company_roles``: the item
library is the company's, so a company-scope grant of a materials role is allowed (answer 14 of
the wave-0 spec). ``StockLot`` is ``draft_only``: issue, transfer and return are captured offline
as drafts and posted on sync (``offline_drafts``).
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec
from tl_core.projection.types import Projector

from tl_mod_materials import MODULE
from tl_mod_materials.commands import DRAFT_COMMAND_WORDS, MATERIALS_COMMANDS
from tl_mod_materials.guards import receipt_upload_guard
from tl_mod_materials.names import (
    MTO,
    MTO_LINE,
    PO_LINE,
    PROJECT_ITEM,
    RECEIPT,
    RECORD_TYPES,
    STOCK_LOT,
)
from tl_mod_materials.projectors import (
    ItemMasterProjector,
    LocationProjector,
    LotProjector,
    MtoProjector,
    PoLineProjector,
    ProjectItemProjector,
    ReceiptProjector,
    StockProjector,
)

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: What a person may do to a record of these types through the generic commands: link it.
LINK_ONLY = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE
#: A receipt also takes property sets and files (the guard limits files by state).
RECEIPT_GENERIC = frozenset({"SetPsetValues", "AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
#: Drafts a remote crew captures offline for a stock lot (offline-classes spec, section 4).
STOCK_LOT_DRAFTS = frozenset({"IssueStock", "TransferStock", "ReturnStock"})


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [
        ItemMasterProjector(),
        ProjectItemProjector(),
        LocationProjector(),
        PoLineProjector(),
        LotProjector(),
        ReceiptProjector(),
        MtoProjector(),
        StockProjector(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        # ItemMaster and InventoryLocation take none: they change through their own commands.
        # ``TransitionWorkflow``, ``UpdateRecord`` and ``VoidRecord`` are on nothing.
        generic_commands={
            RECEIPT: RECEIPT_GENERIC,
            STOCK_LOT: LINK_ONLY,
            MTO: LINK_ONLY,
            MTO_LINE: LINK_ONLY,
            PROJECT_ITEM: LINK_ONLY,
            PO_LINE: LINK_ONLY,
        },
        generic_guards={(RECEIPT, "AttachFile"): receipt_upload_guard},
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={
            **DRAFT_COMMAND_WORDS,
            **{c.model.__name__: c.access for c in MATERIALS_COMMANDS},
        },
        company_roles=True,
        offline_drafts={STOCK_LOT: STOCK_LOT_DRAFTS},
    )
