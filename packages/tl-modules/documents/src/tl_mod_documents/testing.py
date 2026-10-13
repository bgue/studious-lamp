"""Test support other packages share: a ledger with an object store and the document commands.

``DocumentsWorld`` wraps a ledger target, a file store and the file service, and offers one call per
thing a test does: register a document, create and issue revisions, upload a file and attach it as a
rendition, link a record to a document. Every call opens its own unit of work, like a real command.
``forge`` writes a record of this module with raw events when a test must not depend on the command
that makes it. It is not registered anywhere and never runs in production.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.service import CompleteUpload, FileResult, FileService, RegisterUpload
from tl_core.services.commands import CommandResult
from tl_core.services.links import AddLink, handle_add_link

from tl_mod_documents import registry
from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document
from tl_mod_documents.handlers.renditions import AttachRendition, handle_attach_rendition
from tl_mod_documents.handlers.revisions import (
    CreateRevision,
    IssueRevision,
    handle_create_revision,
    handle_issue_revision,
)

PROJECT = "project:P123"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": PROJECT}
PDF = b"%PDF-1.7 isometric drawing sheet"


class DocumentsWorld:
    def __init__(self, db: DbTarget, objects: Path) -> None:
        self.db = db
        self.store = FsObjectStore(objects, secret=b"s")
        self.files = FileService(self.store, secret=b"s")

    # --- reads -----------------------------------------------------------------------------

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def document(self, number: str) -> registry.DocumentRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.find_document(uow.conn(), PROJECT, number)
        assert found is not None
        return found

    def revision(self, number: str, code: str) -> registry.RevisionRow:
        doc = self.document(number)
        with open_uow(self.db, readonly=True) as uow:
            found = registry.find_revision(uow.conn(), doc.id, code)
        assert found is not None
        return found

    def revisions(self, number: str) -> list[registry.RevisionRow]:
        doc = self.document(number)
        with open_uow(self.db, readonly=True) as uow:
            return registry.revisions_of(uow.conn(), doc.id)

    # --- writes ----------------------------------------------------------------------------

    def register(self, number: str = "ISO-1234", **more: Any) -> CommandResult:
        fields: dict[str, Any] = {
            "number": number,
            "title": "Isometric, line 47-P-101",
            "doc_type": "ISO",
            "discipline": "PIP",
        }
        fields.update(more)
        with open_uow(self.db) as uow:
            return handle_register_document(uow, RegisterDocument(**{**BASE, **fields}))

    def create_revision(self, number: str = "ISO-1234", **more: Any) -> CommandResult:
        doc = self.document(number)
        with open_uow(self.db) as uow:
            return handle_create_revision(
                uow, CreateRevision(**{**BASE, "document_id": doc.id, **more})
            )

    def upload(
        self, revision_id: str, slot: str = "pdf", data: bytes = PDF, name: str = "sheet.pdf"
    ) -> FileResult:
        """Upload ``data`` into a slot of the revision through the file service."""
        content_type = "application/pdf" if slot != "native" else "application/octet-stream"
        declared = RegisterUpload(
            **BASE,
            record_id=revision_id,
            slot=slot,
            filename=name,
            content_type=content_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        with open_uow(self.db) as uow:
            ticket = self.files.register_upload(uow, declared)
        with open_uow(self.db) as uow:
            return self.files.complete_upload(
                uow, CompleteUpload(**BASE, upload_id=ticket.upload_id), io.BytesIO(data)
            )

    def attach(
        self,
        number: str,
        code: str,
        slot: str = "pdf",
        data: bytes = PDF,
        name: str = "sheet.pdf",
        **more: Any,
    ) -> CommandResult:
        """Upload a file to a revision and register it as a rendition."""
        rev = self.revision(number, code)
        uploaded = self.upload(rev.id, slot, data, name)
        with open_uow(self.db) as uow:
            return handle_attach_rendition(
                uow,
                AttachRendition(
                    **{**BASE, "revision_id": rev.id, "file_id": uploaded.file_id, **more}
                ),
            )

    def issue(self, number: str, code: str, status: str = "IFR", **more: Any) -> CommandResult:
        rev = self.revision(number, code)
        with open_uow(self.db) as uow:
            return handle_issue_revision(
                uow, IssueRevision(**{**BASE, "stream_id": rev.id, "issue_status": status, **more})
            )

    def people(self, *usernames: str) -> None:
        """Person accounts (role user, no password) for the actors a test names as reviewers."""
        from tl_core.auth import accounts

        for name in usernames:
            with open_uow(self.db) as uow:
                accounts.create_account(
                    uow,
                    username=name,
                    display_name=name.title(),
                    kind="person",
                    roles=["user"],
                    password=None,
                    by="system:test",
                )

    def issued_document(self, number: str = "ISO-1234", status: str = "IFR") -> None:
        """A registered document with revision A attached, issued."""
        self.register(number)
        self.create_revision(number)
        self.attach(number, "A")
        self.issue(number, "A", status)

    def tag(self, key: str = "47-FV-1001") -> str:
        """A bare record to link from; returns its id."""
        from tl_core.services.commands import CreateRecord
        from tl_core.services.records import handle_create_record

        with open_uow(self.db) as uow:
            made = handle_create_record(
                uow, CreateRecord(**BASE, record_type="core.Record", title=key, key=key)
            )
        return made.stream_id

    def link(self, from_id: str, number: str, pin: str | None) -> str:
        doc = self.document(number)
        with open_uow(self.db) as uow:
            made = handle_add_link(
                uow,
                AddLink(**BASE, from_id=from_id, to_id=doc.id, relation="references", pin=pin),
            )
        return made.stream_id

    def link_from(self, from_id: str, to_id: str, *, relation: str = "references") -> str:
        """A link between any two records, made as the module would (the generic rules skipped)."""
        with open_uow(self.db) as uow:
            made = handle_add_link(
                uow,
                AddLink(**BASE, from_id=from_id, to_id=to_id, relation=relation),
                by_module=True,
            )
        return made.stream_id

    def move(self, record_id: str, transition_name: str) -> None:
        """Run a workflow transition on a record of this module, as the module's commands do."""
        from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow

        with open_uow(self.db) as uow:
            version = uow.conn().execute(
                text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": record_id}
            )
            handle_transition_workflow(
                uow,
                TransitionWorkflow(
                    **BASE,
                    stream_id=record_id,
                    expected_version=int(version.scalar_one()),
                    transition=transition_name,
                ),
                by_module=True,
            )

    def link_status(self, link_id: str) -> str:
        return str(self.scalar("SELECT status FROM cur_links WHERE link_id = :i", i=link_id))


def forge(
    world: DocumentsWorld,
    stream_id: str,
    record_type: str,
    key: str,
    events: list[tuple[str, dict[str, Any]]],
    *,
    title: str = "forged",
) -> None:
    """Write a record of this module with raw events, as a handler would, without the handler.

    For tests of readers (reports, the API) that must not depend on the command that makes the
    record. ``events`` follow ``Record.Created`` in the same append.
    """
    from tl_core.ledger import NewEvent

    with open_uow(world.db) as uow:
        uow.append(
            stream_id=stream_id,
            stream_type=record_type,
            scope=PROJECT,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": record_type, "key": key, "title": title, "psets": {}},
                ),
                *[NewEvent(event_type=t, payload=p) for t, p in events],
            ],
            actor="user:forge",
            source="test",
            correlation_id="forge",
        )
