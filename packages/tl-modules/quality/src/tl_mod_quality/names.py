"""Names the quality module shares: record type, event types, table, workflow.

Plain constants, so a projector, a command, a view and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

PUNCH_ITEM: Final = "quality.PunchItem"
RECORD_TYPES: Final = frozenset({PUNCH_ITEM})

PUNCH_ITEM_TABLE: Final = "cur_quality_punch_item"
PUNCH_ITEM_VIEW: Final = "v_quality_punch_item"

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

#: Workflow states.
OPEN: Final = "Open"
CLEARED: Final = "Cleared"
VERIFIED: Final = "Verified"
VOID: Final = "Void"

#: Categories (`PunchCategory`); the default is B.
CATEGORIES: Final = ("A", "B", "C")
DEFAULT_CATEGORY: Final = "B"
