"""The documents module's reads over HTTP: documents, links, transmittals, reports (P1-I2).

The same models the embedded services return (``tl_mod_documents.views``, and the report rows of
``tl_mod_documents.reports``). A missing document or transmittal is the module's error
(``DocumentNotFoundError``, ``TransmittalNotFoundError``), rebuilt from the error body.
"""

from __future__ import annotations

from datetime import date

from pydantic import TypeAdapter
from tl_core.services.commands import CommandResult
from tl_mod_documents import reports, views
from tl_mod_documents.handlers.documents import RegisterDocument
from tl_mod_documents.handlers.revisions import CreateRevision
from tl_mod_documents.handlers.transmittals import CreateTransmittal, IssueTransmittal
from tl_mod_documents.resolver import RepinDocumentLink

from tl_api.client.base import ApiClientBase, quote


class DocumentsApi(ApiClientBase):
    def list_documents(
        self,
        project: str,
        *,
        doc_type: str | None = None,
        discipline: str | None = None,
        state: str | None = None,
        include_void: bool = False,
        limit: int = 1000,
    ) -> list[views.DocumentView]:
        """A project's documents by number (``GET /projects/{project}/documents``)."""
        params = {
            "type": doc_type,
            "discipline": discipline,
            "state": state,
            "include_void": "true" if include_void else None,
            "limit": limit,
        }
        data = self._get_json(f"/projects/{quote(project)}/documents", params)
        return self._models(views.DocumentView, data)

    def get_document(self, project: str, number: str) -> views.DocumentView:
        """One document with revisions and links (``GET /projects/{project}/documents/{n}``)."""
        data = self._get_json(f"/projects/{quote(project)}/documents/{quote(number)}")
        return self._model(views.DocumentView, data)

    def document_diff(
        self, project: str, number: str, from_code: str, to_code: str
    ) -> views.RevisionDiffView:
        """What changed between two issued revisions (``GET .../document-diffs/{n}``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/document-diffs/{quote(number)}",
            {"from": from_code, "to": to_code},
        )
        return self._model(views.RevisionDiffView, data)

    def list_stale_links(self, project: str) -> list[reports.StalePinLine]:
        """Stale links to documents (``GET /projects/{project}/stale-links``)."""
        data = self._get_json(f"/projects/{quote(project)}/stale-links")
        return TypeAdapter(list[reports.StalePinLine]).validate_python(data)

    def list_overdue_reviews(
        self, project: str, *, on: date | None = None
    ) -> list[reports.OverdueLine]:
        """Overdue reviews (``GET /projects/{project}/overdue-reviews``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/overdue-reviews",
            {"on": on.isoformat() if on is not None else None},
        )
        return TypeAdapter(list[reports.OverdueLine]).validate_python(data)

    def list_transmittals(
        self,
        project: str,
        *,
        state: str | None = None,
        direction: str | None = None,
        limit: int = 500,
    ) -> list[views.TransmittalView]:
        """A project's transmittals by number (``GET /projects/{project}/transmittals``)."""
        params = {"state": state, "direction": direction, "limit": limit}
        data = self._get_json(f"/projects/{quote(project)}/transmittals", params)
        return self._models(views.TransmittalView, data)

    def get_transmittal(self, project: str, number: str) -> views.TransmittalView:
        """One transmittal with its items (``GET /projects/{project}/transmittals/{n}``)."""
        data = self._get_json(f"/projects/{quote(project)}/transmittals/{quote(number)}")
        return self._model(views.TransmittalView, data)

    def repin_document_link(self, cmd: RepinDocumentLink) -> CommandResult:
        """Move a link to another revision (``POST /commands/RepinDocumentLink``)."""
        return self._command("RepinDocumentLink", cmd)

    def create_transmittal(self, cmd: CreateTransmittal) -> CommandResult:
        """Draft a transmittal (``POST /commands/CreateTransmittal``); the token's actor is used."""
        return self._command("CreateTransmittal", cmd)

    def issue_transmittal(self, cmd: IssueTransmittal) -> CommandResult:
        """Issue a draft transmittal (``POST /commands/IssueTransmittal``): a controller's act."""
        return self._command("IssueTransmittal", cmd)

    def register_document(self, cmd: RegisterDocument) -> CommandResult:
        """Register a document under its number (``POST /commands/RegisterDocument``)."""
        return self._command("RegisterDocument", cmd)

    def create_revision(self, cmd: CreateRevision) -> CommandResult:
        """Start the next revision, as a draft (``POST /commands/CreateRevision``)."""
        return self._command("CreateRevision", cmd)
