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
from tl_mod_documents.handlers.renditions import (
    AttachRendition,
    RegisterSignedRendition,
    handle_attach_rendition,
    handle_register_signed_rendition,
)
from tl_mod_documents.handlers.revisions import (
    CreateRevision,
    IssueRevision,
    handle_create_revision,
    handle_issue_revision,
)

PROJECT = "project:P123"
EXTRACTOR_FACTORY = "tl_core.derivation.testing:make_extractors"

#: A small document schema and its publish mapping, for the pipeline tests.
INDEX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tag", "type"],
    "properties": {
        "tag": {"type": "string", "pattern": "^[0-9]{2}-[A-Z]{2,3}-[0-9]{3,5}$"},
        "service": {"type": "string"},
        "type": {"type": "string", "enum": ["CV", "HV", "PSV"]},
        "size_in": {"type": "number", "minimum": 0.25},
    },
}
INDEX_MAPPING: dict[str, Any] = {
    "target": "tags",
    "key_column": "tag",
    "columns": [
        {"column": "tag", "to": "number"},
        {"column": "service", "to": "service"},
        {
            "column": "type",
            "to": "class",
            "values": {"CV": "ControlValve", "HV": "ManualValve", "PSV": "SafetyValve"},
        },
        {"column": "size_in", "to": "psets.valve_data.size_in"},
    ],
}


def index_csv(rows: list[tuple[str, str, str, str]]) -> bytes:
    """A CSV of the instrument-index schema: (tag, service, type, size_in) per row."""
    lines = ["tag,service,type,size_in", *(",".join(row) for row in rows)]
    return ("\n".join(lines) + "\n").encode("utf-8")


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
        """Upload a file to a revision and register it as a rendition.

        The first signed copy goes through ``RegisterSignedRendition``, as an admin would run it.
        """
        rev = self.revision(number, code)
        uploaded = self.upload(rev.id, slot, data, name)
        if slot == "signed":
            with open_uow(self.db) as uow:
                return handle_register_signed_rendition(
                    uow,
                    RegisterSignedRendition(
                        **{**BASE, "revision_id": rev.id, "file_id": uploaded.file_id, **more}
                    ),
                )
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

    def people(self, *usernames: str, password: str | None = None) -> None:
        """Person accounts (role user) for the actors a test names as reviewers.

        Without ``password`` the accounts cannot sign in; give one when the test runs commands that
        sign in as them (the CLI tests on Postgres).
        """
        from tl_core.auth import accounts
        from tl_core.auth.password import prepare_password

        for name in usernames:
            with open_uow(self.db) as uow:
                accounts.create_account(
                    uow,
                    username=name,
                    display_name=name.title(),
                    kind="person",
                    roles=["user"],
                    password=None
                    if password is None
                    else prepare_password(password, username=name),
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

    # --- the derivation pipeline (P1-I3) -----------------------------------------------------

    def register_schema(
        self,
        *,
        code: str = "instrument-index",
        semver: str = "1.0.0",
        scope: str = "company",
        **more: Any,
    ) -> CommandResult:
        """Register a document schema version as an admin would (the default: ``INDEX_SCHEMA``)."""
        from tl_mod_documents.derivation.schemas import (
            RegisterDocumentSchema,
            handle_register_document_schema,
        )

        fields: dict[str, Any] = {
            "title": "Instrument index",
            "json_schema": INDEX_SCHEMA,
            "key_column": "tag",
            "target_kind": "tags",
            "mapping": INDEX_MAPPING,
        }
        fields.update(more)
        with open_uow(self.db) as uow:
            return handle_register_document_schema(
                uow,
                RegisterDocumentSchema(
                    **{**BASE, "scope": scope, "code": code, "semver": semver, **fields}
                ),
            )

    def open_derived(self, number: str, code: str, schema_code: str = "instrument-index") -> Any:
        from tl_mod_documents.derivation import rows
        from tl_mod_documents.derivation.derived import (
            OpenDerivedDocument,
            handle_open_derived_document,
        )

        rev = self.revision(number, code)
        with open_uow(self.db) as uow:
            made = handle_open_derived_document(
                uow, OpenDerivedDocument(**BASE, revision_id=rev.id, schema_code=schema_code)
            )
        with open_uow(self.db, readonly=True) as uow:
            return rows.get_derived(uow.conn(), made.stream_id)

    def derived_row(self, derived_id: str) -> Any:
        from tl_mod_documents.derivation import rows

        with open_uow(self.db, readonly=True) as uow:
            found = rows.get_derived(uow.conn(), derived_id)
        assert found is not None
        return found

    def contents(self, derived_id: str) -> list[Any]:
        from tl_mod_documents.derivation import rows

        with open_uow(self.db, readonly=True) as uow:
            return rows.contents_of(uow.conn(), derived_id)

    def jobs(self, derived_id: str | None = None) -> list[Any]:
        from tl_mod_documents.derivation import rows

        with open_uow(self.db, readonly=True) as uow:
            return rows.list_jobs(uow.conn(), PROJECT, derived_id=derived_id)

    def upload_content(
        self, derived_id: str, data: bytes, name: str = "index.csv", content_type: str = "text/csv"
    ) -> FileResult:
        """A person attaches a CSV to the derived document's ``content`` slot."""
        declared = RegisterUpload(
            **BASE,
            record_id=derived_id,
            slot="content",
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

    def start_extraction(self, **fields: Any) -> CommandResult:
        from tl_mod_documents.derivation.derived import StartExtraction, handle_start_extraction

        with open_uow(self.db) as uow:
            return handle_start_extraction(uow, StartExtraction(**{**BASE, **fields}))

    def run_jobs(
        self, *, timeout_s: float = 60.0, worker: str = "test-worker", clock: Any = None
    ) -> list[Any]:
        """Run the job queue to idle with the real job kinds and the child-process extractors."""
        from tl_adapters.db import make_uow_factory
        from tl_adapters.queue import job_queue_for
        from tl_core.jobs import JobRunner

        from tl_mod_documents.derivation.jobs import make_kinds

        factory = make_uow_factory(self.db)
        try:
            with factory() as uow:
                queue = job_queue_for(uow.conn())
            kwargs: dict[str, Any] = {} if clock is None else {"clock": clock}
            runner = JobRunner(
                factory,
                queue,
                make_kinds(self.files, timeout_s=timeout_s, factory=EXTRACTOR_FACTORY),
                worker_id=worker,
                **kwargs,
            )
            return runner.run_until_idle()
        finally:
            factory.dispose()

    def load_standards(self) -> None:
        """The sample company's standards (tag classes, mnemonics, numbering) into the ledger."""
        from tl_mod_engineering.document import load_standards_file
        from tl_mod_engineering.loader import load_standards

        path = (
            Path(__file__).resolve().parents[5]
            / "schema/fixtures/standards/co.acme.standards@1.0.0.yaml"
        )
        with open_uow(self.db) as uow:
            load_standards(uow, load_standards_file(path), actor="user:seed", source="test")

    def valid_derived(
        self,
        rows: list[tuple[str, str, str, str]],
        *,
        number: str = "ISD-001",
        code: str = "A",
        schema_code: str = "instrument-index",
    ) -> Any:
        """A derived document that read ``rows`` from an uploaded CSV and passed its schema."""
        derived = self.open_derived(number, code, schema_code)
        self.upload_content(derived.id, index_csv(rows))
        self.start_extraction(derived_id=derived.id)
        self.run_jobs()
        return self.derived_row(derived.id)

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
