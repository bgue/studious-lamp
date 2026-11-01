"""Names the materials module shares: record types, event types, tables, views, relations.

Plain constants, so a projector, a handler, a view, a CLI command and a test all spell them the
same way (as ``tl_mod_cost.names``).
"""

from __future__ import annotations

from typing import Final

ITEM_MASTER: Final = "materials.ItemMaster"
PROJECT_ITEM: Final = "materials.ProjectItem"
LOCATION: Final = "materials.InventoryLocation"
PO_LINE: Final = "materials.POLineRef"
RECEIPT: Final = "materials.Receipt"
STOCK_LOT: Final = "materials.StockLot"
MTO: Final = "materials.MTO"
MTO_LINE: Final = "materials.MTOLine"
RECORD_TYPES: Final = frozenset(
    {ITEM_MASTER, PROJECT_ITEM, LOCATION, PO_LINE, RECEIPT, STOCK_LOT, MTO, MTO_LINE}
)

ITEM_MASTER_TABLE: Final = "cur_materials_item_master"
PROJECT_ITEM_TABLE: Final = "cur_materials_project_item"
LOCATION_TABLE: Final = "cur_materials_location"
PO_LINE_TABLE: Final = "cur_materials_po_line"
RECEIPT_TABLE: Final = "cur_materials_receipt"
RECEIPT_LINE_TABLE: Final = "cur_materials_receipt_line"
LOT_TABLE: Final = "cur_materials_lot"
MTO_TABLE: Final = "cur_materials_mto"
MTO_LINE_TABLE: Final = "cur_materials_mto_line"
MOVEMENT_TABLE: Final = "cur_materials_movement"
STOCK_TABLE: Final = "cur_materials_stock"
RESERVATION_TABLE: Final = "cur_materials_reservation"

ITEM_MASTER_VIEW: Final = "v_materials_item_master"
PROJECT_ITEM_VIEW: Final = "v_materials_project_item"
LOCATION_VIEW: Final = "v_materials_inventory_location"
PO_LINE_VIEW: Final = "v_materials_poline_ref"
RECEIPT_VIEW: Final = "v_materials_receipt"
LOT_VIEW: Final = "v_materials_stock_lot"
MTO_VIEW: Final = "v_materials_mto"
MTO_LINE_VIEW: Final = "v_materials_mtoline"

ITEM_DEFINED: Final = "ItemMaster.Defined"
ITEM_REVISED: Final = "ItemMaster.Revised"
ITEM_RETIRED: Final = "ItemMaster.Retired"
PROJECT_ITEM_DEFINED: Final = "ProjectItem.Defined"
LOCATION_DEFINED: Final = "InventoryLocation.Defined"
LOCATION_REVISED: Final = "InventoryLocation.Revised"
LOCATION_RETIRED: Final = "InventoryLocation.Retired"
PO_LINE_DEFINED: Final = "POLineRef.Defined"
PO_LINE_UPDATED: Final = "POLineRef.Updated"
RECEIPT_DEFINED: Final = "Receipt.Defined"
RECEIPT_REVISED: Final = "Receipt.Revised"
RECEIPT_INSPECTED: Final = "Receipt.Inspected"
RECEIPT_ACCEPTED: Final = "Receipt.Accepted"
RECEIPT_REJECTED: Final = "Receipt.Rejected"
LOT_DEFINED: Final = "StockLot.Defined"
LOT_MOVED: Final = "StockLot.Moved"
MTO_DEFINED: Final = "MTO.Defined"
MTO_LINE_DEFINED: Final = "MTOLine.Defined"
MTO_LINE_ASSIGNED: Final = "MTOLine.Assigned"

#: The eight kinds of ``StockLot.Moved`` (ADR-0022).
RECEIVE: Final = "receive"
ISSUE: Final = "issue"
TRANSFER: Final = "transfer"
RETURN: Final = "return"
ADJUST: Final = "adjust"
SCRAP: Final = "scrap"
RESERVE: Final = "reserve"
UNRESERVE: Final = "unreserve"
MOVEMENT_KINDS: Final = frozenset(
    {RECEIVE, ISSUE, TRANSFER, RETURN, ADJUST, SCRAP, RESERVE, UNRESERVE}
)

#: Names of the load targets (entry points of ``throughline.load_targets``). The group allows
#: ``^[a-z][a-z0-9_]*$``, so the spec's ``materials.item_master`` is written with an underscore.
TARGET_ITEM_MASTER: Final = "materials_item_master"
TARGET_LOCATION: Final = "materials_location"
TARGET_PO_LINE: Final = "materials_po_line"

#: Relations the module writes (the thirteen of brief 7.1; no new relation).
DERIVED_FROM: Final = "derived_from"
BELONGS_TO: Final = "belongs_to"
REFERENCES: Final = "references"

#: The company scope of the item library.
COMPANY: Final = "company"
