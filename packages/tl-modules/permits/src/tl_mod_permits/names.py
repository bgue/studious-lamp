"""Names the permits module shares: record types, tables, states, access words, event types.

Plain constants, so a projector, a command, a view and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

PERMIT: Final = "permits.Permit"
ISOLATION: Final = "permits.Isolation"
GAS_TEST: Final = "permits.GasTest"
RECORD_TYPES: Final = frozenset({PERMIT, ISOLATION, GAS_TEST})

PERMIT_TABLE: Final = "cur_permits_permit"
ISOLATION_TABLE: Final = "cur_permits_isolation"
GAS_TEST_TABLE: Final = "cur_permits_gas_test"
PERMIT_VIEW: Final = "v_permits_permit"
ISOLATION_VIEW: Final = "v_permits_isolation"
GAS_TEST_VIEW: Final = "v_permits_gas_test"

PERMIT_WORKFLOW: Final = "permits.permit"
ISOLATION_WORKFLOW: Final = "permits.isolation"

#: Permit workflow states. Lapsed is derived (state, `valid_until`, the clock), not a state.
REQUESTED: Final = "Requested"
APPROVED: Final = "Approved"
ACTIVE: Final = "Active"
SUSPENDED: Final = "Suspended"
HANDED_BACK: Final = "Handed back"
CLOSED: Final = "Closed"
REJECTED: Final = "Rejected"
CANCELLED: Final = "Cancelled"
PERMIT_STATES: Final = (
    REQUESTED,
    APPROVED,
    ACTIVE,
    SUSPENDED,
    HANDED_BACK,
    CLOSED,
    REJECTED,
    CANCELLED,
)
#: Isolation workflow states.
APPLIED: Final = "Applied"
VERIFIED: Final = "Verified"
REMOVED: Final = "Removed"
ISOLATION_STATES: Final = (APPLIED, VERIFIED, REMOVED)

#: Permit workflow transitions.
T_APPROVE: Final = "approve"
T_REJECT: Final = "reject"
T_ISSUE: Final = "issue"
T_REVALIDATE: Final = "revalidate"
T_SUSPEND: Final = "suspend"
T_RESUME: Final = "resume"
T_HAND_BACK: Final = "hand_back"
T_CLOSE: Final = "close"
T_CANCEL: Final = "cancel"
#: Isolation workflow transitions.
T_VERIFY: Final = "verify"
T_REMOVE: Final = "remove"

#: Enum values (`PermitType`, `EnergyKind`, `GasResult`).
PERMIT_TYPES: Final = (
    "hot_work",
    "confined_space",
    "work_at_height",
    "excavation",
    "isolation",
    "general",
)
ENERGY_KINDS: Final = ("electrical", "mechanical", "process", "other")
GAS_RESULTS: Final = ("pass", "fail")

#: Fine access words (``schema/settings/access-words.yaml``), twelve.
VIEW: Final = "permits.view"
REQUEST: Final = "permits.request"
REVALIDATE: Final = "permits.revalidate"
SUSPEND: Final = "permits.suspend"
HANDBACK: Final = "permits.handback"
ISOLATION_APPLY: Final = "permits.isolation.apply"
GASTEST_RECORD: Final = "permits.gastest.record"
APPROVE: Final = "permits.approve"
ISSUE: Final = "permits.issue"
RESUME: Final = "permits.resume"
CLOSE: Final = "permits.close"
ISOLATION_VERIFY: Final = "permits.isolation.verify"
WORDS: Final = frozenset(
    {
        VIEW,
        REQUEST,
        REVALIDATE,
        SUSPEND,
        HANDBACK,
        ISOLATION_APPLY,
        GASTEST_RECORD,
        APPROVE,
        ISSUE,
        RESUME,
        CLOSE,
        ISOLATION_VERIFY,
    }
)

#: Event types.
PERMIT_REQUESTED: Final = "Permit.Requested"
PERMIT_APPROVED: Final = "Permit.Approved"
PERMIT_REJECTED: Final = "Permit.Rejected"
PERMIT_ISSUED: Final = "Permit.Issued"
PERMIT_REVALIDATED: Final = "Permit.Revalidated"
PERMIT_SUSPENDED: Final = "Permit.Suspended"
PERMIT_RESUMED: Final = "Permit.Resumed"
PERMIT_HANDED_BACK: Final = "Permit.HandedBack"
PERMIT_CLOSED: Final = "Permit.Closed"
PERMIT_CANCELLED: Final = "Permit.Cancelled"
PERMIT_LAPSED: Final = "Permit.Lapsed"
PERMIT_ISOLATION_LINKED: Final = "Permit.IsolationLinked"
PERMIT_ISOLATION_UNLINKED: Final = "Permit.IsolationUnlinked"
PERMIT_EVENTS: Final = frozenset(
    {
        PERMIT_REQUESTED,
        PERMIT_APPROVED,
        PERMIT_REJECTED,
        PERMIT_ISSUED,
        PERMIT_REVALIDATED,
        PERMIT_SUSPENDED,
        PERMIT_RESUMED,
        PERMIT_HANDED_BACK,
        PERMIT_CLOSED,
        PERMIT_CANCELLED,
        PERMIT_LAPSED,
        PERMIT_ISOLATION_LINKED,
        PERMIT_ISOLATION_UNLINKED,
    }
)
ISOLATION_APPLIED: Final = "Isolation.Applied"
ISOLATION_VERIFIED: Final = "Isolation.Verified"
ISOLATION_REMOVED: Final = "Isolation.Removed"
ISOLATION_EVENTS: Final = frozenset({ISOLATION_APPLIED, ISOLATION_VERIFIED, ISOLATION_REMOVED})
GAS_TEST_RECORDED: Final = "GasTest.Recorded"
GAS_TEST_EVENTS: Final = frozenset({GAS_TEST_RECORDED})

FEED_NONE: Final = "none"
