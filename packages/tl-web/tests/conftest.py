"""tl-web test harness: a ledger with something of every class in it, five readers, sessions.

pytest runs in importlib mode (root pyproject), so a test module cannot import a sibling. Everything
the tests share is a fixture here: the ``World`` (ledger, file service, app, readers), the sign-in
client, the PDF upload and the ``htmlkit`` reader (``htmlkit.py`` is a file, loaded by the fixture
through ``importlib.util.spec_from_file_location``). Do not add ``__init__.py`` here.

The ledger is ``seed_hidden_world`` (project ``P123``: correspondence items of four classes, a
privileged and an open RFI, a commercial item, a restricted and an open document, files) plus a few
more RFIs the page tests need (awaiting, closed, draft, restricted, a planted-markup one, and one in
another project). ``MAY_READ`` is the table of the JSON walk in
``packages/tl-api/tests/test_confidentiality_walk.py`` (five readers); ``bob`` is the plain user,
``ctl`` the document controller, ``boss`` the admin, ``amy`` the person named on the privileged
items and ``bot`` the agent.

A world is built once per test module (``world``, read-only tests) or once per test
(``fresh_world``, tests that sign in, sign out, lock an account or run a command). It runs on
SQLite only. The adapter fixtures of the root ``conftest.py`` are usable (``build_world`` takes
any ``DbTarget``), but ``seed_hidden_world`` itself fails on Postgres in this environment before
any web code runs (``AttachFile needs the user access word``; the JSON walk of tl-api,
``test_confidentiality_walk[postgres]``, errors the same way), so no test here is marked
``parity`` (see the report).
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import importlib.util
import io
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tl_adapters.backend import open_backend
from tl_adapters.db import DbTarget, create_schema
from tl_adapters.objectstore.fs import FsObjectStore
from tl_api.app import create_app
from tl_api.ratelimit import SourceLimiter
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core import confidentiality as cf
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.confidentiality import use_viewer, viewer_for
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_mod_correspondence.confseed import Hidden, seed_hidden_world
from tl_mod_correspondence.testing import CorrWorld
from tl_web.reads import WebReadClient

HERE = Path(__file__).resolve().parent
SECRET = "web-secret-for-tests-0123456789abcdef-0123456789"  # 47 bytes
PASSWORD = "correct horse battery"
OWN = "http://127.0.0.1"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
NEVER = "01J000000000000000000000"  # an id nothing has
#: The policy of the spec (section 5), written out again so a change of the code shows here.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)
PLANTED = 'Plant <i>bold</i> & "quoted"'

#: name -> (roles, kind). ``bob`` is the plain user of the scripts' ``alice``.
ACCOUNTS: dict[str, tuple[list[Any], Any]] = {
    "bob": (["user"], "person"),
    "ctl": (["document_controller"], "person"),
    "boss": (["admin"], "person"),
    "amy": (["user"], "person"),
    "bot": (["user"], "agent"),
}
#: What each reader may read, by the kinds of ``seed_hidden_world`` (the table of the JSON walk in
#: ``packages/tl-api/tests/test_confidentiality_walk.py``). The admin is a controller: no agent
#: and no privilege. Only the accounts named on a privileged item read it. A class nobody knows is
#: read by nobody.
MAY_READ: dict[str, set[str]] = {
    "bob": {"open"},
    "ctl": {
        "open", "restricted", "privileged", "document", "file", "commercial", "secret_rfi",
    },
    "boss": {"open", "restricted", "document", "file", "commercial"},
    "amy": {"open", "privileged", "secret_rfi"},
    "bot": {"open"},
}  # fmt: skip
READERS = tuple(MAY_READ)


def iter_routes(routes: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """``(path, route)`` of every real route, through the wrappers of included routers.

    FastAPI 0.14x keeps an included router as one ``_IncludedRouter`` entry of ``app.routes``
    (``original_router``, ``include_context.prefix``); older versions listed the routes flat.
    """
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from iter_routes(inner.routes, prefix + route.include_context.prefix)
        elif hasattr(route, "path"):
            yield prefix + route.path, route


def web_routes(app: Any, methods: set[str] | None = None) -> list[tuple[str, str]]:
    """``(method, path template)`` of every route under ``/web`` with a method of ``methods``
    (all of them when ``None``), sorted. The static mount has no methods and is left out."""
    found: set[tuple[str, str]] = set()
    for path, route in iter_routes(app.routes):
        verbs = getattr(route, "methods", None)
        if not path.startswith("/web") or not verbs:
            continue
        for method in verbs if methods is None else verbs & methods:
            found.add((method, path))
    return sorted(found)


def make_pdf(pages: int = 1, width: float = 300) -> bytes:
    """A small real PDF (pypdfium2), for the page-1 renderer and the viewer."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(width, 400)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def expected_csrf(session_token: str, secret: str = SECRET) -> str:
    """base64url(HMAC-SHA256(secret, "csrf|" + sha256(session_token))), no padding (spec 5)."""
    message = b"csrf|" + hashlib.sha256(session_token.encode()).hexdigest().encode()
    mac = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def cookie_attrs(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(";")[1:]}


