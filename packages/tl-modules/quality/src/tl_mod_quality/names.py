"""Names the quality module shares: record type, event types, table, workflow.

Plain constants, so a projector, a command, a view and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

PUNCH_ITEM: Final = "quality.PunchItem"
CHECKLIST: Final = "quality.Checklist"
INSPECTION: Final = "quality.Inspection"
RECORD_TYPES: Final = frozenset({PUNCH_ITEM, CHECKLIST, INSPECTION})

PUNCH_ITEM_TABLE: Final = "cur_quality_punch_item"
PUNCH_ITEM_VIEW: Final = "v_quality_punch_item"

CHECKLIST_TABLE: Final = "cur_quality_checklist"
CHECKLIST_VIEW: Final = "v_quality_checklist"
INSPECTION_TABLE: Final = "cur_quality_inspection"
INSPECTION_VIEW: Final = "v_quality_inspection"

CHECKLIST_WORKFLOW: Final = "quality.checklist"
INSPECTION_WORKFLOW: Final = "quality.inspection"
PUNCH_WORKFLOW: Final = "quality.punch-item"

PUNCH_RAISED: Final = "PunchItem.Raised"
PUNCH_EDITED: Final = "PunchItem.Edited"
PUNCH_CLEARED: Final = "PunchItem.Cleared"
PUNCH_VERIFIED: Final = "PunchItem.Verified"
PUNCH_REOPENED: Final = "PunchItem.Reopened"
PUNCH_VOIDED: Final = "PunchItem.Voided"
PUNCH_EVENTS: Final = frozenset(
    {PUNCH_RAISED, PUNCH_EDITED, PUNCH_CLEARED, PUNCH_VERIFIED, PUNCH_REOPENED, PUNCH_VOIDED}
)

CHECKLIST_CREATED: Final = "Checklist.Created"
CHECKLIST_EDITED: Final = "Checklist.Edited"
CHECKLIST_PUBLISHED: Final = "Checklist.Published"
CHECKLIST_RETIRED: Final = "Checklist.Retired"
CHECKLIST_EVENTS: Final = frozenset(
    {CHECKLIST_CREATED, CHECKLIST_EDITED, CHECKLIST_PUBLISHED, CHECKLIST_RETIRED}
)
INSPECTION_PLANNED: Final = "Inspection.Planned"
INSPECTION_SCHEDULED: Final = "Inspection.Scheduled"
INSPECTION_RESULT_RECORDED: Final = "Inspection.ResultRecorded"
INSPECTION_VERIFIED: Final = "Inspection.Verified"
INSPECTION_CANCELLED: Final = "Inspection.Cancelled"
INSPECTION_EVENTS: Final = frozenset(
    {
        INSPECTION_PLANNED,
        INSPECTION_SCHEDULED,
        INSPECTION_RESULT_RECORDED,
        INSPECTION_VERIFIED,
        INSPECTION_CANCELLED,
    }
)

#: Workflow states.
OPEN: Final = "Open"
CLEARED: Final = "Cleared"
VERIFIED: Final = "Verified"
VOID: Final = "Void"
#: Checklist states.
DRAFT: Final = "Draft"
PUBLISHED: Final = "Published"
RETIRED: Final = "Retired"
#: Inspection states (``Verified`` is shared with the punch item).
PLANNED: Final = "Planned"
SCHEDULED: Final = "Scheduled"
DONE: Final = "Done"
CANCELLED: Final = "Cancelled"

#: Inspection points (``InspectionPoint``) and results (``InspectionOutcome``).
POINTS: Final = ("hold", "witness", "review", "surveillance")
OUTCOMES: Final = ("accept", "reject", "conditional")

#: Categories (`PunchCategory`); the default is B.
CATEGORIES: Final = ("A", "B", "C")
DEFAULT_CATEGORY: Final = "B"

#: Fine access words (``schema/settings/access-words.yaml``).
RAISE: Final = "quality.punch.raise"
EDIT: Final = "quality.punch.edit"
CLEAR: Final = "quality.punch.clear"
VERIFY: Final = "quality.punch.verify"
REOPEN: Final = "quality.punch.reopen"
VOID_WORD: Final = "quality.punch.void"

CHECKLIST_EDIT: Final = "quality.checklist.edit"
CHECKLIST_PUBLISH: Final = "quality.checklist.publish"
INSPECTION_PLAN: Final = "quality.inspection.plan"
INSPECTION_RECORD: Final = "quality.inspection.record"
INSPECTION_VERIFY: Final = "quality.inspection.verify"
INSPECTION_CANCEL: Final = "quality.inspection.cancel"

#: Workflow transitions (``schema/fixtures/workflows/quality-punch-item.yaml``).
T_CLEAR: Final = "clear"
T_VERIFY: Final = "verify"
T_REOPEN: Final = "reopen"
T_VOID: Final = "void"
T_PUBLISH: Final = "publish"
T_RETIRE: Final = "retire"
T_SCHEDULE: Final = "schedule"
T_RECORD: Final = "record"
T_CANCEL: Final = "cancel"

#: The link from a punch item to the record it was raised from, and its (module) source.
RAISED_AGAINST: Final = "raised_against"
RULE_LINK_SOURCE: Final = "rule"
FEED_NONE: Final = "none"
