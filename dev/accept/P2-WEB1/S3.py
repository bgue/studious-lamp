"""Acceptance script for P2-WEB1 S3: page 1 of a PDF on the server, and the web file mirrors.

Runs on SQLite with a temp ledger, a temp object store and a temp picture cache, under
``TL_ENV=test``, with the FastAPI TestClient on ``http://127.0.0.1``. Prints one ``PASS <check>``
line per check; exits 0 when every check passes, 1 on the first failure. Expected values come from
the spec text (``docs/tickets/P2-WEB1/S3-server-page1.md``), never from the code under test.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

os.environ["TL_ENV"] = "test"
os.environ["TL_WEB_SECRET"] = "web-secret-for-acceptance-0123456789abcdef"
for _name in ("TL_WEB", "TL_WEB_ORIGIN", "TL_PROJECT", "TL_SCHEMA_DIR"):
    os.environ.pop(_name, None)
WORK = Path(tempfile.mkdtemp(prefix="tl-accept-s3-"))
os.environ["XDG_CACHE_HOME"] = str(WORK / "cache")

import pypdfium2 as pdfium  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import create_schema  # noqa: E402
from tl_adapters.objectstore.fs import FsObjectStore  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.ratelimit import SourceLimiter  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth import accounts, sessions  # noqa: E402
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload  # noqa: E402
from tl_mod_correspondence.confseed import seed_hidden_world  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
OWN = "http://127.0.0.1"
SCOPE = "project:P123"
PNG = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 50 * 1024 * 1024  # the spec: over 50 MB is not rendered
CSP = (  # the web policy (spec web-client-i1 section 5), written out again
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)
NEVER = "01J000000000000000000000"


def passed(check: str) -> None:
    print(f"PASS {check}")


def expect(condition: bool, what: str) -> None:
    if not condition:
        raise AssertionError(what)


def make_pdf(pages: int, width: float) -> bytes:
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(width, 400)
    target = WORK / f"made-{pages}-{int(width)}.pdf"
    document.save(str(target))
    return target.read_bytes()


# every child process the renderer starts is counted here
STARTED: list[list[str]] = []
_real_popen = subprocess.Popen


def _spy(argv: Any, *args: Any, **kwargs: Any) -> Any:
    STARTED.append(list(argv))
    return _real_popen(argv, *args, **kwargs)


subprocess.Popen = _spy  # type: ignore[misc,assignment]

# every private copy of a file's bytes made for the renderer is counted here
COPIES: list[str] = []
_real_tempdir = tempfile.TemporaryDirectory


def _tempdir_spy(*args: Any, **kwargs: Any) -> Any:
    COPIES.append(str(kwargs.get("prefix", "")))
    return _real_tempdir(*args, **kwargs)


tempfile.TemporaryDirectory = _tempdir_spy  # type: ignore[misc,assignment]

from tl_api.preview import render as api_render  # noqa: E402
from tl_api.routes import files as file_routes  # noqa: E402


class World:
    def __init__(self) -> None:
        self.db = WORK / "ledger.db"
        create_schema(self.db)
        self.backend = open_backend(self.db)
        store = FsObjectStore(WORK / "objects", secret=b"k")
        self.service = FileService(store, secret=b"s", scan_inline=True)
        with self.backend(False) as uow:
            for name, role in (("bob", "user"), ("ctl", "document_controller")):
                accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="person", roles=[role],
                    password=prepare_password(PASSWORD, username=name), by="svc:accept",
                )  # fmt: skip
            bot = accounts.create_account(
                uow, username="bot", display_name="Bot", kind="agent", roles=["user"],
                password=None, by="svc:accept",
            )  # fmt: skip
            _, self.agent_token = accounts.issue_agent_token(
                uow, account_id=bot.account_id, label="accept",
                expires_at=datetime.now(UTC) + timedelta(days=1), by="svc:accept",
            )  # fmt: skip
        tokens_path = WORK / "tokens.json"
        settings = ApiSettings(db_path=self.db, tokens_path=tokens_path)
        self.app = create_app(
            self.backend, settings=settings, tokens=TokenStore(tokens_path),
            files_service=self.service, object_store=store, source_limiter=SourceLimiter(10_000),
        )  # fmt: skip
        self.hidden = seed_hidden_world(self.db, self.service, WORK)
        self.open_item = self.hidden.ids["open"]
        self.restricted_item = self.hidden.ids["restricted"]
        self.bearer = {
            n: sessions.sign_in(self.backend, username=n, password=PASSWORD)[1]
            for n in ("bob", "ctl")
        }

    def upload(self, record_id: str, filename: str, data: bytes) -> str:
        with cf.system_view():  # the seeder sees every item, as the module that owns it does
            return self._upload(record_id, filename, data)

    def _upload(self, record_id: str, filename: str, data: bytes) -> str:
        with self.backend(False) as uow:
            ticket = self.service.register_upload(
                uow,
                RegisterUpload(
                    actor="user:ctl", source="test", scope=SCOPE, record_id=record_id, slot=None,
                    filename=filename, content_type="application/pdf", size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                ),
                by_module=True,
            )  # fmt: skip
        with self.backend(False) as uow:
            done = self.service.complete_upload(
                uow,
                CompleteUpload(
                    actor="user:ctl", source="test", scope=SCOPE, upload_id=ticket.upload_id
                ),
                io.BytesIO(data),
                by_module=True,
            )
        return done.file_id

    def client(self, bearer: str | None = None, cookie: str | None = None) -> TestClient:
        client = TestClient(self.app, base_url=OWN, follow_redirects=False)
        if bearer is not None:
            client.headers["Authorization"] = f"Bearer {bearer}"
        if cookie is not None:
            client.headers["Cookie"] = f"tl_session={cookie}"
        return client

    def web_session(self, username: str) -> str:
        response = self.client().post(
            "/web/sign-in", data={"username": username, "password": PASSWORD}
        )
        expect(response.status_code == 303, f"sign-in {response.status_code}")
        return response.headers["set-cookie"].split(";")[0].partition("=")[2]


def path(file_id: str) -> str:
    return f"/files/{file_id}/page1.png?scope={SCOPE}"


def check_move() -> None:
    from tl_api.preview import _worker as api_worker
    from tl_api.preview import cache as api_cache
    from tl_tui.preview import _worker, cache, render

    expect(render is api_render, "tl_tui.preview.render is not the tl_api module")
    expect(cache is api_cache, "tl_tui.preview.cache is not the tl_api module")
    expect(_worker is api_worker, "tl_tui.preview._worker is not the tl_api module")
    expect(api_render.WORKER_COMMAND[-1] == "tl_api.preview._worker", "worker command")
    expect(api_render.WORKER_COMMAND[:3] == (sys.executable, "-I", "-m"), "worker command flags")
    for name in ("render", "_worker", "cache"):
        alias = ROOT / "packages/tl-tui/src/tl_tui/preview" / f"{name}.py"
        lines = len(alias.read_text().splitlines())
        expect(lines <= 12, f"{alias.name} has {lines} lines")
    passed("a: tl_tui preview modules are the tl_api modules; worker command; aliases <= 12 lines")


def check_json_route(w: World, ids: dict[str, str]) -> None:
    ctl = w.client(w.bearer["ctl"])
    first = ctl.get(path(ids["pdf_a"]))
    expect(first.status_code == 200, f"first call {first.status_code} {first.text[:200]}")
    expect(first.headers["content-type"] == "image/png", "content type")
    expect(first.headers["cache-control"] == "private", f"cache-control {first.headers}")
    expect(first.content.startswith(PNG), "not a PNG")
    expect(len(STARTED) == 1, f"first call started {len(STARTED)} children")
    api_render.WORKER_COMMAND = (sys.executable, "-c", "import sys; sys.exit(3)")
    second = ctl.get(path(ids["pdf_a"]))
    expect(second.status_code == 200 and second.content == first.content, "cached second call")
    expect(len(STARTED) == 1, "the second call started a child")
    passed("b: 200 image/png, Cache-Control: private; the second call is a cache hit, no child")


def check_hidden_before_cache(w: World, ids: dict[str, str]) -> None:
    ctl, bob = w.client(w.bearer["ctl"]), w.client(w.bearer["bob"])
    before = len(STARTED)
    # the hidden file holds the bytes of pdf_a, whose picture is in the cache now
    seen = ctl.get(path(ids["hidden_same"]))
    expect(seen.status_code == 200, f"the controller reads the restricted file: {seen.status_code}")
    hidden = bob.get(path(ids["hidden_same"]))
    fresh = bob.get(path(ids["hidden_fresh"]))
    never = bob.get(path(NEVER))
    for name, response in (("cached", hidden), ("fresh", fresh), ("never", never)):
        expect(response.status_code == 404, f"hidden {name}: {response.status_code}")
        expect(response.headers["content-type"].startswith("application/json"), name)
    for name, response, file_id in (
        ("cached", hidden, ids["hidden_same"]),
        ("fresh", fresh, ids["hidden_fresh"]),
    ):
        expect(
            response.text.replace(file_id, NEVER) == never.text, f"{name} differs: {response.text}"
        )
    expect(len(STARTED) == before, "a child was started for a hidden or unknown file")
    passed("c: a hidden file is the same 404 as an unknown id, cached or not; no child")


def check_not_renderable(w: World, ids: dict[str, str]) -> None:
    ctl = w.client(w.bearer["ctl"])
    before, copies = len(STARTED), len(COPIES)
    bodies = []
    for name in ("fake_pdf", "text", "huge"):
        response = ctl.get(path(ids[name]))
        expect(response.status_code == 404, f"{name}: {response.status_code}")
        expect(response.json()["error"] == "no_preview", f"{name}: {response.text}")
        bodies.append(response.json())
    expect(all(b == bodies[0] for b in bodies), "the no_preview text differs between reasons")
    expect(len(STARTED) == before, "a child was started for a file that is not renderable")
    expect(len(COPIES) == copies, "the bytes of a file that is not renderable were copied out")
    passed("d: no %PDF- header, not a PDF, over 50 MB: 404 no_preview, one text, no child")


def check_busy(w: World, ids: dict[str, str]) -> None:
    ctl = w.client(w.bearer["ctl"])
    slots = file_routes.RENDER_SLOTS
    expect(slots.acquire(blocking=False) and slots.acquire(blocking=False), "could not hold slots")
    try:
        before = len(STARTED)
        busy = ctl.get(path(ids["pdf_b"]))  # not in the cache
        expect(busy.status_code == 503, f"busy: {busy.status_code}")
        expect(busy.json()["error"] == "preview_busy", busy.text)
        expect(busy.headers.get("retry-after") == "2", f"Retry-After {busy.headers}")
        hit = ctl.get(path(ids["pdf_a"]))
        expect(hit.status_code == 200 and hit.content.startswith(PNG), "a cache hit while busy")
        expect(len(STARTED) == before, "a child started while the slots were held")
    finally:
        slots.release()
        slots.release()
    api_render.WORKER_COMMAND = _GOOD_COMMAND
    again = ctl.get(path(ids["pdf_b"]))
    expect(again.status_code == 200, f"after release: {again.status_code}")
    passed("e: two slots held: third render 503 preview_busy, Retry-After: 2; a cache hit is 200")


def check_web(w: World, ids: dict[str, str], blobs: dict[str, bytes]) -> None:
    cookie = w.web_session("bob")
    web = w.client(cookie=cookie)
    api = w.client(w.bearer["bob"])
    scope = f"?scope={SCOPE}"
    png = web.get(f"/web/files/{ids['pdf_a']}/page1.png{scope}")
    expect(png.status_code == 200, f"web page1 {png.status_code} {png.text[:200]}")
    expect(png.headers["content-type"] == "image/png" and png.content.startswith(PNG), "web png")
    expect(png.headers["content-security-policy"] == CSP, "web CSP on the picture")
    expect(png.headers["cache-control"] == "private", f"web png cache {png.headers}")
    body = web.get(f"/web/files/{ids['pdf_a']}/content{scope}")
    expect(body.status_code == 200 and body.content == blobs["pdf_a"], "web content bytes")
    expect(body.headers["content-disposition"].startswith("attachment"), "web attachment")
    expect(body.headers["cache-control"].startswith("private"), f"web content {body.headers}")
    expect(body.headers["content-security-policy"] == CSP, "web CSP on the bytes")
    for suffix in ("page1.png", "content"):
        for file_id in (ids["hidden_same"], NEVER):
            mirrored = web.get(f"/web/files/{file_id}/{suffix}{scope}")
            direct = api.get(
                f"/files/{file_id}/{'content' if suffix == 'content' else 'page1.png'}{scope}"
            )
            expect(mirrored.status_code == direct.status_code == 404, f"{suffix} {file_id}")
            expect(mirrored.json() == direct.json(), f"{suffix}: the JSON bodies differ")
        anon = w.client().get(f"/web/files/{ids['pdf_a']}/{suffix}{scope}")
        expect(anon.status_code == 303, f"no cookie {suffix}: {anon.status_code}")
        expect(anon.headers["location"] == "/web/sign-in", "redirect target")
        agent = w.client(cookie=w.agent_token).get(f"/web/files/{ids['pdf_a']}/{suffix}{scope}")
        expect(agent.status_code == 401, f"agent token {suffix}: {agent.status_code}")
    passed("f: web mirrors give the bytes and the PNG (CSP), hidden is the JSON 404, 303 / 401")


def check_cookie_only_on_web(w: World, ids: dict[str, str]) -> None:
    cookie = w.web_session("bob")
    response = w.client(cookie=cookie).get(path(ids["pdf_a"]))
    expect(response.status_code == 401, f"cookie on the JSON route: {response.status_code}")
    passed("g: the cookie alone is 401 on /files/{id}/page1.png")


def check_openapi() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "tl_api.openapi", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    expect(done.returncode == 0 and not done.stdout.strip(), f"openapi --check: {done.stdout}")
    base = subprocess.run(
        ["git", "merge-base", "HEAD", "p2/web1"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    old = subprocess.run(
        ["git", "show", f"{base}:docs/reference/openapi.json"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    new = (ROOT / "docs/reference/openapi.json").read_text()
    added = set(json.loads(new)["paths"]) - set(json.loads(old)["paths"])
    gone = set(json.loads(old)["paths"]) - set(json.loads(new)["paths"])
    expect(added == {"/files/{file_id}/page1.png"} and not gone, f"paths added {added} gone {gone}")
    passed("h: openapi --check is silent; the diff adds /files/{file_id}/page1.png")


_GOOD_COMMAND = api_render.WORKER_COMMAND


def main() -> None:
    check_move()
    w = World()
    blobs = {
        "pdf_a": make_pdf(2, 300),
        "pdf_b": make_pdf(3, 310),
        "hidden_fresh": make_pdf(4, 320),
        "fake_pdf": b"this is plain text, not a PDF\n" * 20,
        "text": b"notes\n" * 20,
        "huge": b"%PDF-" + b"\0" * (MAX_BYTES + 1 - 5),
    }
    ids = {
        "pdf_a": w.upload(w.open_item, "a.pdf", blobs["pdf_a"]),
        "pdf_b": w.upload(w.open_item, "b.pdf", blobs["pdf_b"]),
        "fake_pdf": w.upload(w.open_item, "fake.pdf", blobs["fake_pdf"]),
        "text": w.upload(w.open_item, "notes.txt", blobs["text"]),
        "huge": w.upload(w.open_item, "huge.pdf", blobs["huge"]),
        "hidden_same": w.upload(w.restricted_item, "same.pdf", blobs["pdf_a"]),
        "hidden_fresh": w.upload(w.restricted_item, "fresh.pdf", blobs["hidden_fresh"]),
    }
    check_json_route(w, ids)
    check_hidden_before_cache(w, ids)
    check_not_renderable(w, ids)
    api_render.WORKER_COMMAND = _GOOD_COMMAND
    check_busy(w, ids)
    check_web(w, ids, blobs)
    check_cookie_only_on_web(w, ids)
    check_openapi()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as failure:
        print(f"FAIL {failure}")
        sys.exit(1)
