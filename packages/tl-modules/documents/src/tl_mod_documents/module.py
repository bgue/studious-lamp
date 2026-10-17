"""What the documents module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``documents`` in this package's ``pyproject.toml`` names
``spec``. The platform calls it once per process.
"""

from __future__ import annotations

from tl_core.modules import ChildSource, ConfidentialSource, ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector

from tl_mod_documents import MODULE
from tl_mod_documents.derivation.derived import StartExtraction, handle_start_extraction
from tl_mod_documents.derivation.publish import (
    PublishDerivedDocuments,
    PublishDerivedTags,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
)
from tl_mod_documents.guards import derived_upload, revision_upload, transmittal_draft_only
from tl_mod_documents.names import (
    DERIVED_DOCUMENT,
    DERIVED_DOCUMENT_TABLE,
    DOCUMENT,
    DOCUMENT_SCHEMA,
    DOCUMENT_TABLE,
    PROCESSING_JOB,
    PROCESSING_JOB_TABLE,
    RECORD_TYPES,
    RENDITION,
    RENDITION_TABLE,
    REVIEW_CYCLE,
    REVIEW_CYCLE_TABLE,
    REVISION,
    REVISION_TABLE,
    TRANSMITTAL,
)
from tl_mod_documents.projectors import (
    DerivedDocumentProjector,
    DocumentProjector,
    DocumentSchemaProjector,
    ProcessingJobProjector,
    RenditionProjector,
    ReviewCycleProjector,
    RevisionProjector,
    TransmittalProjector,
)

#: The generic commands a person may run on each record type (ADR-0010 addendum). Everything else
#: changes through the module's own commands, which check the module's rules:
#:
#: * a document takes property-set values (custom fields) and links;
#: * a revision takes links and file uploads into its four slots (an upload becomes a controlled
#:   rendition only when ``AttachRendition`` registers it);
#: * a transmittal takes links and attachments (a cover letter);
#: * a rendition and a review cycle allow none: they change only through ``AttachRendition`` and
#:   the review commands.
#:
#: The title, the register fields, the workflow state and a void are never generic.
#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract) is
#: allowed too; a link a rule of this module wrote is kept by the module (core refuses a generic
#: FlagLink or RetractLink on it).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
DOCUMENT_GENERIC_COMMANDS = frozenset({"SetPsetValues", "AddLink", "SuggestLink"}) | LINK_LIFE
REVISION_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
TRANSMITTAL_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE
#: The derivation records (ADR-0014): a schema takes links only; a derived document takes links and
#: the person's file in the slot ``content`` (``derived_upload`` guards the state and the slot); a
#: processing job takes nothing. Their state moves only through the module's own commands.
SCHEMA_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink"}) | LINK_LIFE
DERIVED_GENERIC_COMMANDS = frozenset({"AddLink", "SuggestLink", "AttachFile"}) | LINK_LIFE


#: What an agent may propose (ADR-0014 section 8). Accepting runs the command as the accepting
#: person, who needs the access written here: starting an extraction is any signed-in person's,
#: publishing into tags the admin's (as `tl tag import --apply`), into documents the document
#: controller's (as `tl doc import --apply`). `tl_core.services.proposals` refuses an accept by
#: anyone without it and a command with no access at all.
PROPOSABLE = (
    ProposableCommand("start_extraction", StartExtraction, handle_start_extraction, "user"),
    ProposableCommand(
        "propose_import_tags", PublishDerivedTags, handle_publish_derived_tags, "admin"
    ),
    ProposableCommand(
        "propose_import_documents",
        PublishDerivedDocuments,
        handle_publish_derived_documents,
        "controller",
    ),
)


#: The class of a document is its `confidentiality` column (ADR-0016); NULL is `internal`. A
#: revision, rendition, review, derived document and processing job are readable only when their
#: document is (a processing job hangs on its derived document, which hangs on a document).
CONFIDENTIAL = (
    ConfidentialSource(
        record_types=frozenset({DOCUMENT}),
        table=DOCUMENT_TABLE,
        id_column="id",
        class_column="confidentiality",
        null_class="internal",
        children=(
            ChildSource(frozenset({REVISION}), REVISION_TABLE, "id", "document_id"),
            ChildSource(frozenset({RENDITION}), RENDITION_TABLE, "id", "document_id"),
            ChildSource(frozenset({REVIEW_CYCLE}), REVIEW_CYCLE_TABLE, "id", "document_id"),
            ChildSource(
                frozenset({DERIVED_DOCUMENT}), DERIVED_DOCUMENT_TABLE, "id", "source_document_id"
            ),
            ChildSource(
                frozenset({PROCESSING_JOB}),
                PROCESSING_JOB_TABLE,
                "id",
                "derived_id",
                hop=(DERIVED_DOCUMENT_TABLE, "id", "source_document_id"),
            ),
        ),
    ),
)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [
        DocumentProjector(),
        RevisionProjector(),
        RenditionProjector(),
        TransmittalProjector(),
        ReviewCycleProjector(),
        DocumentSchemaProjector(),
        DerivedDocumentProjector(),
        ProcessingJobProjector(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={
            DOCUMENT: DOCUMENT_GENERIC_COMMANDS,
            REVISION: REVISION_GENERIC_COMMANDS,
            TRANSMITTAL: TRANSMITTAL_GENERIC_COMMANDS,
            DOCUMENT_SCHEMA: SCHEMA_GENERIC_COMMANDS,
            DERIVED_DOCUMENT: DERIVED_GENERIC_COMMANDS,
        },
        generic_guards={
            (REVISION, "AttachFile"): revision_upload,
            (TRANSMITTAL, "AttachFile"): transmittal_draft_only,
            (TRANSMITTAL, "AddLink"): transmittal_draft_only,
            (TRANSMITTAL, "SuggestLink"): transmittal_draft_only,
            (TRANSMITTAL, "FlagLink"): transmittal_draft_only,
            (TRANSMITTAL, "RetractLink"): transmittal_draft_only,
            (DERIVED_DOCUMENT, "AttachFile"): derived_upload,
        },
        proposable=PROPOSABLE,
        confidential=CONFIDENTIAL,
    )
