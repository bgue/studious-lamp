"""Acceptance script for P2-WEB1-T02: the document register page on the web.

Reuses the helpers and the world of ``S4.py`` (loaded as a module, not run). The ledger holds no
documents, so three ``DocumentView``s are built here and the three reads of the page are patched
for the whole run with ``mock.patch.object(WebReadClient, ...)``. S4's demo page is switched off
(``PAGE_SOURCE`` is an empty router). Prints one ``PASS <letter>: ...`` per check, exits 0 when all
pass and 1 on the first failure.
"""

from __future__ import annotations

import html
import importlib.util
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("accept_s4", ROOT / "dev/accept/P2-WEB1/S4.py")
assert spec is not None and spec.loader is not None
S4 = importlib.util.module_from_spec(spec)
sys.modules["accept_s4"] = S4
spec.loader.exec_module(S4)
S4.PAGE_SOURCE = (
    "from fastapi import APIRouter\n"
    "router = APIRouter(prefix='/web', include_in_schema=False)\n"  # S4's own demo page off
)

from tl_mod_documents.views import DocumentView, RevisionView  # noqa: E402
from tl_tui import document_text, file_text  # noqa: E402
from tl_web import present, routers  # noqa: E402
from tl_web.log import LOGS  # noqa: E402
from tl_web.reads import WebReadClient  # noqa: E402

expect, passed, Doc, PROJECT = S4.expect, S4.passed, S4.Doc, S4.PROJECT
COLUMNS = document_text.COLUMNS
PAGE = f"/web/p/{PROJECT}/documents"
IMG = re.compile(r"<img\b[^>]*>")
SRC = re.compile(r'src="([^"]*)"')
PDF_SCOPE = "project:P123"


def revision(doc_id: str, code: str) -> RevisionView:
    return RevisionView(
        id=f"REV-{doc_id}-{code}",
        code=code,
        state="Issued",
        issue_status="Issued",
        status_class=None,
        issued_on="2026-10-01",
        is_current=True,
        purpose=None,
        change_note=None,
        revision_date=None,
        intended_status=None,
        superseded_by=None,
    )


def document(
    number: str, title: str, doc_type: str | None, discipline: str | None, rev: RevisionView | None
) -> DocumentView:
    return DocumentView(
        id=f"DOC-{number}",
        number=number,
        title=title,
        description=None,
        state="Issued" if rev is not None else "Draft",
        doc_type=doc_type,
        discipline=discipline,
        originator=None,
        confidentiality=None,
        revision_scheme="letter",
        pattern_code=None,
        current_revision_code=rev.code if rev is not None else None,
        current_revision_status="Issued" if rev is not None else None,
        current_revision_class=None,
        current_revision_issued_on=rev.issued_on if rev is not None else None,
        superseded_by=None,
        conformance="conforming",
        version=1,
        revisions=[rev] if rev is not None else [],
        links=[],
    )


REV_1001 = revision("ISO-1001", "A")
REV_1002 = revision("ISO-1002", "A")
DOCS = [
    document("ISO-1001", "General arrangement", "DWG", "ARC", REV_1001),
    document("ISO-1002", "Drainage notes", "SPE", "CIV", REV_1002),
    document("ISO-1003", "Unissued schedule", None, None, None),
]
FILES = {
    REV_1001.id: [
        SimpleNamespace(
            file_id="FILE-1001",
            scope=PDF_SCOPE,
            filename="ISO-1001-A.pdf",
            content_type="application/pdf",
            size=1258291,
        )
    ],
    REV_1002.id: [
        SimpleNamespace(
            file_id="FILE-1002",
            scope=PDF_SCOPE,
            filename="notes.txt",
            content_type="text/plain",
            size=2048,
        )
    ],
}


def fake_list_documents(self: WebReadClient, project: str, **kwargs: Any) -> list[DocumentView]:
    return list(DOCS)


def fake_get_document(self: WebReadClient, project: str, number: str) -> DocumentView:
    for doc in DOCS:
        if doc.number == number:
            return doc
    raise KeyError(number)


