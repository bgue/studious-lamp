"""``GET /files/{file_id}/page1.png``: page 1 of a PDF, drawn on the server (P2-WEB1-S3).

The file is opened under the viewer first; only then are the size, the ``%PDF-`` header and the
picture cache looked at, so the bytes of a file the viewer may not see never reach the renderer
and a cached picture never leaks one. Ports of the checks a to e and g of the S3 script (the web
mirrors are in ``packages/tl-web/tests/test_web_files.py``).
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.preview import render
from tl_api.routes import files as file_routes
from tl_core import confidentiality as cf
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.files.service import CompleteUpload, RegisterUpload
from tl_mod_correspondence.confseed import Hidden, seed_hidden_world

ROOT = Path(__file__).resolve().parents[3]
SCOPE = "project:P123"
PASSWORD = "correct horse battery"
PNG = b"\x89PNG\r\n\x1a\n"
NEVER = "01J000000000000000000000"


def make_pdf(folder: Path, pages: int, width: float) -> bytes:
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(width, 400)
    target = folder / f"made-{pages}-{int(width)}.pdf"
    document.save(str(target))
    return target.read_bytes()


class World:
    """The harness, a controller who reads everything, a plain user who reads the open item."""

    def __init__(self, h: Harness, tmp_path: Path) -> None:
        self.h = h
        with h.backend(False) as uow:
            for name, role in (("bob", "user"), ("ctl", "document_controller")):
                accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="person", roles=[role],
                    password=prepare_password(PASSWORD, username=name), by="svc:test",
                )  # fmt: skip
        self.tokens = {
            n: sessions.sign_in(h.backend, username=n, password=PASSWORD)[1] for n in ("bob", "ctl")
        }
        self.hidden: Hidden = seed_hidden_world(h.target or h.db, h.service, tmp_path)
        self.open_item = self.hidden.ids["open"]
        self.restricted_item = self.hidden.ids["restricted"]

    def upload(self, record_id: str, filename: str, data: bytes) -> str:
        with cf.system_view():  # the seeder sees every item, as the module that owns it does
            with self.h.backend(False) as uow:
                ticket = self.h.service.register_upload(
                    uow,
                    RegisterUpload(
                        actor="user:ctl", source="test", scope=SCOPE, record_id=record_id,
                        slot=None, filename=filename, content_type="application/pdf",
                        size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                    ),
                    by_module=True,
                )  # fmt: skip
            with self.h.backend(False) as uow:
                done = self.h.service.complete_upload(
                    uow,
                    CompleteUpload(
                        actor="user:ctl", source="test", scope=SCOPE, upload_id=ticket.upload_id
                    ),
                    io.BytesIO(data),
                    by_module=True,
                )
        return done.file_id

    def get(self, who: str | None, file_id: str, *, cookie: str | None = None) -> Any:
        client = TestClient(self.h.app, base_url="http://127.0.0.1", follow_redirects=False)
        if who is not None:
            client.headers["Authorization"] = f"Bearer {self.tokens[who]}"
        if cookie is not None:
            client.headers["Cookie"] = f"tl_session={cookie}"
        return client.get(f"/files/{file_id}/page1.png?scope={SCOPE}")


@pytest.fixture
def w(harness: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))  # a private picture cache
    return World(harness, tmp_path)


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every child process the renderer starts."""
    calls: list[list[str]] = []
    real = subprocess.Popen

    def spy(argv: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(list(argv))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    return calls


@pytest.fixture
def copies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every private copy of a file's bytes made for the renderer."""
    made: list[str] = []
    real = tempfile.TemporaryDirectory

    def spy(*args: Any, **kwargs: Any) -> Any:
        made.append(str(kwargs.get("prefix", "")))
        return real(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", spy)
    return made


def test_the_preview_modules_of_the_terminal_are_the_api_modules() -> None:
    from tl_api.preview import _worker as api_worker
    from tl_api.preview import cache as api_cache
    from tl_tui.preview import _worker, cache
    from tl_tui.preview import render as tui_render

    assert tui_render is render and cache is api_cache and _worker is api_worker
    assert render.WORKER_COMMAND[-1] == "tl_api.preview._worker"
    assert render.WORKER_COMMAND[:3] == (sys.executable, "-I", "-m")
    assert render.MAX_BYTES == 50 * 1024 * 1024  # the spec: over 50 MB is not rendered


def test_page1_is_a_png_and_the_second_call_is_a_cache_hit(
    w: World, tmp_path: Path, started: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    file_id = w.upload(w.open_item, "a.pdf", make_pdf(tmp_path, 2, 300))
    first = w.get("ctl", file_id)
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert first.headers["cache-control"] == "private"
    assert first.content.startswith(PNG)
    assert len(started) == 1
    monkeypatch.setattr(render, "WORKER_COMMAND", (sys.executable, "-c", "import sys; sys.exit(3)"))
    second = w.get("ctl", file_id)
    assert second.status_code == 200 and second.content == first.content
    assert len(started) == 1  # no second child


def test_a_hidden_file_is_the_same_404_as_an_unknown_id_cached_or_not(
    w: World, tmp_path: Path, started: list[list[str]]
) -> None:
    blob = make_pdf(tmp_path, 2, 300)
    open_file = w.upload(w.open_item, "a.pdf", blob)
    cached = w.upload(w.restricted_item, "same.pdf", blob)  # the bytes of a file in the cache
    fresh = w.upload(w.restricted_item, "fresh.pdf", make_pdf(tmp_path, 4, 320))
    assert w.get("ctl", open_file).status_code == 200  # warm the cache as the allowed reader
    assert w.get("ctl", cached).status_code == 200  # the controller reads the restricted file
    before = len(started)
    answers = {
        "cached": (w.get("bob", cached), cached),
        "fresh": (w.get("bob", fresh), fresh),
    }
    never = w.get("bob", NEVER)
    assert never.status_code == 404
    assert never.headers["content-type"].startswith("application/json")
    for name, (response, file_id) in answers.items():
        assert response.status_code == 404, name
        assert response.headers["content-type"].startswith("application/json"), name
        assert response.text.replace(file_id, NEVER) == never.text, name
    assert len(started) == before  # no child for a hidden or unknown file


@pytest.mark.parametrize("kind", ["fake_pdf", "text", "huge"])
def test_a_file_that_cannot_be_drawn_is_one_404_and_starts_nothing(
    w: World,
    started: list[list[str]],
    copies: list[str],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    if kind == "huge":  # the limit is pinned to 50 MB above; shrink it rather than upload 50 MB
        monkeypatch.setattr(render, "MAX_BYTES", 64)
    blobs = {
        "fake_pdf": b"this is plain text, not a PDF\n" * 20,
        "text": b"notes\n" * 20,
        "huge": b"%PDF-" + b"\0" * 80,
    }
    file_id = w.upload(w.open_item, f"{kind}.pdf", blobs[kind])
    before, made = len(started), len(copies)
    response = w.get("ctl", file_id)
    assert response.status_code == 404
    assert response.json()["error"] == "no_preview"
    assert response.json()["message"] == file_routes.NO_PREVIEW_TEXT  # one text for every reason
    assert len(started) == before  # no child
    assert len(copies) == made  # the bytes were not copied out


def test_when_both_slots_are_taken_a_render_is_503_and_a_cache_hit_is_200(
    w: World, tmp_path: Path, started: list[list[str]]
) -> None:
    cached = w.upload(w.open_item, "a.pdf", make_pdf(tmp_path, 2, 300))
    other = w.upload(w.open_item, "b.pdf", make_pdf(tmp_path, 3, 310))
    assert w.get("ctl", cached).status_code == 200
    slots = file_routes.RENDER_SLOTS
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    try:
        before = len(started)
        busy = w.get("ctl", other)  # not in the cache
        assert busy.status_code == 503
        assert busy.json()["error"] == "preview_busy"
        assert busy.headers.get("retry-after") == "2"
        hit = w.get("ctl", cached)
        assert hit.status_code == 200 and hit.content.startswith(PNG)
        assert len(started) == before  # nothing started while the slots were held
    finally:
        slots.release()
        slots.release()
    assert w.get("ctl", other).status_code == 200  # after the release it draws


def test_the_session_cookie_alone_is_401_on_the_json_route(w: World, tmp_path: Path) -> None:
    file_id = w.upload(w.open_item, "a.pdf", make_pdf(tmp_path, 1, 300))
    cookie = w.tokens["bob"]
    assert w.get(None, file_id, cookie=cookie).status_code == 401


def test_the_committed_openapi_lists_page1_and_no_web_route() -> None:
    document = json.loads((ROOT / "docs" / "reference" / "openapi.json").read_text())
    assert "/files/{file_id}/page1.png" in document["paths"]
    assert not [p for p in document["paths"] if p.startswith("/web")]