@dataclass
class Web:
    """A signed-in client: the cookie, the session token, and the CSRF token of that session."""

    client: TestClient
    token: str
    csrf: str

    def headers(self, **more: str) -> dict[str, str]:
        """The headers of an unsafe request: own Origin and the CSRF token."""
        return {"Origin": OWN, "X-CSRF-Token": self.csrf, **more}


@dataclass
class World:
    target: DbTarget
    root: Path
    backend: Any
    app: Any
    service: FileService
    store: FsObjectStore
    hidden: Hidden
    settings: ApiSettings
    ids: dict[str, str] = field(default_factory=dict)  # kind -> record id (hidden world and extras)
    numbers: dict[str, str] = field(default_factory=dict)  # kind -> number or key
    agent_token: str = ""
    answers: list[Any] = field(default_factory=list)  # every response a client of this world saw
    corr: Any = None
    _clients: list[TestClient] = field(default_factory=list)

    # --- clients ------------------------------------------------------------------------------

    def client(
        self,
        cookie: str | None = None,
        *,
        bearer: str | None = None,
        base: str = OWN,
        raises: bool = True,
        app: Any = None,
    ) -> TestClient:
        client = TestClient(
            app or self.app, base_url=base, follow_redirects=False, raise_server_exceptions=raises
        )
        if cookie is not None:
            client.headers["Cookie"] = f"tl_session={cookie}"
        if bearer is not None:
            client.headers["Authorization"] = f"Bearer {bearer}"
        original = client.request

        def recording(*args: Any, **kwargs: Any) -> Any:
            response = original(*args, **kwargs)
            self.answers.append(response)
            return response

        client.request = recording  # type: ignore[method-assign]
        self._clients.append(client)
        return client

    def sign_in(self, name: str, password: str = PASSWORD) -> tuple[Any, str]:
        """``(response, token)`` of ``POST /web/sign-in``; the token is '' when no cookie came."""
        response = self.client().post(
            "/web/sign-in",
            data={"username": name, "password": password},
            headers={"Origin": OWN},
        )
        raw = response.headers.get("set-cookie", "")
        return response, raw.split(";")[0].partition("=")[2]

    def web(self, name: str) -> Web:
        """A client with a web session of ``name`` (the agent: its token in the cookie)."""
        if name == "bot":
            return Web(
                self.client(self.agent_token), self.agent_token, expected_csrf(self.agent_token)
            )
        response, token = self.sign_in(name)
        assert response.status_code == 303 and token, f"sign-in of {name}: {response.status_code}"
        return Web(self.client(token), token, expected_csrf(token))

    def token(self, name: str) -> str:
        """A session token (also valid as a bearer) of a person; the agent token for ``bot``."""
        if name == "bot":
            return self.agent_token
        return sessions.sign_in(self.backend, username=name, password=PASSWORD)[1]

    def api(self, name: str) -> TestClient:
        """A client with ``name``'s bearer token (the JSON API)."""
        return self.client(bearer=self.token(name))

    def reads(self, name: str) -> WebReadClient:
        """A ``WebReadClient`` built the way a request builds it: inside the viewer's context."""
        principal = self.app.state.ctx.resolver.resolve(self.token(name))
        assert principal is not None, name
        with use_viewer(viewer_for(principal)):
            return WebReadClient(self.app.state.ctx, principal)

    def principal(self, name: str) -> Any:
        principal = self.app.state.ctx.resolver.resolve(self.token(name))
        assert principal is not None, name
        return principal

    # --- the ledger ---------------------------------------------------------------------------

    def events(self) -> int:
        return int(self.corr.scalar("SELECT count(*) FROM events"))

    def upload(
        self,
        record_id: str,
        filename: str,
        data: bytes,
        content_type: str = "application/pdf",
        *,
        scope: str = SCOPE,
    ) -> str:
        """A file registered and completed on ``record_id`` as the module that owns it (id back)."""
        with cf.system_view():
            with self.backend(False) as uow:
                ticket = self.service.register_upload(
                    uow,
                    RegisterUpload(
                        actor="user:ctl", source="test", scope=scope, record_id=record_id,
                        slot=None, filename=filename, content_type=content_type, size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    ),
                    by_module=True,
                )  # fmt: skip
            with self.backend(False) as uow:
                done = self.service.complete_upload(
                    uow,
                    CompleteUpload(
                        actor="user:ctl", source="test", scope=scope, upload_id=ticket.upload_id
                    ),
                    io.BytesIO(data),
                    by_module=True,
                )
        return done.file_id

    def close(self) -> None:
        for client in self._clients:
            with contextlib.suppress(Exception):
                client.close()
        self.backend.close()

    def make_app(self, limiter: SourceLimiter | None = None) -> Any:
        return create_app(
            self.backend,
            settings=self.settings,
            tokens=TokenStore(self.settings.tokens_path),
            files_service=self.service,
            object_store=self.store,
            # no check here trips the per-source limit, unless a test passes a small one
            source_limiter=limiter or SourceLimiter(10_000),
        )