def fake_list_record_files(self: WebReadClient, record_id: str) -> list[Any]:
    return list(FILES.get(record_id, []))


def labels_for(world: Any, name: str) -> Any:
    """The labels the page uses: the project scope and the document label types."""
    return present.load_labels(
        present.as_client(world.reads(name)), f"project:{PROJECT}", ("documents.Document",)
    )


def status_text(doc: Any) -> str:
    return html.unescape(doc.texts.get("log-status", "")).strip()


def images(text: str) -> list[str]:
    return IMG.findall(text)


def src_of(tag: str) -> str:
    found = SRC.search(tag)
    assert found is not None, f"no src in {tag!r}"
    return html.unescape(found.group(1))


def expected_panel(view: DocumentView, labels: Any, files: list[Any]) -> list[str]:
    lines = document_text.detail_lines(view, labels, technical=False)
    if not files:
        return lines
    listed = [file_text.file_line(f.filename, f.content_type, f.size) for f in files]
    return [*lines, "", "Files", *listed]


def check_registration() -> None:
    import tl_web.pages.documents as documents

    mounted = any(r is documents.router for r in routers.page_routers())
    expect(mounted, "pages.documents is not mounted")
    expect(LOGS["documents"].SLUG == "documents", f"SLUG {LOGS['documents'].SLUG!r}")
    passed("a: routers.page_routers() mounts tl_web.pages.documents; LOGS['documents'].SLUG")


def check_page(world: Any) -> None:
    alice, _ = world.web("alice")
    page = alice.get(PAGE)
    expect(page.status_code == 200, f"page {page.status_code}")
    doc = Doc(page.text)
    seen = [i for i in doc.ids if i in S4.REGIONS]
    expect(seen == S4.REGIONS, f"regions {seen}")
    expect(doc.headers[:3] == ["Number", "Title", "State"], f"columns {doc.headers}")
    labels = labels_for(world, "alice")
    full = [document_text.row_cells(view, labels, technical=False) for view in DOCS]
    positions = [COLUMNS.index(h) for h in doc.headers]
    expect(len(doc.rows) == len(full) == 3, f"{len(doc.rows)} rows")
    for row, cells in zip(doc.rows, full, strict=True):
        expect(row["cells"] == [cells[i] for i in positions], f"cells {row['cells']} != {cells}")
    passed("b: seven regions in order; columns start Number, Title, State; cells == row_cells")


def check_panels(world: Any) -> None:
    alice, _ = world.web("alice")
    labels = labels_for(world, "alice")
    # ISO-1001: the picture of page 1 first, then the lines and the file of the current revision
    first = alice.get(f"{PAGE}/panel/ISO-1001")
    expect(first.status_code == 200, f"panel ISO-1001 {first.status_code}")
    got = Doc(first.text)
    lines = expected_panel(DOCS[0], labels, FILES[REV_1001.id])
    expect(got.texts.get("pre", "").split("\n") == lines, "ISO-1001 panel is not the lines")
    pictures = images(first.text)
    expect(len(pictures) == 1, f"ISO-1001 has {len(pictures)} images")
    want = "/web/files/FILE-1001/page1.png?scope=project%3AP123"
    expect(src_of(pictures[0]) == want, f"ISO-1001 src {src_of(pictures[0])!r}")
    passed("c1: panel ISO-1001 has one page-1 image of its PDF, then detail lines and Files")
    # ISO-1002: no PDF, so no picture; the file is shown as a line
    second = alice.get(f"{PAGE}/panel/ISO-1002")
    expect(second.status_code == 200, f"panel ISO-1002 {second.status_code}")
    lines = expected_panel(DOCS[1], labels, FILES[REV_1002.id])
    expect(Doc(second.text).texts.get("pre", "").split("\n") == lines, "ISO-1002 panel lines")
    expect(images(second.text) == [], "ISO-1002 has a picture")
    expect(file_text.file_line("notes.txt", "text/plain", 2048) in lines, "no notes.txt line")
    passed("c2: panel ISO-1002 has the notes.txt line and no picture")
    # ISO-1003: no revision, so no Files list and no picture
    third = alice.get(f"{PAGE}/panel/ISO-1003")
    expect(third.status_code == 200, f"panel ISO-1003 {third.status_code}")
    lines = expected_panel(DOCS[2], labels, [])
    expect(Doc(third.text).texts.get("pre", "").split("\n") == lines, "ISO-1003 panel lines")
    expect("Files" not in lines and images(third.text) == [], "ISO-1003 shows Files or a picture")
    passed("c3: panel ISO-1003 has no Files line and no picture")


