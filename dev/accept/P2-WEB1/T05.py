"""Acceptance script for P2-WEB1 T05: the full PDF viewer page and ``pdfview.js``.

Reuses the S3 world (``S3.World``, ``S3.make_pdf``, the web sessions) by loading S3 as a module;
importing S3 runs nothing. Runs on SQLite with a temp ledger under ``TL_ENV=test`` with the FastAPI
TestClient on ``http://127.0.0.1``. Prints one ``PASS <check>`` line per check; exits 0 when every
check passes, 1 on the first failure. Expected values come from the ticket text
(``docs/tickets/P2-WEB1/T05-pdf-viewer.md``), never from the code under test. ``pdfview.js`` is not
run in a browser here; check (g) only reads its text.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[3]
_S3_PATH = ROOT / "dev/accept/P2-WEB1/S3.py"
_spec = importlib.util.spec_from_file_location("p2_web1_s3", _S3_PATH)
assert _spec is not None and _spec.loader is not None
S3 = importlib.util.module_from_spec(_spec)
sys.modules["p2_web1_s3"] = S3
_spec.loader.exec_module(S3)

from tl_core import confidentiality as cf  # noqa: E402
from tl_core.files.service import CompleteUpload, RegisterUpload  # noqa: E402

PROJECT = S3.SCOPE.partition(":")[2]  # "P123"
SCOPE_Q = quote(S3.SCOPE, safe="")  # "project%3AP123"
WORKER = "/web/static/vendor/pdfjs/pdf.worker.min.mjs"
SCRIPT_TAG = '<script type="module" src="/web/static/pdfview.js"></script>'
NEVER = S3.NEVER
CSP = S3.CSP
MAX_BYTES = S3.MAX_BYTES  # the spec: over 50 MB is not viewed


def passed(check: str) -> None:
    print(f"PASS {check}")


def expect(condition: bool, what: str) -> None:
    if not condition:
        raise AssertionError(what)


def view_path(file_id: str) -> str:
    return f"/web/p/{PROJECT}/files/{file_id}/view"


def download_href(file_id: str) -> str:
    return f'href="/web/files/{file_id}/content?scope={SCOPE_Q}"'


def upload(w: S3.World, record_id: str, filename: str, data: bytes, content_type: str) -> str:
    """The S3 upload with the content type given (``S3.World.upload`` always says PDF)."""
    with cf.system_view():
        with w.backend(False) as uow:
            ticket = w.service.register_upload(
                uow,
                RegisterUpload(
                    actor="user:ctl", source="test", scope=S3.SCOPE, record_id=record_id, slot=None,
                    filename=filename, content_type=content_type, size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                ),
                by_module=True,
            )  # fmt: skip
        with w.backend(False) as uow:
            done = w.service.complete_upload(
                uow,
                CompleteUpload(
                    actor="user:ctl", source="test", scope=S3.SCOPE, upload_id=ticket.upload_id
                ),
                io.BytesIO(data),
                by_module=True,
            )
    return done.file_id


def check_pdf_page(w: S3.World, file_id: str, bob_cookie: str) -> str:
    """(a) the viewer for a PDF: the data attributes, the download link and the script tag."""
    response = w.client(cookie=bob_cookie).get(view_path(file_id))
    expect(response.status_code == 200, f"viewer {response.status_code} {response.text[:200]}")
    html = response.text
    expect(html.count('id="pdf-view"') == 1, "no single pdf-view element")
    expect(
        html.count(f'data-src="/web/files/{file_id}/content?scope={SCOPE_Q}"') == 1,
        "data-src is not the scoped content URL",
    )
    expect(html.count(f'data-worker="{WORKER}"') == 1, "data-worker is not the vendored worker")
    expect(download_href(file_id) in html, "no download link")
    expect(SCRIPT_TAG in html, "no pdfview.js script tag")
    passed("a: viewer 200 with pdf-view, scoped data-src, worker, download link, script tag")
    return html


def check_markup(w: S3.World, file_id: str, bob_cookie: str, html: str) -> None:
    """(b) no inline script, no style or on* attribute, the S3 CSP header."""
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
    expect(len(scripts) == html.count("<script"), "a script tag does not close")
    for attrs, body in scripts:
        expect(re.search(r"\ssrc=", attrs) is not None, f"script without src: {attrs!r}")
        expect(body.strip() == "", f"inline script body: {body[:80]!r}")
    expect(re.search(r"\sstyle\s*=", html) is None, "a style attribute")
    expect(re.search(r"\son[a-z]+\s*=", html, re.I) is None, "an on* attribute")
    response = w.client(cookie=bob_cookie).get(view_path(file_id))
    expect(response.headers["content-security-policy"] == CSP, "CSP header differs")
    passed("b: no inline script, no style= or on* attribute; the S3 CSP header")


def check_other_files(w: S3.World, ids: dict[str, str], bob_cookie: str) -> None:
    """(c) a text file and a PDF over 50 MB: 200, a download link, no viewer."""
    bob = w.client(cookie=bob_cookie)
    for name in ("text", "huge"):
        response = bob.get(view_path(ids[name]))
        expect(response.status_code == 200, f"{name}: {response.status_code}")
        expect(download_href(ids[name]) in response.text, f"{name}: no download link")
        expect('id="pdf-view"' not in response.text, f"{name}: a pdf-view element")
        expect("pdfview.js" not in response.text, f"{name}: the viewer script")
    passed("c: a text file and a PDF over 50 MB: 200, a download link, no pdf-view, no pdfview.js")


def check_hidden(w: S3.World, ids: dict[str, str], bob_cookie: str, ctl_cookie: str) -> None:
    """(d) a hidden file is the same 404 as an id that never existed; the controller can open it."""
    bob = w.client(cookie=bob_cookie)
    hidden = bob.get(view_path(ids["hidden"]))
    never = bob.get(view_path(NEVER))
    expect(
        hidden.status_code == 404 == never.status_code,
        f"{hidden.status_code} {never.status_code}",
    )
    expect(
        hidden.text.replace(ids["hidden"], NEVER) == never.text,
        "the hidden file's 404 differs from the unknown id's 404",
    )
    opened = w.client(cookie=ctl_cookie).get(view_path(ids["hidden"]))
    expect(
        opened.status_code == 200 and 'id="pdf-view"' in opened.text,
        f"ctl: {opened.status_code}",
    )
    passed("d: a hidden file's view is the same 404 as an unknown id; the controller opens it")


def check_no_cookie(w: S3.World, ids: dict[str, str]) -> None:
    """(e) no cookie: 303 to the sign-in page."""
    anon = w.client().get(view_path(ids["pdf"]))
    expect(anon.status_code == 303, f"no cookie: {anon.status_code}")
    expect(anon.headers["location"] == "/web/sign-in", f"redirect: {anon.headers}")
    passed("e: a request without a cookie is 303 to /web/sign-in")


def check_bytes(w: S3.World, ids: dict[str, str], bob_cookie: str, html: str, pdf: bytes) -> None:
    """(f) the data-src bytes, with the same cookie, have the SHA-256 the file info states."""
    info = w.client(w.bearer["bob"]).get(f"/files/{ids['pdf']}?scope={S3.SCOPE}")
    expect(info.status_code == 200, f"file info: {info.status_code}")
    stated = info.json()["sha256"]
    expect(stated == hashlib.sha256(pdf).hexdigest(), "the file info sha256 is not the upload's")
    src = re.search(r'data-src="([^"]+)"', html)
    expect(src is not None, "no data-src")
    fetched = w.client(cookie=bob_cookie).get(src.group(1))
    expect(fetched.status_code == 200, f"data-src fetch: {fetched.status_code}")
    expect(
        hashlib.sha256(fetched.content).hexdigest() == stated,
        "data-src bytes differ from the file",
    )
    passed("f: the data-src bytes with the same cookie have the SHA-256 the file info states")


def check_script() -> None:
    """(g) pdfview.js as text: the pdf.js options and no eval-like or markup-writing calls."""
    js = (ROOT / "packages/tl-web/src/tl_web/static/pdfview.js").read_text(encoding="utf-8")
    for needle in (
        "isEvalSupported: false",
        "enableXfa: false",
        "disableRange: true",
        "disableStream: true",
        "workerSrc",
    ):
        expect(needle in js, f"pdfview.js lacks {needle!r}")
    for banned in ("eval(", "new Function", "innerHTML", "document.write"):
        expect(banned not in js, f"pdfview.js contains {banned!r}")
    passed("g: pdfview.js has the pdf.js options and workerSrc; no eval, innerHTML, document.write")


def main() -> None:
    w = S3.World()
    pdf = S3.make_pdf(2, 300)
    ids = {
        "pdf": upload(w, w.open_item, "two.pdf", pdf, "application/pdf"),
        "text": upload(w, w.open_item, "notes.txt", b"notes\n" * 20, "text/plain"),
        "huge": upload(
            w, w.open_item, "huge.pdf", b"%PDF-" + b"\0" * (MAX_BYTES + 1 - 5), "application/pdf"
        ),
        "hidden": upload(
            w, w.restricted_item, "hidden.pdf", S3.make_pdf(2, 320), "application/pdf"
        ),
    }
    bob = w.web_session("bob")
    ctl = w.web_session("ctl")
    html = check_pdf_page(w, ids["pdf"], bob)
    check_markup(w, ids["pdf"], bob, html)
    check_other_files(w, ids, bob)
    check_hidden(w, ids, bob, ctl)
    check_no_cookie(w, ids)
    check_bytes(w, ids, bob, html, pdf)
    check_script()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as failure:
        print(f"FAIL {failure}")
        sys.exit(1)