def build_world(target: DbTarget, root: Path, *, seeded: bool = True) -> World:
    """The ledger, the accounts, the app; ``seeded=False`` stops after the accounts."""
    create_schema(target)
    backend = open_backend(target)
    # the store the documents seeder writes its files to (``DocumentsWorld``: root/"docs", secret s)
    store = FsObjectStore(root / "docs", secret=b"s")
    service = FileService(store, secret=b"s", scan_inline=True)
    agent_token = ""
    with backend(False) as uow:
        for name, (roles, kind) in ACCOUNTS.items():
            made = accounts.create_account(
                uow, username=name, display_name=name.title(), kind=kind, roles=roles,
                password=prepare_password(PASSWORD, username=name) if kind == "person" else None,
                by="svc:test",
            )  # fmt: skip
            if kind == "agent":
                _, agent_token = accounts.issue_agent_token(
                    uow, account_id=made.account_id, label="web-tests",
                    expires_at=datetime.now(UTC) + timedelta(days=1), by="svc:test",
                )  # fmt: skip
    settings = ApiSettings(db_path=root / "tl.db", tokens_path=root / "tokens.json")
    corr = CorrWorld(target, root / "corr-extra")
    hidden = seed_hidden_world(target, service, root) if seeded else Hidden({}, {}, {})
    world = World(
        target, root, backend, None, service, store, hidden, settings,
        ids=dict(hidden.ids), numbers=dict(hidden.numbers), agent_token=agent_token, corr=corr,
    )  # fmt: skip
    if seeded:
        _extra_rfis(world)
    world.app = world.make_app()
    return world


