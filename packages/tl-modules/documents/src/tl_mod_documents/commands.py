"""The commands the documents module offers to the API (brief 11.1, 25.2; P1-I2).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:

* ``controller``: an admin or a document controller (action ``control.command.<Name>``);
* ``admin``: only an admin (action ``admin.command.<Name>``); none of this module's commands;
* ``user``: any signed-in person.

The **controlling acts** belong to the document controller role (ADR-0013, which replaced the
interim admin-only rule of ADR-0011); an admin may run them too: issuing a revision, superseding a
revision or a document, voiding a document, issuing a transmittal, registering or replacing a
signed copy, setting the confidentiality class, and the two corrections of a review. Everything
that prepares work stays open to any signed-in person: registering, revising, attaching in draft,
opening a review, recording one's own answer, linking and re-pinning. An agent never changes a
record: its calls are proposals a person accepts, and a command is closed to agents until
``tl_core.auth.provider`` lists it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_documents.derivation.derived import (
    CancelJob,
    OpenDerivedDocument,
    StartExtraction,
    ValidateDerived,
    VoidDerivedDocument,
    handle_cancel_job,
    handle_open_derived_document,
    handle_start_extraction,
    handle_validate_derived,
    handle_void_derived_document,
)
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    PublishDerivedDocuments,
    PublishDerivedTags,
    handle_compensate_publication,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
)
from tl_mod_documents.derivation.schemas import (
    RegisterDocumentSchema,
    RetireDocumentSchema,
    handle_register_document_schema,
    handle_retire_document_schema,
)
from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    SetDocumentConfidentiality,
    SupersedeDocument,
    UpdateDocument,
    VoidDocument,
    handle_register_document,
    handle_set_document_confidentiality,
    handle_supersede_document,
    handle_update_document,
    handle_void_document,
)
from tl_mod_documents.handlers.renditions import (
    AttachRendition,
    RegisterSignedRendition,
    ReplaceSignedRendition,
    handle_attach_rendition,
    handle_register_signed_rendition,
    handle_replace_signed_rendition,
)
from tl_mod_documents.handlers.reviews import (
    CloseReviewCycle,
    OpenReviewCycle,
    OverrideReviewOutcome,
    RecordReviewOutcome,
    RecordReviewOutcomeOnBehalf,
    handle_close_review_cycle,
    handle_open_review_cycle,
    handle_override_review_outcome,
    handle_record_review_outcome,
    handle_record_review_outcome_on_behalf,
)
from tl_mod_documents.handlers.revisions import (
    CreateRevision,
    IssueRevision,
    SupersedeRevision,
    VoidRevision,
    handle_create_revision,
    handle_issue_revision,
    handle_supersede_revision,
    handle_void_revision,
)
from tl_mod_documents.handlers.transmittals import (
    CloseTransmittal,
    CreateTransmittal,
    IssueTransmittal,
    RecordTransmittalResponse,
    VoidTransmittal,
    handle_close_transmittal,
    handle_create_transmittal,
    handle_issue_transmittal,
    handle_record_transmittal_response,
    handle_void_transmittal,
)
from tl_mod_documents.resolver import (
    LinkToDocument,
    RepinDocumentLink,
    handle_link_to_document,
    handle_repin_document_link,
)

Access = Literal["admin", "controller", "user"]  # a typo is a type error, not an open door


@dataclass(frozen=True)
class ApiCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: Access


API_COMMANDS: tuple[ApiCommand, ...] = (
    ApiCommand(RegisterDocument, handle_register_document, "user"),
    ApiCommand(UpdateDocument, handle_update_document, "user"),
    ApiCommand(SetDocumentConfidentiality, handle_set_document_confidentiality, "controller"),
    ApiCommand(SupersedeDocument, handle_supersede_document, "controller"),
    ApiCommand(VoidDocument, handle_void_document, "controller"),
    ApiCommand(CreateRevision, handle_create_revision, "user"),
    ApiCommand(IssueRevision, handle_issue_revision, "controller"),
    ApiCommand(SupersedeRevision, handle_supersede_revision, "controller"),
    ApiCommand(VoidRevision, handle_void_revision, "user"),
    ApiCommand(AttachRendition, handle_attach_rendition, "user"),
    ApiCommand(RegisterSignedRendition, handle_register_signed_rendition, "controller"),
    ApiCommand(ReplaceSignedRendition, handle_replace_signed_rendition, "controller"),
    ApiCommand(LinkToDocument, handle_link_to_document, "user"),
    ApiCommand(RepinDocumentLink, handle_repin_document_link, "user"),
    ApiCommand(CreateTransmittal, handle_create_transmittal, "user"),
    ApiCommand(IssueTransmittal, handle_issue_transmittal, "controller"),
    ApiCommand(RecordTransmittalResponse, handle_record_transmittal_response, "user"),
    ApiCommand(CloseTransmittal, handle_close_transmittal, "user"),
    ApiCommand(VoidTransmittal, handle_void_transmittal, "user"),
    ApiCommand(OpenReviewCycle, handle_open_review_cycle, "user"),
    ApiCommand(RecordReviewOutcome, handle_record_review_outcome, "user"),
    ApiCommand(CloseReviewCycle, handle_close_review_cycle, "user"),
    ApiCommand(RecordReviewOutcomeOnBehalf, handle_record_review_outcome_on_behalf, "controller"),
    ApiCommand(OverrideReviewOutcome, handle_override_review_outcome, "controller"),
    # the derivation pipeline (P1-I3, ADR-0014). Document schemas are registry data: the admin's.
    # Running work (opening, extracting, checking again, cancelling, voiding) is any signed-in
    # person's. Publishing needs the access of the bulk import of the target type (tags: the
    # admin's, as `tl tag import --apply`; documents: the controller's, as `tl doc import
    # --apply`); rolling a publication back is the admin's.
    ApiCommand(RegisterDocumentSchema, handle_register_document_schema, "admin"),
    ApiCommand(RetireDocumentSchema, handle_retire_document_schema, "admin"),
    ApiCommand(OpenDerivedDocument, handle_open_derived_document, "user"),
    ApiCommand(StartExtraction, handle_start_extraction, "user"),
    ApiCommand(ValidateDerived, handle_validate_derived, "user"),
    ApiCommand(CancelJob, handle_cancel_job, "user"),
    ApiCommand(VoidDerivedDocument, handle_void_derived_document, "user"),
    ApiCommand(PublishDerivedTags, handle_publish_derived_tags, "admin"),
    ApiCommand(PublishDerivedDocuments, handle_publish_derived_documents, "controller"),
    ApiCommand(CompensatePublication, handle_compensate_publication, "admin"),
)
