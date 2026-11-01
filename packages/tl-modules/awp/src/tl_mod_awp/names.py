"""Names the awp module shares: record types, event types, tables, relations, the job kind.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

WBS_NODE: Final = "awp.WBSNode"
PATH: Final = "awp.PathOfConstruction"
CWA: Final = "awp.CWA"
COST_CODE: Final = "cost.CostCode"
#: S4 adds ``awp.CWP``, ``awp.EWPRef`` and ``awp.PWPRef``.
RECORD_TYPES: Final = frozenset({WBS_NODE, PATH, CWA})

WBS_NODE_TABLE: Final = "cur_awp_wbs_node"
WBS_ALLOCATION_TABLE: Final = "cur_awp_wbs_allocation"
PATH_TABLE: Final = "cur_awp_path"
PATH_STEP_TABLE: Final = "cur_awp_path_step"
CWA_TABLE: Final = "cur_awp_cwa"
CWP_TABLE: Final = "cur_awp_cwp"  # written by S4's projector
CWP_ALLOCATION_TABLE: Final = "cur_awp_cwp_allocation"  # written by S4's projector
WBS_NODE_VIEW: Final = "v_awp_wbsnode"
PATH_VIEW: Final = "v_awp_path_of_construction"
CWA_VIEW: Final = "v_awp_cwa"

WBS_DEFINED: Final = "WBSNode.Defined"
WBS_REVISED: Final = "WBSNode.Revised"
WBS_RETIRED: Final = "WBSNode.Retired"
WBS_COST_CODES_MAPPED: Final = "WBSNode.CostCodesMapped"
PATH_DEFINED: Final = "PathOfConstruction.Defined"
PATH_RESEQUENCED: Final = "PathOfConstruction.Resequenced"
CWA_DEFINED: Final = "CWA.Defined"
CWA_REVISED: Final = "CWA.Revised"
CWA_RETIRED: Final = "CWA.Retired"

#: The eight events with ``feed_policy: none`` (the schema); ``tl_core.feed.cards`` names the same.
NO_CARD_EVENTS: Final = (
    "WBSNode.Defined",
    "WBSNode.Revised",
    "WBSNode.Retired",
    "WBSNode.CostCodesMapped",
    "WBSNode.BudgetRolledUp",
    "PathOfConstruction.Defined",
    "PathOfConstruction.Resequenced",
    "CWP.AllocatedToWbs",
)
FEED_NONE: Final = "none"

#: Relation of the link from a WBS node to each cost code it is allocated to (the module writes it).
COST_RELATION: Final = "references"
RULE_LINK_SOURCE: Final = "rule"

JOB_KIND_ROLLUP: Final = "awp.rollup"
ROLLUP_JOB_PREFIX: Final = "rollup:"
