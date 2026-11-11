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

#: Fine access words (``schema/settings/access-words.yaml``).
RAISE: Final = "quality.punch.raise"
EDIT: Final = "quality.punch.edit"
CLEAR: Final = "quality.punch.clear"
VERIFY: Final = "quality.punch.verify"
REOPEN: Final = "quality.punch.reopen"
VOID_WORD: Final = "quality.punch.void"

#: Workflow transitions (``schema/fixtures/workflows/quality-punch-item.yaml``).
T_CLEAR: Final = "clear"
T_VERIFY: Final = "verify"
T_REOPEN: Final = "reopen"
T_VOID: Final = "void"

#: The link from a punch item to the record it was raised from, and its (module) source.
RAISED_AGAINST: Final = "raised_against"
RULE_LINK_SOURCE: Final = "rule"
FEED_NONE: Final = "none"