def check_selected(world: Any) -> None:
    alice, _ = world.web("alice")
    page = alice.get(PAGE).text
    start = page.index('id="log-panel"')
    end = page.find('id="log-status"', start)
    region = page[start:] if end < 0 else page[start:end]
    pictures = images(region)
    expect(len(pictures) == 1, f"the selected panel has {len(pictures)} images")
    want = "/web/files/FILE-1001/page1.png?scope=project%3AP123"
    expect(src_of(pictures[0]) == want, f"selected src {src_of(pictures[0])!r}")
    passed("d: the page with the first row selected shows ISO-1001's picture inside #log-panel")


def check_summary(world: Any) -> None:
    alice, _ = world.web("alice")
    labels = labels_for(world, "alice")
    want = present.document_text.summary_line(
        3, 3, state=None, doc_type=None, include_void=False, text="", labels=labels
    )
    got = status_text(Doc(alice.get(PAGE).text))
    expect(got == want, f"status {got!r} != summary {want!r}")
    passed(f"e: #log-status is summary_line(3, 3, ...): {want}")


def check_filter_and_hidden(world: Any) -> None:
    alice, _ = world.web("alice")
    found = Doc(alice.get(f"{PAGE}?q=1002").text)
    numbers = [r["cells"][0] for r in found.rows]
    expect(numbers == ["ISO-1002"], f"?q=1002 shows {numbers}")
    unknown = alice.get(f"{PAGE}/panel/ISO-9999")
    expect(unknown.status_code == 404, f"unknown panel {unknown.status_code}")
    other = alice.get(f"{PAGE}/panel/ISO-9998")
    expect(other.status_code == 404, f"second unknown panel {other.status_code}")
    expect(unknown.content == other.content, "two unknown numbers answer different 404 pages")
    passed("f: ?q=1002 leaves only ISO-1002; /panel/ISO-9999 is the 404 page of ISO-9998")


def check_sign_in(world: Any) -> None:
    response = world.client().get(PAGE)
    expect(response.status_code == 303, f"no cookie: {response.status_code}")
    location = response.headers.get("location", "")
    expect(location.startswith("/web/sign-in"), f"redirect to {location!r}")
    passed("g: no cookie: 303 to /web/sign-in")


def check_no_actions(world: Any) -> None:
    alice, _ = world.web("alice")
    page = alice.get(PAGE).text
    start = page.index('id="log-actions"')
    end = page.find("</div>", start)
    bar = page[start:end]
    expect("data-command" not in bar, "an action button is in #log-actions")
    expect("log-open" in bar, "the Open link is missing from #log-actions")
    expect(Doc(page).buttons == [], f"buttons on the page: {Doc(page).buttons}")
    passed("h: #log-actions holds only the Open link; no action button for any row")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        world = S4.World(Path(tmp))
        try:
            patches = [
                mock.patch.object(WebReadClient, "list_documents", fake_list_documents),
                mock.patch.object(WebReadClient, "get_document", fake_get_document),
                mock.patch.object(WebReadClient, "list_record_files", fake_list_record_files),
            ]
            for patch in patches:
                patch.start()
            try:
                check_registration()
                check_page(world)
                check_panels(world)
                check_selected(world)
                check_summary(world)
                check_filter_and_hidden(world)
                check_sign_in(world)
                check_no_actions(world)
            finally:
                for patch in patches:
                    patch.stop()
        finally:
            world.backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
