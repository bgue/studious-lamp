"""Names the requisitions module shares: record types, tables, views, events, kinds.

Plain constants, so a projector, a handler, a view and a test spell them the same way.
"""

from __future__ import annotations

from typing import Final

LABOR: Final = "requisitions.LaborRequisition"
MATERIAL: Final = "requisitions.MaterialRequisition"
GENERAL: Final = "requisitions.GeneralRequisition"
SCAFFOLD: Final = "requisitions.ScaffoldRequest"
WORK_ORDER: Final = "requisitions.WorkOrder"
#: The four kinds of requisition, in the order of ``KINDS``.
REQUISITION_TYPES: Final = (LABOR, MATERIAL, GENERAL, SCAFFOLD)
RECORD_TYPES: Final = frozenset({LABOR, MATERIAL, GENERAL, SCAFFOLD, WORK_ORDER})

#: ``kind`` slot value to record type.
KINDS: Final = {
    "labor": LABOR,
    "material": MATERIAL,
    "general": GENERAL,
    "scaffold": SCAFFOLD,
}

LABOR_TABLE: Final = "cur_requisitions_labor_requisition"
MATERIAL_TABLE: Final = "cur_requisitions_material_requisition"
GENERAL_TABLE: Final = "cur_requisitions_general_requisition"
SCAFFOLD_TABLE: Final = "cur_requisitions_scaffold_request"
WORK_ORDER_TABLE: Final = "cur_requisitions_work_order"
#: Record type to its current-state table.
TABLES: Final = {
    LABOR: LABOR_TABLE,
    MATERIAL: MATERIAL_TABLE,
    GENERAL: GENERAL_TABLE,
    SCAFFOLD: SCAFFOLD_TABLE,
    WORK_ORDER: WORK_ORDER_TABLE,
}

LABOR_VIEW: Final = "v_requisitions_labor_requisition"
MATERIAL_VIEW: Final = "v_requisitions_material_requisition"
GENERAL_VIEW: Final = "v_requisitions_general_requisition"
SCAFFOLD_VIEW: Final = "v_requisitions_scaffold_request"
WORK_ORDER_VIEW: Final = "v_requisitions_work_order"

REQUISITION_RAISED: Final = "Requisition.Raised"
REQUISITION_REVISED: Final = "Requisition.Revised"
REQUISITION_APPROVED: Final = "Requisition.Approved"
REQUISITION_REJECTED: Final = "Requisition.Rejected"
REQUISITION_CANCELLED: Final = "Requisition.Cancelled"
REQUISITION_FULFILLED: Final = "Requisition.Fulfilled"
WORK_ORDER_OPENED: Final = "WorkOrder.Opened"
WORK_ORDER_SCHEDULED: Final = "WorkOrder.Scheduled"
WORK_ORDER_ASSIGNED: Final = "WorkOrder.Assigned"
WORK_ORDER_STARTED: Final = "WorkOrder.Started"
WORK_ORDER_COMPLETED: Final = "WorkOrder.Completed"
WORK_ORDER_CLOSED: Final = "WorkOrder.Closed"
REQUISITION_EVENTS: Final = frozenset(
    {
        REQUISITION_RAISED,
        REQUISITION_REVISED,
        REQUISITION_APPROVED,
        REQUISITION_REJECTED,
        REQUISITION_CANCELLED,
        REQUISITION_FULFILLED,
    }
)
WORK_ORDER_EVENTS: Final = frozenset(
    {
        WORK_ORDER_OPENED,
        WORK_ORDER_SCHEDULED,
        WORK_ORDER_ASSIGNED,
        WORK_ORDER_STARTED,
        WORK_ORDER_COMPLETED,
        WORK_ORDER_CLOSED,
    }
)

MAX_LINES: Final = 200

# --- states (the workflow files ``schema/fixtures/workflows/requisitions-*.yaml``) ---------------
ST_REQUESTED: Final = "Requested"
ST_APPROVED: Final = "Approved"
ST_SCHEDULED: Final = "Scheduled"
ST_IN_PROGRESS: Final = "In progress"
ST_DONE: Final = "Done"
ST_CLOSED: Final = "Closed"
ST_REJECTED: Final = "Rejected"
ST_CANCELLED: Final = "Cancelled"
ST_OPEN: Final = "Open"
#: States of a requisition, and of a work order, that take no further command.
REQUISITION_FINAL: Final = frozenset({ST_CLOSED, ST_REJECTED, ST_CANCELLED})
WORK_ORDER_FINAL: Final = frozenset({ST_CLOSED, ST_CANCELLED})

# --- links ---------------------------------------------------------------------------------------
REQUIRES_RELATION: Final = "requires"
REFERENCES_RELATION: Final = "references"
RULE_LINK_SOURCE: Final = "rule"
FEED_NONE: Final = "none"
FEED_FULL: Final = "full"

# --- other modules' record types the commands name (read through ``cur_core_record`` only) -------
IWP_TYPE: Final = "awp.IWP"
CWP_TYPE: Final = "awp.CWP"
COST_CODE_TYPE: Final = "cost.CostCode"
ACTIVITY_TYPE: Final = "schedule.ActivityRef"
PROJECT_ITEM_TYPE: Final = "materials.ProjectItem"
LOCATION_TYPE: Final = "materials.InventoryLocation"
GENERAL_TYPE_LIST: Final = "GeneralRequisitionType"

# --- access words (``schema/settings/access-words.yaml``) ----------------------------------------
RAISE: Final = "requisitions.raise"
EDIT: Final = "requisitions.edit"
APPROVE: Final = "requisitions.approve"
REJECT: Final = "requisitions.reject"
CANCEL: Final = "requisitions.cancel"
SCHEDULE: Final = "requisitions.schedule"
ASSIGN: Final = "requisitions.assign"
START: Final = "requisitions.start"
COMPLETE: Final = "requisitions.complete"
CLOSE: Final = "requisitions.close"
