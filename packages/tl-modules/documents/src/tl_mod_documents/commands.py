"""The commands the documents module offers to the API (brief 11.1, 25.2; P1-I2).

The API builds one ``POST /commands/<Name>`` route per row. ``access`` says who may call it:

* ``admin``: only an admin (action ``admin.command.<Name>``);
* ``user``: any signed-in person.

Document control has no role of its own in Phase 1 (ADR-0008 has two roles), so registering,
revising, issuing and transmitting are open to every signed-in person; voiding a whole document is
the one admin command. An agent never changes a record: its calls are proposals a person accepts,
and a command is closed to agents until ``tl_core.auth.provider`` lists it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    SupersedeDocument,
    UpdateDocument,
    VoidDocument,
    handle_register_document,
    handle_supersede_document,
    handle_update_document,
    handle_void_document,
)
from tl_mod_documents.handlers.renditions import AttachRendition, handle_attach_rendition
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
    ApiCommand(SupersedeDocument, handle_supersede_document, "user"),
    ApiCommand(VoidDocument, handle_void_document, "admin"),
    ApiCommand(CreateRevision, handle_create_revision, "user"),
    ApiCommand(IssueRevision, handle_issue_revision, "user"),
    ApiCommand(SupersedeRevision, handle_supersede_revision, "user"),
    ApiCommand(VoidRevision, handle_void_revision, "user"),
    ApiCommand(AttachRendition, handle_attach_rendition, "user"),
    ApiCommand(LinkToDocument, handle_link_to_document, "user"),
    ApiCommand(RepinDocumentLink, handle_repin_document_link, "user"),
)
