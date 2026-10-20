"""Names the correspondence module shares: record types, event types, tables, vocabularies.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
The record types and event types are documented in ``docs/modules/correspondence/README.md`` and
catalogued in ``schema/modules/correspondence/events.yaml``.
"""

from __future__ import annotations

from typing import Final

# Record types. Each is a row of cur_core_record and a row of the table named below.
CORRESPONDENCE: Final = "correspondence.Correspondence"
THREAD: Final = "correspondence.CorrespondenceThread"
CLOCK: Final = "correspondence.ResponseClock"
CLAUSE: Final = "correspondence.ContractClause"
PARTY: Final = "correspondence.Party"
#: The items of the Technical and Commercial domains: records of a type of their own because a
#: workflow belongs to a record type (brief 8). They have a row in the item table too.
TECHNICAL: Final = "correspondence.TechnicalItem"
COMMERCIAL: Final = "correspondence.CommercialItem"

RECORD_TYPES: Final = frozenset(
    {CORRESPONDENCE, THREAD, CLOCK, CLAUSE, PARTY, TECHNICAL, COMMERCIAL}
)
#: Every record type that is a row of the item table (register, clocks, threads, class).
ITEM_TYPES: Final = frozenset({CORRESPONDENCE, TECHNICAL, COMMERCIAL})

# Tables (generated from schema/modules/correspondence/*.yaml) and their flat views.
CORRESPONDENCE_TABLE: Final = "cur_correspondence_correspondence"
CLEARANCE_TABLE: Final = "cur_correspondence_clearance"
THREAD_TABLE: Final = "cur_correspondence_correspondence_thread"
CLOCK_TABLE: Final = "cur_correspondence_response_clock"
CLAUSE_TABLE: Final = "cur_correspondence_contract_clause"
PARTY_TABLE: Final = "cur_correspondence_party"
CONTACT_TABLE: Final = "cur_correspondence_contact_role"
TECHNICAL_TABLE: Final = "cur_correspondence_technical_item"
COMMERCIAL_TABLE: Final = "cur_correspondence_commercial_item"

CORRESPONDENCE_VIEW: Final = "v_correspondence_correspondence"
THREAD_VIEW: Final = "v_correspondence_correspondence_thread"
CLOCK_VIEW: Final = "v_correspondence_response_clock"
CLAUSE_VIEW: Final = "v_correspondence_contract_clause"
PARTY_VIEW: Final = "v_correspondence_party"
TECHNICAL_VIEW: Final = "v_correspondence_technical_item"
COMMERCIAL_VIEW: Final = "v_correspondence_commercial_item"

# Event types. The first event of a record follows Record.Created in the same append.
CORR_DEFINED: Final = "Correspondence.Defined"
CORR_UPDATED: Final = "Correspondence.Updated"
CORR_TRIAGED: Final = "Correspondence.Triaged"
CORR_RECLASSIFIED: Final = "Correspondence.Reclassified"
CORR_THREAD_ASSIGNED: Final = "Correspondence.ThreadAssigned"
CORR_ISSUED: Final = "Correspondence.Issued"
CORR_RESPONDED: Final = "Correspondence.Responded"
CORR_SUPERSEDED: Final = "Correspondence.Superseded"
CORR_CLASS_CHANGED: Final = "Correspondence.ConfidentialityChanged"
CORR_CLEARANCE_GRANTED: Final = "Correspondence.ClearanceGranted"
CORR_CLEARANCE_WITHDRAWN: Final = "Correspondence.ClearanceWithdrawn"

THREAD_DEFINED: Final = "CorrespondenceThread.Defined"
THREAD_ITEM_ADDED: Final = "CorrespondenceThread.ItemAdded"
THREAD_STATE_CHANGED: Final = "CorrespondenceThread.StateChanged"

CLOCK_STARTED: Final = "ResponseClock.Started"
CLOCK_PAUSED: Final = "ResponseClock.Paused"
CLOCK_RESUMED: Final = "ResponseClock.Resumed"
CLOCK_RESTARTED: Final = "ResponseClock.Restarted"
CLOCK_MET: Final = "ResponseClock.Met"
CLOCK_CANCELLED: Final = "ResponseClock.Cancelled"
CLOCK_WARNED: Final = "ResponseClock.Warned"
CLOCK_EXPIRED: Final = "ResponseClock.Expired"
CLOCK_EVENTS: Final = (
    CLOCK_STARTED,
    CLOCK_PAUSED,
    CLOCK_RESUMED,
    CLOCK_RESTARTED,
    CLOCK_MET,
    CLOCK_CANCELLED,
    CLOCK_WARNED,
    CLOCK_EXPIRED,
)

CLAUSE_DEFINED: Final = "ContractClause.Defined"
CLAUSE_RETIRED: Final = "ContractClause.Retired"

PARTY_DEFINED: Final = "Party.Defined"
PARTY_CONTACT_ADDED: Final = "Party.ContactAdded"
PARTY_CONTACT_ENDED: Final = "Party.ContactEnded"
PARTY_RETIRED: Final = "Party.Retired"

TECH_DEFINED: Final = "Technical.Defined"
TECH_UPDATED: Final = "Technical.Updated"
TECH_ANSWERED: Final = "Technical.Answered"
TECH_REVIEWED: Final = "Technical.Reviewed"
TECH_REISSUED: Final = "Technical.Reissued"
TECH_EVENTS: Final = (TECH_DEFINED, TECH_UPDATED, TECH_ANSWERED, TECH_REVIEWED, TECH_REISSUED)