def _extra_rfis(world: World) -> None:
    """The RFIs the page tests need beyond the hidden world's two (0001 open, 0002 secret)."""
    make = world.corr.forge_technical
    for key, number, kwargs in (
        ("waiting", "P123-RFI-0003",
         {"subject": "Awaiting RFI", "state": "Awaiting response", "subtype": "tq"}),
        ("closed", "P123-RFI-0004", {"subject": "Closed RFI, no actions", "state": "Closed"}),
        ("draft", "P123-RFI-0005", {"subject": "Draft RFI", "state": "Draft"}),
        ("restricted_rfi", "P123-RFI-0006",
         {"subject": "RESTSECRET subject", "state": "Awaiting response",
          "confidentiality": "restricted"}),
        ("planted", "P123-RFI-0007",
         {"subject": PLANTED, "state": "Awaiting response", "question": "Why <u>this</u>?"}),
    ):  # fmt: skip
        world.ids[key] = make(number, scope=SCOPE, **kwargs)
        world.numbers[key] = number
    world.ids["other"] = make(
        "OTH-RFI-0001", subject="Other project", state="Draft", scope="project:OTHER"
    )
    world.numbers["other"] = "OTH-RFI-0001"


@pytest.fixture(autouse=True)
def _web_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test mode, a long web secret, no leftovers from the shell, a private picture cache."""
    monkeypatch.setenv("TL_ENV", "test")
    monkeypatch.setenv("TL_WEB_SECRET", SECRET)
    for name in ("TL_WEB", "TL_WEB_ORIGIN", "TL_PROJECT", "TL_SCHEMA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture(scope="session")
def k() -> SimpleNamespace:
    """The constants and small helpers the tests share (a test module cannot import conftest)."""
    return SimpleNamespace(
        OWN=OWN, PASSWORD=PASSWORD, SECRET=SECRET, CSP=CSP, NEVER=NEVER, PROJECT=PROJECT,
        SCOPE=SCOPE, PLANTED=PLANTED, MAY_READ=MAY_READ, READERS=READERS,
        expected_csrf=expected_csrf, cookie_attrs=cookie_attrs, web_routes=web_routes,
        iter_routes=iter_routes, make_pdf=make_pdf,
    )  # fmt: skip


@pytest.fixture(scope="session")
def htmlkit() -> ModuleType:
    """The HTML reader of ``htmlkit.py``, loaded by path (no sibling imports in importlib mode)."""
    spec = importlib.util.spec_from_file_location("tl_web_tests_htmlkit", HERE / "htmlkit.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def walk() -> ModuleType:
    """``walk.py``: the table of routes the walks go through (``WALK``, ``NO_RECORD_TEXT``)."""
    spec = importlib.util.spec_from_file_location("tl_web_tests_walk", HERE / "walk.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tl_web_tests_walk"] = module  # a frozen dataclass looks its module up here
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def world(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch_module: pytest.MonkeyPatch
) -> Iterator[World]:
    """The seeded world, built once per test module. Read-only tests only."""
    root = tmp_path_factory.mktemp("web-world")
    monkeypatch_module.setenv("XDG_CACHE_HOME", str(root / "cache"))
    built = build_world(root / "tl.db", root)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def fresh_world(tmp_path: Path) -> Iterator[World]:
    """A seeded world for this test alone (it signs in, locks, signs out or runs a command)."""
    built = build_world(tmp_path / "tl.db", tmp_path)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def light_world(tmp_path: Path) -> Iterator[World]:
    """The accounts and the app, no records: the foundation tests (sign-in, CSRF, headers)."""
    built = build_world(tmp_path / "tl.db", tmp_path, seeded=False)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture(scope="module")
def monkeypatch_module() -> Iterator[pytest.MonkeyPatch]:
    """A ``MonkeyPatch`` that lives as long as the module (the module-scoped world needs one)."""
    patch = pytest.MonkeyPatch()
    patch.setenv("TL_ENV", "test")
    patch.setenv("TL_WEB_SECRET", SECRET)
    for name in ("TL_WEB", "TL_WEB_ORIGIN", "TL_PROJECT", "TL_SCHEMA_DIR"):
        patch.delenv(name, raising=False)
    try:
        yield patch
    finally:
        patch.undo()


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every child process the page-1 renderer starts (the list grows as the test goes)."""
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
