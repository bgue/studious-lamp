"""The commands the materials module offers to the API (m4-materials.md section 3).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` is a row of
``schema/settings/access-words.yaml`` (nothing is invented here); the module's
``command_words`` carry
the same rows. The table is complete: the library, location and PO-line commands (S2), the six
receipt commands and seven movement commands (S3), and the MTO commands (``mto.py``, S4).
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
from tl_mod_materials.handlers.movements import (
    AdjustStock,
    IssueStock,
    ReserveStock,
    ReturnStock,
    ScrapStock,
    TransferStock,
    UnreserveStock,
    handle_adjust_stock,
    handle_issue_stock,
    handle_reserve_stock,
    handle_return_stock,
    handle_scrap_stock,
    handle_transfer_stock,
    handle_unreserve_stock,
)
from tl_mod_materials.handlers.po_lines import (
    RecordPoLine,
    UpdatePoLine,
    handle_record_po_line,
    handle_update_po_line,
)
from tl_mod_materials.handlers.receipts import (
    AcceptReceipt,
    CreateReceipt,
    InspectReceipt,
    RejectReceipt,
    ReviseReceipt,
    VoidReceipt,
    handle_accept_receipt,
    handle_create_receipt,
    handle_inspect_receipt,
    handle_reject_receipt,
    handle_revise_receipt,
    handle_void_receipt,
)
from tl_mod_materials.mto import MTO_COMMANDS

#: The word the API table (``tl_api.commands``) reads for the builder's row type.
ApiCommand = CommandSpec

LIBRARY_EDIT = "materials.library.edit"
ITEM_ADOPT = "materials.item.adopt"
LOCATION_CONFIGURE = "materials.location.configure"
PO_EDIT = "materials.po.edit"
RECEIVE = "materials.receive"
RECEIPT_DECIDE = "materials.receipt.decide"
VOID = "materials.void"
MOVE = "materials.move"
RESERVE = "materials.reserve"
ADJUST = "materials.adjust"

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
    CommandSpec(CreateReceipt, handle_create_receipt, RECEIVE),
    CommandSpec(ReviseReceipt, handle_revise_receipt, RECEIVE),
    CommandSpec(InspectReceipt, handle_inspect_receipt, RECEIVE),
    CommandSpec(AcceptReceipt, handle_accept_receipt, RECEIPT_DECIDE),
    CommandSpec(RejectReceipt, handle_reject_receipt, RECEIPT_DECIDE),
    CommandSpec(VoidReceipt, handle_void_receipt, VOID),
    CommandSpec(IssueStock, handle_issue_stock, MOVE),
    CommandSpec(TransferStock, handle_transfer_stock, MOVE),
    CommandSpec(ReturnStock, handle_return_stock, MOVE),
    CommandSpec(ReserveStock, handle_reserve_stock, RESERVE),
    CommandSpec(UnreserveStock, handle_unreserve_stock, RESERVE),
    CommandSpec(AdjustStock, handle_adjust_stock, ADJUST),
    CommandSpec(ScrapStock, handle_scrap_stock, ADJUST),
    *MTO_COMMANDS,
)
