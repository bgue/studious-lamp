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
IWP_CLOSEOUT: Final = "awp.IWPCloseout"
WEEKLY_PLAN: Final = "awp.WeeklyPlan"
COST_CODE: Final = "cost.CostCode"
RECORD_TYPES: Final = frozenset(
    {WBS_NODE, PATH, CWA, CWP, EWP, PWP, IWP, SCOPE_ITEM, IWP_CLOSEOUT, WEEKLY_PLAN}
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
IWP_CLOSEOUT_TABLE: Final = "cur_awp_iwp_closeout"
WEEKLY_PLAN_TABLE: Final = "cur_awp_weekly_plan"
WEEK_COMMITMENT_TABLE: Final = "cur_awp_week_commitment"
IWP_PROGRESS_TABLE: Final = "cur_awp_iwp_progress"
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
PIN_RELATION: Final = "references"
DOCUMENT_TYPE: Final = "documents.Document"
TAG_TYPE: Final = "engineering.Tag"

WEEKLY_PLAN_VIEW: Final = "v_awp_weekly_plan"
IWP_VIEW: Final = "v_awp_iwp"
SCOPE_ITEM_VIEW: Final = "v_awp_scope_item"

IWP_CREATED: Final = "IWP.Created"
IWP_REVISED: Final = "IWP.Revised"
IWP_SCOPE_ADDED: Final = "IWP.ScopeAdded"
IWP_SCOPE_REMOVED: Final = "IWP.ScopeRemoved"
IWP_DOCUMENT_PINNED: Final = "IWP.DocumentPinned"
IWP_SPLIT: Final = "IWP.Split"
IWP_SIGNED_OFF: Final = "IWP.SignedOff"
IWP_ISSUED_EVENT: Final = "IWP.Issued"
IWP_HELD: Final = "IWP.Held"
IWP_HOLD_RELEASED: Final = "IWP.HoldReleased"
SCOPE_ITEM_CREATED: Final = "ScopeItem.Created"

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
#: Terminal states: the generic commands (``guards.not_closed``) refuse them.
IWP_TERMINAL: Final = (IWP_CLOSED, IWP_SPLIT_STATE, IWP_CANCELLED)
#: The states of a scope item.
SCI_PLANNED: Final = "Planned"
SCI_VERIFIED: Final = "Verified"
SCI_VOID: Final = "Void"

#: Fixed sizing warning codes (the ``message`` of a ``guards_evaluated`` entry of the event).
WARN_OVERSIZE: Final = "iwp_oversize"
WARN_UNDERSIZE: Final = "iwp_undersize"

#: Sign-off, issue and hold (P2-I2 S3): settings, tables and the limits of the sign-off list.
SIGNOFF_ROLES_SETTING: Final = "awp.release.signoff_roles"
UNKNOWN_CHECKS_SETTING: Final = "awp.release.allow_unknown_checks"
MAX_SIGNOFFS: Final = 4
SIGNERS_NEEDED: Final = 2

#: Readiness (P2-I2 S4): the job kind, its job id prefix, the events and the actor of the job.
JOB_KIND_READINESS: Final = "awp.readiness"
READINESS_JOB_PREFIX: Final = "ready:"
READINESS_SOURCE: Final = f"job:{JOB_KIND_READINESS}"
READINESS_ACTOR: Final = "svc:awp.readiness"
IWP_READINESS_EVALUATED: Final = "IWP.ReadinessEvaluated"
IWP_READY_EVENT: Final = "IWP.Ready"
TRANSITION_READY: Final = "ready"
TRANSITION_UNREADY: Final = "unready"
CONSTRAINT_TYPE: Final = "core.Constraint"
CONSTRAINT_TABLE: Final = "cur_core_constraint"

#: Weekly plan, progress, closeout and subcontract (P2-I5 S1): the events and the weekly plan workflow.
WEEK_OPENED: Final = "WeeklyPlan.Opened"
WEEK_IWP_COMMITTED: Final = "WeeklyPlan.IwpCommitted"
WEEK_OUTCOME_RECORDED: Final = "WeeklyPlan.OutcomeRecorded"
WEEK_CLOSED: Final = "WeeklyPlan.Closed"
IWP_STARTED: Final = "IWP.Started"
IWP_PROGRESS_RECORDED: Final = "IWP.ProgressRecorded"
IWP_FIELD_COMPLETED: Final = "IWP.FieldCompleted"
IWP_CLOSEOUT_RECORDED: Final = "IWPCloseout.Recorded"
CWP_PARTY_ASSIGNED: Final = "Cwp.PartyAssigned"
CWP_SUBCONTRACT_PROGRESS: Final = "Cwp.SubcontractProgressRecorded"
#: The states of the weekly plan workflow (``schema/fixtures/workflows/awp-weekly-plan.yaml``).
WEEK_DRAFT: Final = "Draft"
WEEK_COMMITTED: Final = "Committed"
WEEK_CLOSED_STATE: Final = "Closed"
OUTCOME_DONE: Final = "done"
OUTCOME_MISSED: Final = "missed"
#: The events of this part whose payload carries ``feed_policy: none``. ``WeeklyPlan.Closed`` and
#: ``IWPCloseout.Recorded`` make a feed card. (``tl_core.feed.cards`` honours the key only for the
#: names in its ``POLICY_EVENT_TYPES``, as for the IWP events: the key is data, not yet read.)
PART3_NO_CARD_EVENTS: Final = (
    WEEK_OPENED,
    WEEK_IWP_COMMITTED,
    WEEK_OUTCOME_RECORDED,
    IWP_STARTED,
    IWP_PROGRESS_RECORDED,
    IWP_FIELD_COMPLETED,
    CWP_PARTY_ASSIGNED,
    CWP_SUBCONTRACT_PROGRESS,
)
