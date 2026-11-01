"""The commands the materials module offers to the API (m4-materials.md section 3).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` is a row of
``schema/settings/access-words.yaml`` (nothing is invented here); the module's
``command_words`` carry
the same rows. This piece (S2) holds the library, location and PO-line commands and the MTO seam;
S3 appends the receipt and movement commands in a later piece.
"""

from __future__ import annotations

from tl_mod_materials.common import CommandSpec
from tl_mod_materials.handlers.items import (
    AdoptItem,
    DefineItem,
    RetireItem,
    ReviseItem,
    handle_adopt_item,
    handle_define_item,
    handle_retire_item,
    handle_revise_item,
)
from tl_mod_materials.handlers.locations import (
    DefineLocation,
    RetireLocation,
    ReviseLocation,
    handle_define_location,
    handle_retire_location,
    handle_revise_location,
)
from tl_mod_materials.handlers.po_lines import (
    RecordPoLine,
    UpdatePoLine,
    handle_record_po_line,
    handle_update_po_line,
)
from tl_mod_materials.mto import MTO_COMMANDS

#: The word the API table (``tl_api.commands``) reads for the builder's row type.
ApiCommand = CommandSpec

LIBRARY_EDIT = "materials.library.edit"
ITEM_ADOPT = "materials.item.adopt"
LOCATION_CONFIGURE = "materials.location.configure"
PO_EDIT = "materials.po.edit"
MOVE = "materials.move"

MATERIALS_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(DefineItem, handle_define_item, LIBRARY_EDIT),
    CommandSpec(ReviseItem, handle_revise_item, LIBRARY_EDIT),
    CommandSpec(RetireItem, handle_retire_item, LIBRARY_EDIT),
    CommandSpec(AdoptItem, handle_adopt_item, ITEM_ADOPT),
    CommandSpec(DefineLocation, handle_define_location, LOCATION_CONFIGURE),
    CommandSpec(ReviseLocation, handle_revise_location, LOCATION_CONFIGURE),
    CommandSpec(RetireLocation, handle_retire_location, LOCATION_CONFIGURE),
    CommandSpec(RecordPoLine, handle_record_po_line, PO_EDIT),
    CommandSpec(UpdatePoLine, handle_update_po_line, PO_EDIT),
    *MTO_COMMANDS,
)

#: The three drafting commands of ``StockLot`` (``ModuleSpec.offline_drafts``). Their handlers are
#: S3's; the module load check needs their words today, so the words are listed here and S3 replaces
#: them with its ``CommandSpec`` rows (the module takes ``command_words`` from both).
DRAFT_COMMAND_WORDS: dict[str, str] = {
    "IssueStock": MOVE,
    "TransferStock": MOVE,
    "ReturnStock": MOVE,
}
