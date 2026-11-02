"""The file bytes and page 1 for a cookie session: the web mirrors of two JSON routes (P2-WEB1-S3).

``/web/files/{id}/content`` and ``/web/files/{id}/page1.png`` run the JSON route's own function
with the same file, scope and actor, so there is one visibility path: open the file under the
viewer, then everything else. The JSON routes' own tests are in
``packages/tl-api/tests/test_api_page1.py``.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
from tl_api.preview import render
from tl_api.routes import files as file_routes

PNG = b"\x89PNG\r\n\x1a\n"
SCOPE_Q = "?scope=project%3AP123"


@pytest.fixture(scope="module")
def files(world: Any, k: Any) -> dict[str, Any]:
    """Files on the open item, and on the restricted item (one with the bytes of ``pdf_a``)."""
    blobs = {
        "pdf_a": k.make_pdf(2, 300),
        "pdf_b": k.make_pdf(3, 310),
        "hidden_fresh": k.make_pdf(4, 320),
        "fake_pdf": b"this is plain text, not a PDF\n" * 20,
        "text": b"notes\n" * 20,
        "tiny": b"%PDF-" + b"\0" * 80,
    }
    open_item, restricted = world.ids["open"], world.ids["restricted"]
    ids = {
        "pdf_a": world.upload(open_item, "a.pdf", blobs["pdf_a"]),
        "pdf_b": world.upload(open_item, "b.pdf", blobs["pdf_b"]),
        "fake_pdf": world.upload(open_item, "fake.pdf", blobs["fake_pdf"]),
        "text": world.upload(open_item, "notes.txt", blobs["text"], "text/plain"),
        "tiny": world.upload(open_item, "tiny.pdf", blobs["tiny"]),
        "hidden_same": world.upload(restricted, "same.pdf", blobs["pdf_a"]),
        "hidden_fresh": world.upload(restricted, "fresh.pdf", blobs["hidden_fresh"]),
    }
    return {"ids": ids, "blobs": blobs}


def page1(file_id: str) -> str:
    return f"/web/files/{file_id}/page1.png{SCOPE_Q}"


def content(file_id: str) -> str:
    return f"/web/files/{file_id}/content{SCOPE_Q}"


def test_the_web_gives_the_picture_with_the_web_policy(world: Any, files: Any, k: Any) -> None:
    png = world.web("bob").client.get(page1(files["ids"]["pdf_a"]))
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png" and png.content.startswith(PNG)
    assert png.headers["content-security-policy"] == k.CSP
    assert png.headers["cache-control"] == "private"


def test_the_web_gives_the_bytes_as_an_attachment(world: Any, files: Any, k: Any) -> None:
    body = world.web("bob").client.get(content(files["ids"]["pdf_a"]))
    assert body.status_code == 200 and body.content == files["blobs"]["pdf_a"]
    assert body.headers["content-disposition"].startswith("attachment")
    assert body.headers["cache-control"].startswith("private")
    assert body.headers["content-security-policy"] == k.CSP


@pytest.mark.parametrize("suffix", ["page1.png", "content"])
@pytest.mark.parametrize("which", ["hidden_same", "never"])
def test_a_hidden_or_unknown_file_is_the_json_404_of_the_api(
    world: Any, files: Any, k: Any, suffix: str, which: str
) -> None:
    file_id = files["ids"]["hidden_same"] if which == "hidden_same" else k.NEVER
    mirrored = world.web("bob").client.get(f"/web/files/{file_id}/{suffix}{SCOPE_Q}")
    direct = world.api("bob").get(f"/files/{file_id}/{suffix}{SCOPE_Q}")
    assert mirrored.status_code == direct.status_code == 404
    assert mirrored.json() == direct.json()
    assert mirrored.headers["content-type"].startswith("application/json")  # not an HTML page


@pytest.mark.parametrize("suffix", ["page1.png", "content"])
def test_no_cookie_is_a_redirect_and_an_agent_token_is_401(
    world: Any, files: Any, suffix: str
) -> None:
    url = f"/web/files/{files['ids']['pdf_a']}/{suffix}{SCOPE_Q}"
    anon = world.client().get(url)
    assert anon.status_code == 303 and anon.headers["location"] == "/web/sign-in"
    assert world.client(world.agent_token).get(url).status_code == 401


def test_a_hidden_file_is_404_before_the_cache_and_no_child_starts(
    world: Any, files: Any, k: Any, started: list[list[str]]
) -> None:
    ids = files["ids"]
    ctl, bob = world.web("ctl").client, world.web("bob").client
    assert bob.get(page1(ids["pdf_a"])).status_code == 200  # warm the cache (the bytes of ...)
    assert ctl.get(page1(ids["hidden_same"])).status_code == 200  # ... the restricted file
    before = len(started)
    cached, fresh, never = (
        bob.get(page1(ids["hidden_same"])),
        bob.get(page1(ids["hidden_fresh"])),
        bob.get(page1(k.NEVER)),
    )
    assert cached.status_code == fresh.status_code == never.status_code == 404
    assert cached.text.replace(ids["hidden_same"], k.NEVER) == never.text
    assert fresh.text.replace(ids["hidden_fresh"], k.NEVER) == never.text
    assert len(started) == before


def test_the_second_call_is_a_cache_hit_and_starts_no_child(
    world: Any, files: Any, started: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    web = world.web("bob").client
    first = web.get(page1(files["ids"]["pdf_b"]))
    assert first.status_code == 200 and len(started) == 1
    monkeypatch.setattr(render, "WORKER_COMMAND", (sys.executable, "-c", "import sys; sys.exit(3)"))
    second = web.get(page1(files["ids"]["pdf_b"]))
    assert second.status_code == 200 and second.content == first.content
    assert len(started) == 1


@pytest.mark.parametrize("which", ["fake_pdf", "text", "tiny"])
def test_a_file_that_cannot_be_drawn_is_404_no_preview(
    world: Any,
    files: Any,
    started: list[list[str]],
    copies: list[str],
    monkeypatch: pytest.MonkeyPatch,
    which: str,
) -> None:
    if which == "tiny":  # over the limit: shrink the limit rather than upload 50 MB
        monkeypatch.setattr(render, "MAX_BYTES", 64)
    response = world.web("bob").client.get(page1(files["ids"][which]))
    assert response.status_code == 404 and response.json()["error"] == "no_preview"
    assert response.json()["message"] == file_routes.NO_PREVIEW_TEXT
    assert started == [] and copies == []


def test_busy_is_503_with_retry_after_and_a_cache_hit_is_still_200(
    world: Any, files: Any, started: list[list[str]]
) -> None:
    web = world.web("bob").client
    assert web.get(page1(files["ids"]["pdf_a"])).status_code == 200
    slots = file_routes.RENDER_SLOTS
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    try:
        before = len(started)
        busy = web.get(page1(files["ids"]["pdf_b"]))
        assert busy.status_code == 503 and busy.json()["error"] == "preview_busy"
        assert busy.headers.get("retry-after") == "2"
        assert web.get(page1(files["ids"]["pdf_a"])).status_code == 200  # a hit takes no slot
        assert len(started) == before
    finally:
        slots.release()
        slots.release()


def test_the_cookie_alone_is_401_on_the_json_route(world: Any, files: Any) -> None:
    cookie = world.web("bob").token
    response = world.client(cookie).get(
        f"/files/{files['ids']['pdf_a']}/page1.png?scope=project:P123"
    )
    assert response.status_code == 401
