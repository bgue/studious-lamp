"""Names the awp module shares: record types, event types, tables, relations, the job kind.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

WBS_NODE: Final = "awp.WBSNode"
PATH: Final = "awp.PathOfConstruction"
CWA: Final = "awp.CWA"
CWP: Final = "awp.CWP"
EWP: Final = "awp.EWPRef"
PWP: Final = "awp.PWPRef"
IWP: Final = "awp.IWP"
SCOPE_ITEM: Final = "awp.ScopeItem"
CONSTRAINT: Final = "awp.Constraint"
IWP_CLOSEOUT: Final = "awp.IWPCloseout"
COST_CODE: Final = "cost.CostCode"
RECORD_TYPES: Final = frozenset(
    {WBS_NODE, PATH, CWA, CWP, EWP, PWP, IWP, SCOPE_ITEM, CONSTRAINT, IWP_CLOSEOUT}
)
PACKAGE_TYPES: Final = (EWP, PWP)

#: The namespace of a record key. A typed key cannot hold ``@``, so no typed record of another
#: module can equal one (``tl_core.services.records.create_module_record`` ``composed_key``).
KEY_PREFIX: Final = {WBS_NODE: "awp.wbs@", CWA: "awp.cwa@", EWP: "awp.ewp@", PWP: "awp.pwp@"}

WBS_NODE_TABLE: Final = "cur_awp_wbs_node"
WBS_ALLOCATION_TABLE: Final = "cur_awp_wbs_allocation"
PATH_TABLE: Final = "cur_awp_path"
PATH_STEP_TABLE: Final = "cur_awp_path_step"
CWA_TABLE: Final = "cur_awp_cwa"
CWP_TABLE: Final = "cur_awp_cwp"
CWP_ALLOCATION_TABLE: Final = "cur_awp_cwp_allocation"
EWP_TABLE: Final = "cur_awp_ewp_ref"
PWP_TABLE: Final = "cur_awp_pwp_ref"
IWP_TABLE: Final = "cur_awp_iwp"
SCOPE_ITEM_TABLE: Final = "cur_awp_scope_item"
CONSTRAINT_TABLE: Final = "cur_awp_constraint"
IWP_CLOSEOUT_TABLE: Final = "cur_awp_iwp_closeout"
READINESS_TABLE: Final = "cur_awp_readiness"
READINESS_CHECK_TABLE: Final = "cur_awp_readiness_check"
PACKAGE_TABLE: Final = {EWP: EWP_TABLE, PWP: PWP_TABLE}
WBS_NODE_VIEW: Final = "v_awp_wbsnode"
PATH_VIEW: Final = "v_awp_path_of_construction"
CWA_VIEW: Final = "v_awp_cwa"
CWP_VIEW: Final = "v_awp_cwp"
EWP_VIEW: Final = "v_awp_ewpref"
PWP_VIEW: Final = "v_awp_pwpref"

WBS_DEFINED: Final = "WBSNode.Defined"
WBS_REVISED: Final = "WBSNode.Revised"
WBS_RETIRED: Final = "WBSNode.Retired"
WBS_REINSTATED: Final = "WBSNode.Reinstated"
WBS_COST_CODES_MAPPED: Final = "WBSNode.CostCodesMapped"
PATH_DEFINED: Final = "PathOfConstruction.Defined"
PATH_RESEQUENCED: Final = "PathOfConstruction.Resequenced"
CWA_DEFINED: Final = "CWA.Defined"
CWA_REVISED: Final = "CWA.Revised"
CWA_RETIRED: Final = "CWA.Retired"
CWP_DEFINED: Final = "CWP.Defined"
CWP_REVISED: Final = "CWP.Revised"
CWP_ALLOCATED: Final = "CWP.AllocatedToWbs"
CWP_RELEASED: Final = "CWP.Released"
PACKAGE_DEFINED: Final = {EWP: "EWPRef.Defined", PWP: "PWPRef.Defined"}
PACKAGE_UPDATED: Final = {EWP: "EWPRef.Updated", PWP: "PWPRef.Updated"}

#: The states of the CWP workflow (``schema/fixtures/workflows/awp-cwp.yaml``).
ST_PLANNED: Final = "Planned"
ST_DEVELOPMENT: Final = "In development"
ST_RELEASED: Final = "Released for IWP development"
ST_EXECUTING: Final = "Executing"
ST_COMPLETE: Final = "Complete"
ST_CLOSED: Final = "Closed"
ST_VOID: Final = "Void"
#: The states in which the fields of a package may change (frozen from Released).
EDITABLE_STATES: Final = (ST_PLANNED, ST_DEVELOPMENT)

#: The nine events with ``feed_policy: none`` (the schema); ``tl_core.feed.cards`` names the same.
NO_CARD_EVENTS: Final = (
    "WBSNode.Defined",
    "WBSNode.Revised",
    "WBSNode.Retired",
    "WBSNode.Reinstated",
    "WBSNode.CostCodesMapped",
    "WBSNode.BudgetRolledUp",
    "PathOfConstruction.Defined",
    "PathOfConstruction.Resequenced",
    "CWP.AllocatedToWbs",
)
FEED_NONE: Final = "none"

#: Relation of the link from a WBS node to each cost code it is allocated to (the module writes it).
COST_RELATION: Final = "references"
#: Relation of the link from a CWP to its area and to each WBS node it is allocated to.
BELONGS_RELATION: Final = "belongs_to"
RULE_LINK_SOURCE: Final = "rule"

JOB_KIND_ROLLUP: Final = "awp.rollup"
ROLLUP_JOB_PREFIX: Final = "rollup:"

#: Relation words of the links the IWP commands write (the links carry no schema class).
#: ``contains`` is how a scope reads from the IWP; the vocabulary holds it as the inverse of
#: ``belongs_to`` (``tl_core.links.vocabulary``), so the stored link is ``belongs_to`` from the
#: scope record to the IWP (``SCOPE_RELATION``) and ``contains`` is its inverse reading.
CONTAINS_RELATION: Final = "contains"
SCOPE_RELATION: Final = "belongs_to"
BLOCKS_RELATION: Final = "blocks"
RESOLVES_RELATION: Final = "resolves"
PIN_RELATION: Final = "references"
DOCUMENT_TYPE: Final = "documents.Document"
TAG_TYPE: Final = "engineering.Tag"

IWP_VIEW: Final = "v_awp_iwp"
SCOPE_ITEM_VIEW: Final = "v_awp_scope_item"
CONSTRAINT_VIEW: Final = "v_awp_constraint"

IWP_CREATED: Final = "IWP.Created"
IWP_REVISED: Final = "IWP.Revised"
IWP_SCOPE_ADDED: Final = "IWP.ScopeAdded"
IWP_SCOPE_REMOVED: Final = "IWP.ScopeRemoved"
IWP_DOCUMENT_PINNED: Final = "IWP.DocumentPinned"
IWP_SPLIT: Final = "IWP.Split"
SCOPE_ITEM_CREATED: Final = "ScopeItem.Created"
CONSTRAINT_RAISED: Final = "Constraint.Raised"
CONSTRAINT_ASSIGNED: Final = "Constraint.Assigned"
CONSTRAINT_CLEARED: Final = "Constraint.Cleared"

#: The states of the IWP workflow (``schema/fixtures/workflows/awp-iwp.yaml``).
IWP_DRAFT: Final = "Draft"
IWP_DEVELOPMENT: Final = "In development"
IWP_CHECK: Final = "Constraint check"
IWP_READY: Final = "Ready"
IWP_ISSUED: Final = "Issued"
IWP_IN_PROGRESS: Final = "In progress"
IWP_FIELD_COMPLETE: Final = "Field complete"
IWP_CLOSED: Final = "Closed"
IWP_ON_HOLD: Final = "On hold"
IWP_SPLIT_STATE: Final = "Split"
IWP_CANCELLED: Final = "Cancelled"
#: States in which the fields and the scope of an IWP may change (frozen from Ready).
IWP_EDITABLE: Final = (IWP_DRAFT, IWP_DEVELOPMENT, IWP_CHECK)
#: Terminal states: the generic commands (``guards.not_closed``) and a new constraint refuse them.
IWP_TERMINAL: Final = (IWP_CLOSED, IWP_SPLIT_STATE, IWP_CANCELLED)
#: The states of the constraint workflow and of a scope item.
CON_OPEN: Final = "Open"
CON_ASSIGNED: Final = "Assigned"
CON_CLEARED: Final = "Cleared"
CON_VOID: Final = "Void"
SCI_PLANNED: Final = "Planned"
SCI_VERIFIED: Final = "Verified"
SCI_VOID: Final = "Void"

#: Constraint sources: a person raises ``manual``; a module raises the other four.
SOURCE_MANUAL: Final = "manual"
MODULE_SOURCES: Final = ("check", "rule", "feed_hold", "thread_hold")
ALL_SOURCES: Final = (SOURCE_MANUAL, *MODULE_SOURCES)

#: Fixed warning codes of the IWP sizing check (carried in the ``warnings`` list of the event).
WARN_OVERSIZE: Final = "iwp_oversize"
WARN_UNDERSIZE: Final = "iwp_undersize"
CODE_SUPPRESSED: Final = "suppressed"
