"""The documents module's reads over HTTP: documents, links, transmittals, reports (P1-I2).

The same models the embedded services return (``tl_mod_documents.views``, and the report rows of
``tl_mod_documents.reports``). A missing document or transmittal is the module's error
(``DocumentNotFoundError``, ``TransmittalNotFoundError``), rebuilt from the error body.
"""

from __future__ import annotations

from datetime import date

from pydantic import TypeAdapter
from tl_mod_documents import reports, views

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
        """What changed between two issued revisions (``GET .../documents/{n}/diff``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/documents/{quote(number)}/diff",
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
