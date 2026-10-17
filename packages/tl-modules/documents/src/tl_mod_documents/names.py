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

# Derivation pipeline (P1-I3, ADR-0014).
DOCUMENT_SCHEMA: Final = "documents.DocumentSchema"
DERIVED_DOCUMENT: Final = "documents.DerivedDocument"
PROCESSING_JOB: Final = "documents.ProcessingJob"

RECORD_TYPES: Final = frozenset(
    {
        DOCUMENT,
        REVISION,
        RENDITION,
        TRANSMITTAL,
        REVIEW_CYCLE,
        DOCUMENT_SCHEMA,
        DERIVED_DOCUMENT,
        PROCESSING_JOB,
    }
)

# Tables (generated from schema/modules/documents/*.yaml) and their flat views.
DOCUMENT_TABLE: Final = "cur_documents_document"
REVISION_TABLE: Final = "cur_documents_revision"
RENDITION_TABLE: Final = "cur_documents_rendition"
TRANSMITTAL_TABLE: Final = "cur_documents_transmittal"
TRANSMITTAL_ITEM_TABLE: Final = "cur_documents_transmittal_item"
REVIEW_CYCLE_TABLE: Final = "cur_documents_review_cycle"
REVIEWER_TABLE: Final = "cur_documents_reviewer"

DOCUMENT_SCHEMA_TABLE: Final = "cur_documents_document_schema"
DERIVED_DOCUMENT_TABLE: Final = "cur_documents_derived_document"
DERIVED_CONTENT_TABLE: Final = "cur_documents_derived_content"
PROCESSING_JOB_TABLE: Final = "cur_documents_processing_job"

DOCUMENT_SCHEMA_VIEW: Final = "v_documents_document_schema"
DERIVED_DOCUMENT_VIEW: Final = "v_documents_derived_document"
PROCESSING_JOB_VIEW: Final = "v_documents_processing_job"

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
DOCUMENT_SCHEMA_DEFINED: Final = "DocumentSchema.Defined"
DOCUMENT_SCHEMA_RETIRED: Final = "DocumentSchema.Retired"
DERIVED_DEFINED: Final = "DerivedDocument.Defined"
DERIVED_CONTENT_RECORDED: Final = "DerivedDocument.ContentRecorded"
DERIVED_VALIDATED: Final = "DerivedDocument.Validated"
DERIVED_PUBLISHED: Final = "DerivedDocument.Published"
DERIVED_COMPENSATED: Final = "DerivedDocument.PublicationCompensated"
JOB_DEFINED: Final = "ProcessingJob.Defined"
JOB_STARTED: Final = "ProcessingJob.Started"
JOB_SUCCEEDED: Final = "ProcessingJob.Succeeded"
JOB_FAILED: Final = "ProcessingJob.Failed"
JOB_CANCELLED: Final = "ProcessingJob.Cancelled"

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
# Derived document states (schema/fixtures/workflows/documents-derived-document.yaml).
DD_PENDING: Final = "Pending"
DD_PROCESSING: Final = "Processing"
DD_INVALID: Final = "Invalid"
DD_VALID: Final = "Valid"
DD_PUBLISHED: Final = "Published"
DD_VOID: Final = "Void"
#: Processing job states (a column; the job record has no workflow).
JOB_QUEUED: Final = "queued"
JOB_RUNNING: Final = "running"
JOB_SUCCEEDED_STATE: Final = "succeeded"
JOB_FAILED_STATE: Final = "failed"
JOB_CANCELLED_STATE: Final = "cancelled"
#: Job kinds.
JOB_KIND_EXTRACT: Final = "extract"
JOB_KIND_VALIDATE: Final = "validate"
JOB_KINDS: Final = (JOB_KIND_EXTRACT, JOB_KIND_VALIDATE)
#: What a document schema publishes its valid rows as.
TARGET_TAGS: Final = "tags"
TARGET_DOCUMENTS: Final = "documents"
TARGET_KINDS: Final = (TARGET_TAGS, TARGET_DOCUMENTS)
#: How a derived document got its data.
METHODS: Final = ("manual", "automated", "hybrid")
#: File slots of a derived document: ``content`` is what a person attaches; ``extracted`` and
#: ``report`` are written by the module only.
SLOT_CONTENT: Final = "content"
SLOT_EXTRACTED: Final = "extracted"
SLOT_REPORT: Final = "report"
#: Provenance written to every record a publication creates: ``src.doc.<number>@<revision>``.
PROVENANCE_PSET: Final = "provenance"
PROVENANCE_PROPERTY: Final = "source"
#: Relation of the link from a published record to the derived document it came from.
DERIVED_FROM_RELATION: Final = "derived_from"

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
