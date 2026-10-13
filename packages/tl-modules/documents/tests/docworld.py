"""Shared support of the documents module tests (the name is unique on purpose: L-P1-I0A-1).

``World`` wraps a ledger target, a file store and the file service, and offers one call per thing a
test does: register a document, create and issue revisions, upload a file and attach it as a
rendition, link a tag to a document. Every call opens its own unit of work, like a real command.
``install`` creates every table of every default projector on an engine.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.service import CompleteUpload, FileResult, FileService, RegisterUpload
from tl_core.ledger import Event
from tl_core.projection.defaults import default_registry
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

FIXTURES = Path(__file__).resolve().parents[4] / "schema" / "fixtures"
PROJECT = "project:P123"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": PROJECT}
PDF = b"%PDF-1.7 isometric drawing sheet"
BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def install(engine: Engine, dialect: str) -> None:
    """Create every table (and view) of every default projector."""
    with engine.begin() as conn:
        for projector in default_registry().all():
            for statement in projector.ddl(dialect):
                conn.exec_driver_sql(statement)


class World:
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

    def link_status(self, link_id: str) -> str:
        return str(self.scalar("SELECT status FROM cur_links WHERE link_id = :i", i=link_id))


class Events:
    """Numbers events in one global sequence and per-stream versions, like the ledger."""

    def __init__(self) -> None:
        self.seq = 0
        self.versions: dict[str, int] = {}

    def make(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        stream_id: str,
        stream_type: str,
        scope: str = PROJECT,
    ) -> Event:
        self.seq += 1
        version = self.versions.get(stream_id, 0) + 1
        self.versions[stream_id] = version
        at = BASE_TIME + timedelta(minutes=self.seq)
        return Event(
            event_type=event_type,
            payload=payload,
            seq=self.seq,
            event_id=f"E{self.seq:06d}",
            stream_id=stream_id,
            stream_type=stream_type,
            stream_version=version,
            scope=scope,
            actor="user:test",
            recorded_at=at,
            effective_at=at,
            correlation_id="c",
            causation_id=None,
            source="test",
            prev_hash=None,
            hash=f"h{self.seq}",
        )

    def created(
        self, stream_id: str, record_type: str, key: str, *, title: str = "t", scope: str = PROJECT
    ) -> Event:
        """``Record.Created``: the envelope event every module record starts with."""
        return self.make(
            "Record.Created",
            {"record_type": record_type, "key": key, "title": title, "psets": {}},
            stream_id=stream_id,
            stream_type=record_type,
            scope=scope,
        )


def apply(engine: Engine, *events: Event) -> None:
    """Run the registered projectors over ``events`` in one transaction."""
    registry_ = default_registry()
    with engine.begin() as conn:
        for event in events:
            for projector in registry_.for_event(event.event_type):
                projector.apply(conn, event)


def table_rows(engine: Engine, table: str, order: str = "id") -> list[dict[str, Any]]:
    """Every row of ``table`` (a name from the module, never user input), ordered by ``order``."""
    with engine.connect() as conn:
        found = conn.execute(text(f"SELECT * FROM {table} ORDER BY {order}")).mappings()
        return [dict(r) for r in found]


def as_json(value: Any) -> Any:
    """A JSON column as Python: SQLite and Postgres both hand back JSON text through the adapter."""
    return json.loads(value) if isinstance(value, str) else value
