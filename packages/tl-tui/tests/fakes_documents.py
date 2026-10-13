"""In-memory documents for `FakeClient` (P1-I2): the document reads of `ClientInterface`.

It holds `DocumentView`s and `TransmittalView`s by project and answers the reads the way the
embedded client does: documents and transmittals by number, a void document or transmittal only on
request, the module's errors for an unknown number. The stale links, overdue reviews and diffs are
whatever the test gave it. `test_embedded_documents.py` runs the same reads on this fake and on the
embedded client and compares the answers.
"""

from __future__ import annotations

from datetime import date

from tl_core.services.commands import CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_mod_documents import reports, views
from tl_mod_documents.errors import (
    DocumentNotFoundError,
    InvalidPinError,
    InvalidTransmittalError,
    RevisionNotFoundError,
    TransmittalNotFoundError,
)
from tl_mod_documents.handlers.transmittals import CreateTransmittal
from tl_mod_documents.resolver import CURRENT, RepinDocumentLink


class FakeDocumentSupport:
    """Mixin for `FakeClient`: call `_init_documents()` from its `__init__`."""

    def _init_documents(self) -> None:
        self._documents: dict[str, dict[str, views.DocumentView]] = {}
        self._transmittals: dict[str, dict[str, views.TransmittalView]] = {}
        self._stale: dict[str, list[reports.StalePinLine]] = {}
        self._overdue: dict[str, list[reports.OverdueLine]] = {}
        self._diffs: dict[tuple[str, str, str, str], views.RevisionDiffView] = {}
        self.document_commands: list[object] = []  # every command a document screen sent

    def seed_documents(self, project: str = "P123") -> None:
        """Three documents the document screens' tests share.

        ``ISO-1234`` has A (IFR, replaced as the current review revision by B) and B (IFC, current);
        the tag ``47-FV-1001`` is pinned to A, so the link is stale, and ``47-FV-1002`` floats.
        ``ISO-2000`` is registered with no revision. ``ISO-3000`` is void. The A to B diff is
        stored, and the stale link is in the stale-link report.
        """
        pdf_a = views.RenditionView(
            kind="pdf", filename="sheet-A.pdf", content_type="application/pdf", size=1200,
            sha256="a" * 64, page_count=3, is_current=True,
        )  # fmt: skip
        pdf_b = pdf_a.model_copy(update={"filename": "sheet-B.pdf", "size": 1900, "page_count": 5})
        rev_a = views.RevisionView(
            id="REV-ISO-1234-A", code="A", state="Issued", issue_status="IFR",
            status_class="review", issued_on="2026-10-01", is_current=False, purpose="First issue",
            change_note=None, revision_date="2026-10-01", intended_status=None,
            superseded_by=None, renditions=[pdf_a],
        )  # fmt: skip
        rev_b = rev_a.model_copy(
            update={
                "id": "REV-ISO-1234-B", "code": "B", "issue_status": "IFC",
                "status_class": "construction", "issued_on": "2026-10-10", "is_current": True,
                "purpose": "For construction", "renditions": [pdf_b],
            }
        )  # fmt: skip
        stale = views.DocumentLinkView(
            link_id="LINK-STALE", from_key="47-FV-1001", from_type="core.Record",
            from_title="Feed gas control valve", relation="references", link_status="stale",
            pin="A", pin_state="stale", current_code="B", newer_codes=["B"],
        )  # fmt: skip
        floating = views.DocumentLinkView(
            link_id="LINK-FLOAT", from_key="47-FV-1002", from_type="core.Record",
            from_title="Second valve", relation="references", link_status="active",
            pin=None, pin_state="floating", current_code="B", newer_codes=[],
        )  # fmt: skip
        base = views.DocumentView(
            id="DOC-ISO-1234", number="ISO-1234", title="Isometric, line 47-P-101",
            description=None, state="Issued", doc_type="ISO", discipline="PIP", originator=None,
            confidentiality=None, revision_scheme="alpha", pattern_code=None,
            current_revision_code="B", current_revision_status="IFC",
            current_revision_class="construction", current_revision_issued_on="2026-10-10",
            superseded_by=None, conformance="ok", version=9,
            revisions=[rev_a, rev_b], links=[stale, floating],
        )  # fmt: skip
        self.add_document(project, base)
        self.add_document(
            project,
            base.model_copy(
                update={
                    "id": "DOC-ISO-2000", "number": "ISO-2000", "title": "Pump datasheet",
                    "state": "Registered", "doc_type": "DAT", "discipline": "MEC",
                    "current_revision_code": None, "current_revision_status": None,
                    "current_revision_class": None, "current_revision_issued_on": None,
                    "revisions": [], "links": [],
                }
            ),
        )  # fmt: skip
        self.add_document(
            project,
            base.model_copy(
                update={
                    "id": "DOC-ISO-3000", "number": "ISO-3000", "title": "Drawn in error",
                    "state": "Void", "current_revision_code": None,
                    "current_revision_status": None, "current_revision_class": None,
                    "current_revision_issued_on": None, "revisions": [], "links": [],
                }
            ),
        )  # fmt: skip
        self.add_diff(
            project,
            "ISO-1234",
            views.RevisionDiffView(
                document_number="ISO-1234", from_code="A", to_code="B", from_status="IFR",
                to_status="IFC",
                summary=[
                    "ISO-1234: A (IFR) to B (IFC)",
                    "status IFR to IFC",
                    "issued B (IFC, 2026-10-10): For construction",
                    "pdf changed: sheet-A.pdf, 1 KB, 3 pages to sheet-B.pdf, 2 KB, 5 pages",
                ],
            ),
        )  # fmt: skip
        self.add_stale_link(
            project,
            reports.StalePinLine(
                document_number="ISO-1234", document_title="Isometric, line 47-P-101",
                pinned_code="A", current_code="B", current_status="IFC", linked_key="47-FV-1001",
                linked_type="core.Record", link_id="LINK-STALE", link_status="stale",
                newer_codes=["B"],
            ),
        )  # fmt: skip

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

    # --- the two changes a document screen makes -------------------------------------------

    def repin_document_link(self, cmd: RepinDocumentLink) -> CommandResult:
        """Move a stored link to ``cmd.pin`` (``current`` is the document's current revision)."""
        self.calls.append("repin_document_link")  # type: ignore[attr-defined]
        self.document_commands.append(cmd)
        for project, documents in self._documents.items():
            for number, doc in documents.items():
                for index, link in enumerate(doc.links):
                    if link.link_id != cmd.link_id:
                        continue
                    pin = doc.current_revision_code if cmd.pin == CURRENT else cmd.pin
                    codes = [r.code for r in doc.revisions if r.issue_status is not None]
                    if pin is None or pin not in codes:
                        raise InvalidPinError(f"{pin!r} is not an issued revision of {number}")
                    moved = link.model_copy(
                        update={
                            "pin": pin,
                            "pin_state": "current" if pin == doc.current_revision_code else "stale",
                            "link_status": "active",
                            "newer_codes": codes[codes.index(pin) + 1 :],
                        }
                    )
                    links = [*doc.links[:index], moved, *doc.links[index + 1 :]]
                    documents[number] = doc.model_copy(update={"links": links})
                    self._stale[project] = [
                        s for s in self._stale.get(project, []) if s.link_id != cmd.link_id
                    ]
                    return CommandResult(stream_id=cmd.link_id, key=None, version=2, events=[])
        raise RecordNotFoundError(f"no link {cmd.link_id!r}")

    def create_transmittal(self, cmd: CreateTransmittal) -> CommandResult:
        """Store a draft transmittal numbered ``P123-TRN-000n`` for the project of the scope."""
        self.calls.append("create_transmittal")  # type: ignore[attr-defined]
        self.document_commands.append(cmd)
        project = cmd.scope.removeprefix("project:")
        by_id = {
            r.id: (doc, r)
            for doc in self._documents.get(project, {}).values()
            for r in doc.revisions
        }
        items: list[views.TransmittalItemView] = []
        for position, revision_id in enumerate(cmd.revision_ids, start=1):
            if revision_id not in by_id:
                raise RevisionNotFoundError(f"no revision {revision_id!r} in scope {cmd.scope!r}")
            if by_id[revision_id][1].issue_status is None:
                raise InvalidTransmittalError("a transmittal carries issued revisions only")
            doc, rev = by_id[revision_id]
            items.append(
                views.TransmittalItemView(
                    position=position,
                    document_number=doc.number,
                    revision_code=rev.code,
                    issue_status=rev.issue_status,
                )
            )
        known = self._transmittals.setdefault(project, {})
        number = cmd.number or f"{project}-TRN-{len(known) + 1:04d}"
        known[number] = views.TransmittalView(
            id=f"TRN{len(known) + 1:023d}",
            number=number,
            title=cmd.subject,
            description=cmd.notes,
            state="Draft",
            direction=cmd.direction,
            purpose=cmd.purpose,
            due_date=cmd.due_date,
            issued_on=None,
            response_code=None,
            response_note=None,
            responded_on=None,
            recipients=[r.model_dump() for r in cmd.recipients],
            version=2,
            items=items,
        )
        return CommandResult(stream_id=known[number].id, key=number, version=2, events=[])
