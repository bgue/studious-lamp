"""The commands the documents module offers to the API (brief 11.1, 25.2; P1-I2).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:

* ``admin``: only an admin (action ``admin.command.<Name>``);
* ``user``: any signed-in person.

Document control has no role of its own in Phase 1 (ADR-0008 has two roles). Until one exists
(Entra groups, later) the **controlling acts** are the admin's (ADR-0011): issuing a revision,
superseding a revision or a document, voiding a document, issuing a transmittal, registering or
replacing a signed copy, setting the confidentiality class, and the two corrections of a review.
Everything that prepares work stays open to any signed-in person: registering, revising,
attaching in draft, opening a review, recording one's own answer, linking and re-pinning. An agent
never changes a record: its calls are proposals a person accepts, and a command is closed to
agents until ``tl_core.auth.provider`` lists it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

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

Access = Literal["admin", "user"]  # a typo is a type error, not an open door


@dataclass(frozen=True)
class ApiCommand:
    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: Access


API_COMMANDS: tuple[ApiCommand, ...] = (
    ApiCommand(RegisterDocument, handle_register_document, "user"),
    ApiCommand(UpdateDocument, handle_update_document, "user"),
    ApiCommand(SetDocumentConfidentiality, handle_set_document_confidentiality, "admin"),
    ApiCommand(SupersedeDocument, handle_supersede_document, "admin"),
    ApiCommand(VoidDocument, handle_void_document, "admin"),
    ApiCommand(CreateRevision, handle_create_revision, "user"),
    ApiCommand(IssueRevision, handle_issue_revision, "admin"),
    ApiCommand(SupersedeRevision, handle_supersede_revision, "admin"),
    ApiCommand(VoidRevision, handle_void_revision, "user"),
    ApiCommand(AttachRendition, handle_attach_rendition, "user"),
    ApiCommand(RegisterSignedRendition, handle_register_signed_rendition, "admin"),
    ApiCommand(ReplaceSignedRendition, handle_replace_signed_rendition, "admin"),
    ApiCommand(LinkToDocument, handle_link_to_document, "user"),
    ApiCommand(RepinDocumentLink, handle_repin_document_link, "user"),
    ApiCommand(CreateTransmittal, handle_create_transmittal, "user"),
    ApiCommand(IssueTransmittal, handle_issue_transmittal, "admin"),
    ApiCommand(RecordTransmittalResponse, handle_record_transmittal_response, "user"),
    ApiCommand(CloseTransmittal, handle_close_transmittal, "user"),
    ApiCommand(VoidTransmittal, handle_void_transmittal, "user"),
    ApiCommand(OpenReviewCycle, handle_open_review_cycle, "user"),
    ApiCommand(RecordReviewOutcome, handle_record_review_outcome, "user"),
    ApiCommand(CloseReviewCycle, handle_close_review_cycle, "user"),
    ApiCommand(RecordReviewOutcomeOnBehalf, handle_record_review_outcome_on_behalf, "admin"),
    ApiCommand(OverrideReviewOutcome, handle_override_review_outcome, "admin"),
)