COMM_DEFINED: Final = "Commercial.Defined"
COMM_UPDATED: Final = "Commercial.Updated"
COMM_ASSESSED: Final = "Commercial.Assessed"
COMM_EVENTS: Final = (COMM_DEFINED, COMM_UPDATED, COMM_ASSESSED)

# Workflow of a correspondence item (schema/fixtures/workflows/correspondence-correspondence.yaml).
# A record that never moved has no status in cur_core_record: it is in the initial state, Draft.
WORKFLOW_ID: Final = "correspondence.correspondence"
ST_DRAFT: Final = "Draft"
ST_RECEIVED: Final = "Received"
ST_TRIAGED: Final = "Triaged"
ST_ISSUED: Final = "Issued"
ST_RESPONDED: Final = "Responded"
ST_CLOSED: Final = "Closed"
ST_VOID: Final = "Void"
STATES: Final = (ST_DRAFT, ST_RECEIVED, ST_TRIAGED, ST_ISSUED, ST_RESPONDED, ST_CLOSED, ST_VOID)

# Workflow of a Technical item (schema/fixtures/workflows/correspondence-technical.yaml).
TECHNICAL_WORKFLOW_ID: Final = "correspondence.technical"
ST_INTERNAL_REVIEW: Final = "Internal review"
ST_AWAITING_RESPONSE: Final = "Awaiting response"
ST_ANSWERED: Final = "Answered"
ST_ACCEPTED: Final = "Accepted"
ST_REJECTED: Final = "Rejected"
TECHNICAL_STATES: Final = (
    ST_DRAFT,
    ST_INTERNAL_REVIEW,
    ST_ISSUED,
    ST_AWAITING_RESPONSE,
    ST_ANSWERED,
    ST_ACCEPTED,
    ST_REJECTED,
    ST_CLOSED,
    ST_VOID,
)

# Workflow of a Commercial item (schema/fixtures/workflows/correspondence-commercial.yaml).
COMMERCIAL_WORKFLOW_ID: Final = "correspondence.commercial"
ST_COMMERCIAL_REVIEW: Final = "Commercial review"
ST_PM_APPROVAL: Final = "PM approval"
ST_AWAITING_ASSESSMENT: Final = "Awaiting assessment"
ST_AGREED: Final = "Agreed"
ST_DISPUTED: Final = "Disputed"
ST_PARTLY_AGREED: Final = "Partially agreed"
ST_ESCALATED: Final = "Escalated"
COMMERCIAL_STATES: Final = (
    ST_DRAFT,
    ST_COMMERCIAL_REVIEW,
    ST_PM_APPROVAL,
    ST_ISSUED,
    ST_AWAITING_ASSESSMENT,
    ST_AGREED,
    ST_DISPUTED,
    ST_PARTLY_AGREED,
    ST_CLOSED,
    ST_ESCALATED,
    ST_VOID,
)

# Vocabularies.
YES_NO_UNKNOWN: Final = ("yes", "no", "unknown")
REVIEW_DECISIONS: Final = ("accepted", "rejected")
ASSESSMENT_STATUSES: Final = ("agreed", "disputed", "partially_agreed")
DIRECTIONS: Final = ("in", "out", "internal")
MEDIA: Final = ("letter", "email", "portal", "minutes", "other")
RECEIVED_VIA: Final = ("upload", "email", "manual")
PARTY_ROLES: Final = (
    "client",
    "engineer",
    "contractor",
    "subcontractor",
    "supplier",
    "authority",
    "internal",
    "other",
)
SERVICE_METHODS: Final = ("email", "letter", "portal", "hand")
DAY_TYPES: Final = ("calendar", "working")
CLOCK_KINDS: Final = ("response_from_them", "response_from_us", "time_bar")
CLOCK_TRIGGERS: Final = ("receipt", "issue", "awareness")
#: How a clock came to start (the ``trigger`` of ``ResponseClock.Started``).
START_TRIGGERS: Final = ("receipt", "issue", "triage", "manual", "awareness")
CLOCK_RUNNING: Final = "running"
CLOCK_PAUSED_STATE: Final = "paused"
CLOCK_MET_STATE: Final = "met"
CLOCK_CANCELLED_STATE: Final = "cancelled"
CLOCK_EXPIRED_STATE: Final = "expired"
CLOCK_STATES: Final = (
    CLOCK_RUNNING,
    CLOCK_PAUSED_STATE,
    CLOCK_MET_STATE,
    CLOCK_CANCELLED_STATE,
    CLOCK_EXPIRED_STATE,
)
THREAD_OPEN: Final = "open"
THREAD_CLOSED: Final = "closed"
MATCHED_BY: Final = ("header", "reference_key", "subject", "manual")

# Domains of this increment. A domain is defined by a file (tl_mod_correspondence.domains).
DOMAIN_GENERAL: Final = "general"
DOMAIN_DOCUMENT_CONTROL: Final = "document_control"
DOMAIN_TECHNICAL: Final = "technical"
DOMAIN_COMMERCIAL: Final = "commercial"

# File slots of a correspondence item (schema/fixtures/files/correspondence-correspondence.yaml):
# ``original`` and ``attachment`` are what a person uploads; ``rendition`` and ``message`` are
# written by the module only.
SLOT_ORIGINAL: Final = "original"
SLOT_ATTACHMENT: Final = "attachment"
SLOT_RENDITION: Final = "rendition"
SLOT_MESSAGE: Final = "message"

#: Shown on every command field that sets a class (the OpenAPI text, the CLI help).
LIMITS_NOTE_CLASSES: Final = (
    "internal: any signed-in person and agent. restricted: a document controller or admin, no "
    "agent. privileged: only the accounts named on the item. Enforced (ADR-0016)."
)
