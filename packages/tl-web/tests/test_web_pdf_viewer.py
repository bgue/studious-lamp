"""The full PDF viewer ``GET /web/p/{project}/files/{file_id}/view`` and ``pdfview.js`` (T05).

A PDF of at most ``MAX_VIEW_BYTES`` gets the pdf.js viewer; anything else gets the filename and a
download link only. The page holds no script text and no ``on*`` attribute, the policy has no
``unsafe-eval`` and no ``unsafe-inline`` for scripts, and the vendored pdf.js is at or above 4.2.67
(CVE-2024-4367) with the hashes of the manifest. ``pdfview.js`` is not run in a browser here; its
text is read for the options that switch off the risky features of pdf.js.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import quote

import pytest
from tl_web.pages import viewer
from tl_web.reads import WebReadClient

WEB = Path(__file__).resolve().parents[1] / "src" / "tl_web"
VENDOR = WEB / "static" / "vendor"
SCOPE_Q = quote("project:P123", safe="")
WORKER = "/web/static/vendor/pdfjs/pdf.worker.min.mjs"
MAX_BYTES = 50 * 1024 * 1024  # the spec: over 50 MB is not viewed


def view_path(file_id: str) -> str:
    return f"/web/p/P123/files/{file_id}/view"


def download_href(file_id: str) -> str:
    return f'href="/web/files/{file_id}/content?scope={SCOPE_Q}"'


@pytest.fixture(scope="module")
def stored(world: Any, k: Any) -> dict[str, Any]:
    pdf = k.make_pdf(2, 300)
    open_item, restricted = world.ids["open"], world.ids["restricted"]
    ids = {
        "pdf": world.upload(open_item, "two.pdf", pdf),
        "text": world.upload(open_item, "notes.txt", b"notes\n" * 20, "text/plain"),
        "binary": world.upload(
            open_item, "drawing.dwg", b"\x00\x01" * 30, "application/octet-stream"
        ),
        "named": world.upload(
            open_item, "SCAN.PDF", k.make_pdf(1, 200), "application/octet-stream"
        ),
        "hidden": world.upload(restricted, "hidden.pdf", k.make_pdf(2, 320)),
    }
    return {"ids": ids, "pdf": pdf}


def test_a_pdf_gets_the_viewer_with_scoped_data_attributes(
    world: Any, stored: Any, htmlkit: Any
) -> None:
    file_id = stored["ids"]["pdf"]
    response = world.web("bob").client.get(view_path(file_id))
    assert response.status_code == 200
    page = htmlkit.parse(response.text)
    node = page.by_id("pdf-view")
    assert response.text.count('id="pdf-view"') == 1 and node is not None
    assert node.get("data-src") == f"/web/files/{file_id}/content?scope={SCOPE_Q}"
    assert node.get("data-worker") == WORKER
    assert download_href(file_id) in response.text
    assert '<script type="module" src="/web/static/pdfview.js"></script>' in response.text


def test_the_page_has_no_inline_script_no_style_and_no_on_attribute(
    world: Any, stored: Any, htmlkit: Any
) -> None:
    text = world.web("bob").client.get(view_path(stored["ids"]["pdf"])).text
    for attrs, body in re.findall(r"<script\b([^>]*)>(.*?)</script>", text, re.S):
        assert re.search(r"\ssrc=", attrs), f"script without src: {attrs!r}"
        assert body.strip() == "", f"inline script body: {body[:80]!r}"
    assert len(re.findall(r"<script\b", text)) == len(re.findall(r"</script>", text))
    assert re.search(r"\sstyle\s*=", text) is None
    assert re.search(r"\son[a-z]+\s*=", text, re.I) is None
    assert htmlkit.parse(text).inline_problems() == []


def test_the_policy_has_no_unsafe_eval_and_no_unsafe_inline_for_scripts(
    world: Any, stored: Any, k: Any
) -> None:
    csp = (
        world.web("bob")
        .client.get(view_path(stored["ids"]["pdf"]))
        .headers["content-security-policy"]
    )
    assert csp == k.CSP
    assert "unsafe-eval" not in csp
    script_src = next(d for d in csp.split(";") if d.strip().startswith("script-src"))
    assert script_src.strip() == "script-src 'self'"  # nothing else: no unsafe-inline, no host
    assert "wasm-unsafe-eval" not in csp


@pytest.mark.parametrize("which", ["text", "binary"])
def test_a_file_that_is_not_a_pdf_gets_its_name_and_a_download_link_only(
    world: Any, stored: Any, which: str
) -> None:
    file_id = stored["ids"][which]
    response = world.web("bob").client.get(view_path(file_id))
    assert response.status_code == 200
    assert download_href(file_id) in response.text
    assert 'id="pdf-view"' not in response.text and "pdfview.js" not in response.text


def test_a_pdf_by_its_name_is_still_a_pdf(world: Any, stored: Any) -> None:
    response = world.web("bob").client.get(view_path(stored["ids"]["named"]))
    assert 'id="pdf-view"' in response.text  # the name SCAN.PDF, whatever the type says


def test_a_pdf_over_the_limit_gets_a_download_link_only_and_the_limit_itself_is_viewed(
    world: Any, stored: Any
) -> None:
    file_id = stored["ids"]["pdf"]
    assert viewer.MAX_VIEW_BYTES == MAX_BYTES
    real = WebReadClient.file_info

    def declared(size: int) -> Any:
        def info(self: WebReadClient, scope: str, fid: str) -> Any:
            return real(self, scope, fid).model_copy(update={"size": size})

        return info

    bob = world.web("bob").client
    with mock.patch.object(WebReadClient, "file_info", declared(MAX_BYTES + 1)):
        over = bob.get(view_path(file_id))
    with mock.patch.object(WebReadClient, "file_info", declared(MAX_BYTES)):
        at_limit = bob.get(view_path(file_id))
    assert over.status_code == 200 and 'id="pdf-view"' not in over.text
    assert download_href(file_id) in over.text and "two.pdf" in over.text
    assert 'id="pdf-view"' in at_limit.text


def test_a_hidden_or_unknown_file_is_the_one_404_page(world: Any, stored: Any, k: Any) -> None:
    bob = world.web("bob").client
    hidden = bob.get(view_path(stored["ids"]["hidden"]))
    never = bob.get(view_path(k.NEVER))
    assert hidden.status_code == never.status_code == 404
    assert hidden.text.replace(stored["ids"]["hidden"], k.NEVER) == never.text
    assert hidden.content == bob.get("/web/nowhere").content  # the same page as any unknown path
    opened = world.web("ctl").client.get(view_path(stored["ids"]["hidden"]))
    assert opened.status_code == 200 and 'id="pdf-view"' in opened.text  # the controller can


def test_no_cookie_is_a_redirect_to_sign_in(world: Any, stored: Any) -> None:
    anon = world.client().get(view_path(stored["ids"]["pdf"]))
    assert anon.status_code == 303 and anon.headers["location"] == "/web/sign-in"


def test_the_data_src_bytes_with_the_same_cookie_have_the_sha256_the_file_info_states(
    world: Any, stored: Any
) -> None:
    file_id = stored["ids"]["pdf"]
    info = world.api("bob").get(f"/files/{file_id}?scope=project:P123")
    assert info.status_code == 200
    stated = info.json()["sha256"]
    assert stated == hashlib.sha256(stored["pdf"]).hexdigest()
    bob = world.web("bob").client
    src = re.search(r'data-src="([^"]+)"', bob.get(view_path(file_id)).text)
    assert src is not None
    fetched = bob.get(src.group(1).replace("&amp;", "&"))
    assert fetched.status_code == 200
    assert hashlib.sha256(fetched.content).hexdigest() == stated


# --- pdfview.js and the vendored files ----------------------------------------------------------


def test_pdfview_js_switches_off_the_risky_features_of_pdf_js() -> None:
    js = (WEB / "static" / "pdfview.js").read_text(encoding="utf-8")
    for needle in ("isEvalSupported: false", "enableXfa: false", "disableRange: true",
                   "disableStream: true", "workerSrc"):  # fmt: skip
        assert needle in js, f"pdfview.js lacks {needle!r}"
    assert "workerSrc = view.dataset.worker" in js  # the worker URL is the page's data-worker
    assert '"/web/static/vendor/pdfjs/pdf.min.mjs"' in js  # and the library is the vendored one
    for banned in ("eval(", "new Function", "innerHTML", "document.write"):
        assert banned not in js, f"pdfview.js contains {banned!r}"


def test_the_vendored_worker_is_served_and_listed_in_the_manifest(world: Any) -> None:
    manifest = tomllib.loads((VENDOR / "VENDORED.toml").read_text(encoding="utf-8"))["file"]
    paths = {e["path"] for e in manifest}
    assert WORKER.removeprefix("/web/static/vendor/") in paths
    served = world.client().get(WORKER)
    assert served.status_code == 200 and served.headers["content-type"].startswith(
        "text/javascript"
    )


def test_pdfjs_is_at_least_4_2_67_and_the_hashes_match_the_manifest() -> None:
    manifest = tomllib.loads((VENDOR / "VENDORED.toml").read_text(encoding="utf-8"))["file"]
    pdfjs = [
        e for e in manifest if e["name"].startswith("pdfjs-dist") and e["path"].endswith(".mjs")
    ]
    assert pdfjs
    for entry in pdfjs:
        version = tuple(int(part) for part in entry["version"].split("."))
        assert version >= (4, 2, 67), f"{entry['name']} {version} is open to CVE-2024-4367"
    for entry in manifest:
        data = (VENDOR / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
    assert b"4.10.38" in (VENDOR / "pdfjs" / "pdf.min.mjs").read_bytes()
