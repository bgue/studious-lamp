"""The document register page: ``GET /web/p/{project}/documents`` (P2-WEB1-T02, D20).

The three reads of the page are patched with ``mock.patch.object(WebReadClient, ...)`` and three
``DocumentView``s: one with a PDF (the panel opens with the picture of page 1), one with a text file
(the file is a line, no picture) and one with no revision. The commands of the document module have
no ``ACTION_UI`` row, so the page offers no action (D20). The real documents of the world are read
once, unpatched, at the end.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from tl_mod_documents.views import DocumentView, RevisionView
from tl_tui import document_text, file_text
from tl_web import present, routers
from tl_web.log import LOGS
from tl_web.reads import WebReadClient

PAGE = "/web/p/P123/documents"
COLUMNS = document_text.COLUMNS
SCOPE = "project:P123"
PICTURE = "/web/files/FILE-1001/page1.png?scope=project%3AP123"
IMG = re.compile(r"<img\b[^>]*>")


def revision(doc_id: str, code: str) -> RevisionView:
    return RevisionView(
        id=f"REV-{doc_id}-{code}", code=code, state="Issued", issue_status="Issued",
        status_class=None, issued_on="2026-10-01", is_current=True, purpose=None, change_note=None,
        revision_date=None, intended_status=None, superseded_by=None,
    )  # fmt: skip


def document(
    number: str, title: str, doc_type: str | None, discipline: str | None, rev: RevisionView | None
) -> DocumentView:
    return DocumentView(
        id=f"DOC-{number}", number=number, title=title, description=None,
        state="Issued" if rev is not None else "Draft", doc_type=doc_type, discipline=discipline,
        originator=None, confidentiality=None, revision_scheme="letter", pattern_code=None,
        current_revision_code=rev.code if rev is not None else None,
        current_revision_status="Issued" if rev is not None else None,
        current_revision_class=None,
        current_revision_issued_on=rev.issued_on if rev is not None else None,
        superseded_by=None, conformance="conforming", version=1,
        revisions=[rev] if rev is not None else [], links=[],
    )  # fmt: skip


REV_1001, REV_1002 = revision("ISO-1001", "A"), revision("ISO-1002", "A")
DOCS = [
    document("ISO-1001", "General arrangement", "DWG", "ARC", REV_1001),
    document("ISO-1002", "Drainage notes", "SPE", "CIV", REV_1002),
    document("ISO-1003", "Unissued schedule", None, None, None),
]
FILES = {
    REV_1001.id: [SimpleNamespace(
        file_id="FILE-1001", scope=SCOPE, filename="ISO-1001-A.pdf",
        content_type="application/pdf", size=1258291,
    )],
    REV_1002.id: [SimpleNamespace(
        file_id="FILE-1002", scope=SCOPE, filename="notes.txt",
        content_type="text/plain", size=2048,
    )],
}  # fmt: skip


def labels_for(w: Any, name: str) -> Any:
    return present.load_labels(present.as_client(w.reads(name)), SCOPE, ("documents.Document",))


def expected_panel(view: DocumentView, labels: Any, files: list[Any]) -> list[str]:
    lines = document_text.detail_lines(view, labels, technical=False)
    if not files:
        return lines
    listed = [file_text.file_line(f.filename, f.content_type, f.size) for f in files]
    return [*lines, "", "Files", *listed]


def pictures(text: str) -> list[str]:
    tags = IMG.findall(text)
    return [re.search(r'src="([^"]*)"', t).group(1).replace("&amp;", "&") for t in tags]  # type: ignore[union-attr]


@pytest.fixture
def fakes() -> Iterator[None]:
    def list_documents(self: WebReadClient, project: str, **kwargs: Any) -> list[DocumentView]:
        return list(DOCS)

    def get_document(self: WebReadClient, project: str, number: str) -> DocumentView:
        for doc in DOCS:
            if doc.number == number:
                return doc
        raise KeyError(number)

    def list_record_files(self: WebReadClient, record_id: str) -> list[Any]:
        return list(FILES.get(record_id, []))

    with (
        mock.patch.object(WebReadClient, "list_documents", list_documents),
        mock.patch.object(WebReadClient, "get_document", get_document),
        mock.patch.object(WebReadClient, "list_record_files", list_record_files),
    ):
        yield


def test_the_page_is_mounted_and_registered() -> None:
    import tl_web.pages.documents as documents

    assert any(r is documents.router for r in routers.page_routers())
    assert LOGS["documents"].SLUG == "documents"


def test_seven_regions_and_the_cells_equal_row_cells(world: Any, htmlkit: Any, fakes: None) -> None:
    page = world.web("bob").client.get(PAGE)
    assert page.status_code == 200
    doc = htmlkit.parse(page.text)
    assert doc.regions() == list(htmlkit.LOG_REGIONS)
    assert doc.headers("log-table")[:3] == ["Number", "Title", "State"]
    labels = labels_for(world, "bob")
    full = [document_text.row_cells(view, labels, technical=False) for view in DOCS]
    assert doc.rows("log-table") == htmlkit.project_cells(doc.headers("log-table"), COLUMNS, full)


def test_the_panel_of_a_pdf_document_opens_with_page_1_then_lines_and_files(
    world: Any, htmlkit: Any, fakes: None
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/ISO-1001")
    assert panel.status_code == 200
    lines = expected_panel(DOCS[0], labels_for(world, "bob"), FILES[REV_1001.id])
    assert htmlkit.parse(panel.text).pre().split("\n") == lines
    assert pictures(panel.text) == [PICTURE]


def test_a_text_file_is_a_line_and_no_picture(world: Any, htmlkit: Any, fakes: None) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/ISO-1002")
    lines = expected_panel(DOCS[1], labels_for(world, "bob"), FILES[REV_1002.id])
    assert htmlkit.parse(panel.text).pre().split("\n") == lines
    assert file_text.file_line("notes.txt", "text/plain", 2048) in lines
    assert pictures(panel.text) == []  # the text fallback: a line, not an image


def test_a_document_with_no_revision_has_no_files_and_no_picture(
    world: Any, htmlkit: Any, fakes: None
) -> None:
    panel = world.web("bob").client.get(f"{PAGE}/panel/ISO-1003")
    lines = expected_panel(DOCS[2], labels_for(world, "bob"), [])
    assert htmlkit.parse(panel.text).pre().split("\n") == lines
    assert "Files" not in lines and pictures(panel.text) == []


def test_the_selected_row_shows_its_picture_inside_the_panel_region(
    world: Any, htmlkit: Any, fakes: None
) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    inside = doc.by_id("log-panel")
    assert inside is not None
    assert [i.get("src") for i in inside.find_all("img")] == [PICTURE]
    assert len(doc.images()) == 1


def test_the_status_line_is_the_documents_summary(world: Any, htmlkit: Any, fakes: None) -> None:
    want = present.document_text.summary_line(
        3, 3, state=None, doc_type=None, include_void=False, text="",
        labels=labels_for(world, "bob"),
    )  # fmt: skip
    assert htmlkit.parse(world.web("bob").client.get(PAGE).text).status() == want


def test_the_filter_and_an_unknown_number(world: Any, htmlkit: Any, fakes: None) -> None:
    bob = world.web("bob").client
    found = htmlkit.parse(bob.get(PAGE, params={"q": "1002"}).text)
    assert [r.get("data-number") for r in found.log_rows()] == ["ISO-1002"]
    one, two = bob.get(f"{PAGE}/panel/ISO-9999"), bob.get(f"{PAGE}/panel/ISO-9998")
    assert one.status_code == two.status_code == 404 and one.content == two.content


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, fakes: None) -> None:
    response = world.client().get(PAGE)
    assert response.status_code == 303 and response.headers["location"].startswith("/web/sign-in")


def test_the_actions_bar_holds_only_the_open_link(world: Any, htmlkit: Any, fakes: None) -> None:
    doc = htmlkit.parse(world.web("bob").client.get(PAGE).text)
    assert doc.buttons() == []
    bar = doc.by_id("log-actions")
    assert bar is not None and bar.find("a", id="log-open") is not None
    assert "data-command" not in bar.text()


def test_a_real_issued_document_shows_its_pdfs_first_page(world: Any, htmlkit: Any) -> None:
    """No patch: the world's ISO-9002 has revision A and a PDF rendition."""
    bob = world.web("bob").client
    doc = htmlkit.parse(bob.get(f"{PAGE}/panel/ISO-9002").text)
    images = doc.images()
    assert len(images) == 1
    assert re.fullmatch(
        r"/web/files/[0-9A-Z]+/page1\.png\?scope=project%3AP123", images[0].get("src")
    )
    assert "Files" in doc.pre().split("\n")
    hidden = bob.get(f"{PAGE}/panel/ISO-9001")  # the restricted document
    assert hidden.status_code == 404
    assert hidden.content == bob.get(f"{PAGE}/panel/ISO-0000").content
