"""Names the documents module shares: record types, event types, table and view names, vocabularies.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
The record types and event types are documented in ``docs/modules/documents/README.md`` and
catalogued in ``schema/modules/documents/events.yaml``.
"""

from __future__ import annotations

from typing import Final

# Record types. Each is a row of cur_core_record and a row of the table named below.
DOCUMENT: Final = "documents.Document"
REVISION: Final = "documents.Revision"
RENDITION: Final = "documents.Rendition"
TRANSMITTAL: Final = "documents.Transmittal"
REVIEW_CYCLE: Final = "documents.ReviewCycle"

RECORD_TYPES: Final = frozenset({DOCUMENT, REVISION, RENDITION, TRANSMITTAL, REVIEW_CYCLE})

# Tables (generated from schema/modules/documents/*.yaml) and their flat views.
DOCUMENT_TABLE: Final = "cur_documents_document"
REVISION_TABLE: Final = "cur_documents_revision"
RENDITION_TABLE: Final = "cur_documents_rendition"
TRANSMITTAL_TABLE: Final = "cur_documents_transmittal"
TRANSMITTAL_ITEM_TABLE: Final = "cur_documents_transmittal_item"
REVIEW_CYCLE_TABLE: Final = "cur_documents_review_cycle"
REVIEWER_TABLE: Final = "cur_documents_reviewer"

DOCUMENT_VIEW: Final = "v_documents_document"
REVISION_VIEW: Final = "v_documents_revision"
RENDITION_VIEW: Final = "v_documents_rendition"
TRANSMITTAL_VIEW: Final = "v_documents_transmittal"
REVIEW_CYCLE_VIEW: Final = "v_documents_review_cycle"

# Event types. The *Defined event follows Record.Created in the same append.
DOCUMENT_DEFINED: Final = "Document.Defined"
DOCUMENT_UPDATED: Final = "Document.Updated"
DOCUMENT_CURRENT_CHANGED: Final = "Document.CurrentRevisionChanged"
DOCUMENT_SUPERSEDED: Final = "Document.Superseded"
REVISION_DEFINED: Final = "Revision.Defined"
REVISION_ISSUED: Final = "Revision.Issued"
REVISION_SUPERSEDED: Final = "Revision.Superseded"
RENDITION_DEFINED: Final = "Rendition.Defined"
RENDITION_SUPERSEDED: Final = "Rendition.Superseded"
TRANSMITTAL_DEFINED: Final = "Transmittal.Defined"
TRANSMITTAL_ISSUED: Final = "Transmittal.Issued"
TRANSMITTAL_RESPONSE: Final = "Transmittal.ResponseRecorded"
REVIEW_DEFINED: Final = "ReviewCycle.Defined"
REVIEW_OUTCOME: Final = "ReviewCycle.OutcomeRecorded"
REVIEW_CLOSED: Final = "ReviewCycle.Closed"

# Workflow states (schema/fixtures/workflows/documents-*.yaml). A record that never moved has no
# status in cur_core_record: it is in the workflow's initial state.
DOC_DRAFT: Final = "Draft"
DOC_REGISTERED: Final = "Registered"
DOC_IN_REVIEW: Final = "In Review"
DOC_ISSUED: Final = "Issued"
DOC_SUPERSEDED: Final = "Superseded"
DOC_VOID: Final = "Void"
#: Revision states reuse the document words: Draft, In Review, Issued, Superseded, Void.
#: Transmittal states.
TR_DRAFT: Final = "Draft"
TR_ISSUED: Final = "Issued"
TR_ACKNOWLEDGED: Final = "Acknowledged"
TR_CLOSED: Final = "Closed"
TR_VOID: Final = "Void"

#: Rendition kinds, which are also the file slots of a revision.
RENDITION_KINDS: Final = ("native", "pdf", "markup", "signed")
#: Kinds that may still be added to a revision after it was issued.
POST_ISSUE_KINDS: Final = ("markup", "signed")
#: Kinds that satisfy "the revision has a copy to issue".
ISSUE_KINDS: Final = ("native", "pdf")

TRANSMITTAL_DIRECTIONS: Final = ("outgoing", "incoming")
TRANSMITTAL_PURPOSES: Final = (
    "for_review",
    "for_information",
    "for_approval",
    "for_construction",
    "as_built",
    "for_record",
)
RESPONSE_CODES: Final = ("approved", "approved_with_comments", "rejected", "noted")
REVIEW_OUTCOMES: Final = ("approved", "approved_with_comments", "rejected", "withdrawn")

#: The company code lists the module reads from the engineering registry.
DOCUMENT_TYPE_LIST: Final = "DocumentType"
DISCIPLINE_LIST: Final = "Discipline"

#: Relation of a link whose target is a document (brief 7.1).
PIN_RELATION: Final = "references"
