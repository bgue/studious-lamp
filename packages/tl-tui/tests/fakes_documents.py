"""In-memory documents for `FakeClient` (P1-I2): the document reads of `ClientInterface`.

It holds `DocumentView`s and `TransmittalView`s by project and answers the reads the way the
embedded client does: documents and transmittals by number, a void document or transmittal only on
request, the module's errors for an unknown number. The stale links, overdue reviews and diffs are
whatever the test gave it. `test_embedded_documents.py` runs the same reads on this fake and on the
embedded client and compares the answers.
"""

from __future__ import annotations

from datetime import date

from tl_mod_documents import reports, views
from tl_mod_documents.errors import DocumentNotFoundError, TransmittalNotFoundError


class FakeDocumentSupport:
    """Mixin for `FakeClient`: call `_init_documents()` from its `__init__`."""

    def _init_documents(self) -> None:
        self._documents: dict[str, dict[str, views.DocumentView]] = {}
        self._transmittals: dict[str, dict[str, views.TransmittalView]] = {}
        self._stale: dict[str, list[reports.StalePinLine]] = {}
        self._overdue: dict[str, list[reports.OverdueLine]] = {}
        self._diffs: dict[tuple[str, str, str, str], views.RevisionDiffView] = {}

    def add_document(self, project: str, view: views.DocumentView) -> views.DocumentView:
        self._documents.setdefault(project, {})[view.number] = view
        return view

    def add_transmittal(self, project: str, view: views.TransmittalView) -> views.TransmittalView:
        self._transmittals.setdefault(project, {})[view.number] = view
        return view

    def add_stale_link(self, project: str, line: reports.StalePinLine) -> None:
        self._stale.setdefault(project, []).append(line)

    def add_overdue_review(self, project: str, line: reports.OverdueLine) -> None:
        self._overdue.setdefault(project, []).append(line)

    def add_diff(self, project: str, number: str, diff: views.RevisionDiffView) -> None:
        self._diffs[(project, number, diff.from_code, diff.to_code)] = diff

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
        self.calls.append("list_documents")  # type: ignore[attr-defined]
        found = [
            view.model_copy(update={"revisions": [], "links": []})
            for _, view in sorted(self._documents.get(project, {}).items())
            if (doc_type is None or view.doc_type == doc_type)
            and (discipline is None or view.discipline == discipline)
            and (state is None or view.state == state)
            and (include_void or view.state != "Void")
        ]
        return found[:limit]

    def get_document(self, project: str, number: str) -> views.DocumentView:
        self.calls.append("get_document")  # type: ignore[attr-defined]
        view = self._documents.get(project, {}).get(number)
        if view is None:
            raise DocumentNotFoundError(f"no document {number!r} in scope 'project:{project}'")
        return view

    def document_diff(
        self, project: str, number: str, from_code: str, to_code: str
    ) -> views.RevisionDiffView:
        self.calls.append("document_diff")  # type: ignore[attr-defined]
        self.get_document(project, number)
        return self._diffs[(project, number, from_code, to_code)]

    def list_stale_links(self, project: str) -> list[reports.StalePinLine]:
        self.calls.append("list_stale_links")  # type: ignore[attr-defined]
        return list(self._stale.get(project, []))

    def list_overdue_reviews(
        self, project: str, *, on: date | None = None
    ) -> list[reports.OverdueLine]:
        self.calls.append("list_overdue_reviews")  # type: ignore[attr-defined]
        return list(self._overdue.get(project, []))

    def list_transmittals(
        self,
        project: str,
        *,
        state: str | None = None,
        direction: str | None = None,
        limit: int = 500,
    ) -> list[views.TransmittalView]:
        self.calls.append("list_transmittals")  # type: ignore[attr-defined]
        found = [
            view.model_copy(update={"items": []})
            for _, view in sorted(self._transmittals.get(project, {}).items())
            if (state is None or view.state == state)
            and (state == "Void" or view.state != "Void")
            and (direction is None or view.direction == direction)
        ]
        return found[:limit]

    def get_transmittal(self, project: str, number: str) -> views.TransmittalView:
        self.calls.append("get_transmittal")  # type: ignore[attr-defined]
        view = self._transmittals.get(project, {}).get(number)
        if view is None:
            raise TransmittalNotFoundError(
                f"no transmittal {number!r} in scope 'project:{project}'"
            )
        return view
