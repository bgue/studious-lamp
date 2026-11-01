"""Acceptance script for P2-WEB1 S4: web reads, the log standard (``WebLog``) and the action route.

SQLite temp ledger, ``TL_ENV=test``, ``TestClient`` at ``http://127.0.0.1``. Prints one ``PASS
<check>`` per check, exits 0 when all pass and 1 on the first failure. No page exists yet, so the
script builds its own (the recipe of ``tl_web.log``): a module with ``router = web_router()`` and a
small RFI ``WebLog`` over ``WebReadClient.list_rfis`` and the real ``rfi_cells`` goes into
``sys.modules`` and ``tl_web.routers.PAGE_MODULES`` before ``create_app``. Expected values come from
the spec (``docs/tickets/P2-WEB1/S4-log-standard-reads-actions.md``) and from the JSON routes.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import hmac
import html
import importlib.machinery
import json
import os
import re
import subprocess
import sys
import tempfile
import types
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from unittest import mock

os.environ["TL_ENV"] = "test"
SECRET = "web-secret-for-acceptance-0123456789abcdef"
os.environ["TL_WEB_SECRET"] = SECRET
for _name in ("TL_WEB", "TL_WEB_ORIGIN", "TL_PROJECT"):
    os.environ.pop(_name, None)

from fastapi.testclient import TestClient  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import create_schema  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.commands import command_spec, run_command  # noqa: E402
from tl_api.ratelimit import SourceLimiter  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core.actions import RecordActions  # noqa: E402
from tl_core.auth import accounts, sessions  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.auth.module_roles import holder_for_principal  # noqa: E402,F401
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.confidentiality import use_viewer, viewer_for  # noqa: E402
from tl_mod_correspondence.testing import CorrWorld  # noqa: E402
from tl_mod_documents.testing import DocumentsWorld  # noqa: E402
from tl_tui import display, rfi_text  # noqa: E402
from tl_tui.action_ui import ACTION_UI  # noqa: E402
from tl_tui.layout import plain_lines  # noqa: E402
from tl_web import present, routers  # noqa: E402
from tl_web.actions import NOT_OFFERED  # noqa: E402
from tl_web.reads import MIRRORS, UnsupportedRead, WebReadClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "packages" / "tl-web" / "src" / "tl_web"
PASSWORD = "correct horse battery"
OWN = "http://127.0.0.1"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)
REGIONS = [
    "log-crumb",
    "log-filter",
    "log-table",
    "log-panel",
    "log-actions",
    "log-keys",
    "log-status",
]

#: The page the script builds for itself: the recipe of ``tl_web.log``, over the real RFI functions.
PAGE_SOURCE = """
from fastapi import Request, Response
from tl_web import present
from tl_web.log import WebLog, register
from tl_web.webroute import web_router

router = web_router()


class RfiWebLog(WebLog):
    LOG_NAME = "RFI log"
    LABEL_TYPES = ("correspondence.TechnicalItem",)
    _summary = ""

    def columns(self):
        return present.rfi_text.RFI_COLUMNS

    def drop_order(self):
        return present.rfi_text.RFI_DROP

    def load_rows(self):
        log = self.client.list_rfis(self.project, limit=500)
        self._summary = present.rfi_text.rfi_summary(log)
        return log.lines

    def row_key(self, row):
        return row.id

    def row_record(self, row):
        return (row.number, row.subject)

    def row_cells(self, row):
        return present.rfi_text.rfi_cells(row, self.labels, technical=self.technical)

    def panel_text(self, row):
        view = self.client.get_rfi(self.project, row.number)
        page = present.rfi_text.rfi_page(
            view, self.labels, technical=self.technical,
            client=present.as_client(self.client), project=self.project,
        )
        return present.plain_lines(page)

    def summary_text(self):
        return self._summary


register("rfis", RfiWebLog)


@router.get("/p/{project}/rfis")
def rfi_log(request: Request, project: str, q: str = "", sel: str = "", mode: str = "") -> Response:
    return RfiWebLog.page(request, project, q=q, sel=sel, mode=mode)
"""
PAGE_MODULE = "accept_s4_rfi_page"


def passed(check: str) -> None:
    print(f"PASS {check}")


def expect(condition: bool, what: str) -> None:
    if not condition:
        raise AssertionError(what)


def expected_csrf(session_token: str) -> str:
    message = b"csrf|" + hashlib.sha256(session_token.encode()).hexdigest().encode()
    mac = hmac.new(SECRET.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


class Doc(HTMLParser):
    """What the checks read of an HTML answer: ids in order, table, panel, bar, text."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.ids: list[str] = []
        self.headers: list[str] = []
        self.rows: list[dict[str, Any]] = []
        self.buttons: list[dict[str, Any]] = []
        self.texts: dict[str, str] = {}
        self.visible: list[str] = []
        self.fields: list[str] = []
        self._open: list[str] = []  # ids of the open elements with an id
        self._stack: list[tuple[str, str | None]] = []
        self._cell: list[str] | None = None
        self._row: dict[str, Any] | None = None
        self._head: list[str] | None = None
        self._button: dict[str, Any] | None = None
        self._pre: list[str] | None = None
        self._skip = 0
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self.tags.append((tag, a))
        ident = a.get("id")
        if ident:
            self.ids.append(ident)
        if tag not in ("input", "meta", "link", "br"):
            self._stack.append((tag, ident))
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "th":
            self._head = []
        if tag == "tr" and "data-number" in a:
            self._row = {"attrs": a, "cells": []}
        if tag == "td" and self._row is not None:
            self._cell = []
        if tag == "button" and "data-command" in a:
            self._button = {"attrs": a, "text": ""}
        if tag == "pre":
            self._pre = []
        if tag in ("input", "textarea", "select") and a.get("name"):
            self.fields.append(str(a["name"]))

    def handle_endtag(self, tag: str) -> None:
        while self._stack:
            name, ident = self._stack.pop()
            if name == tag:
                break
        if tag in ("script", "style"):
            self._skip -= 1
        if tag == "th" and self._head is not None:
            self.headers.append("".join(self._head))
            self._head = None
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row["cells"].append("".join(self._cell))
            self._cell = None
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        if tag == "button" and self._button is not None:
            self.buttons.append(self._button)
            self._button = None
        if tag == "pre" and self._pre is not None:
            self.texts["pre"] = "".join(self._pre)
            self._pre = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if data.strip():
            self.visible.append(data.strip())
        if self._head is not None:
            self._head.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if self._button is not None:
            self._button["text"] += data
        if self._pre is not None:
            self._pre.append(data)
        for _, ident in self._stack:
            if ident in REGIONS:
                self.texts[ident] = self.texts.get(ident, "") + data

    def meta(self, name: str) -> str | None:
        return next(
            (a.get("content") for t, a in self.tags if t == "meta" and a.get("name") == name), None
        )

    def inline_problems(self) -> list[str]:
        found: list[str] = []
        for tag, attrs in self.tags:
            if tag == "script" and "src" not in attrs:
                found.append("inline script")
            if tag == "style":
                found.append("style element")
            found.extend(f"{tag}[{n}]" for n in attrs if n == "style" or n.startswith("on"))
        return found

    @property
    def text(self) -> str:
        return "\n".join(self.visible)


class World:
    def __init__(self, work: Path) -> None:
        self.db = work / "ledger.db"
        create_schema(self.db)
        self.backend = open_backend(self.db)
        self.answers: list[Any] = []  # every response the script saw (check i)
        for name, roles in (
            ("alice", ["user"]),
            ("bob", ["user"]),
            ("root", ["admin"]),
            ("ctl", ["document_controller"]),
        ):  # fmt: skip
            with self.backend() as uow:
                accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="person", roles=roles,
                    password=prepare_password(PASSWORD, username=name), by="svc:accept",
                )  # fmt: skip
        self.corr = CorrWorld(self.db, work / "objects")
        self.ids: dict[str, str] = {}
        self.seed(work)
        # the page, before create_app: sys.modules and PAGE_MODULES (recipe of tl_web.log)
        module = types.ModuleType(PAGE_MODULE)
        module.__spec__ = importlib.machinery.ModuleSpec(PAGE_MODULE, None)
        sys.modules[PAGE_MODULE] = module
        exec(compile(PAGE_SOURCE, PAGE_MODULE, "exec"), module.__dict__)  # noqa: S102
        routers.PAGE_MODULES = (*routers.PAGE_MODULES, PAGE_MODULE)
        tokens = work / "tokens.json"
        self.app = create_app(
            self.backend,
            settings=ApiSettings(db_path=self.db, tokens_path=tokens),
            tokens=TokenStore(tokens),
            source_limiter=SourceLimiter(10_000),
        )
        self.ctx = self.app.state.ctx

    def seed(self, work: Path) -> None:
        make = self.corr.forge_technical
        self.ids["answered"] = make(
            "P123-RFI-0001", subject="Answered RFI", state="Answered", scope=SCOPE
        )
        self.ids["closed"] = make(
            "P123-RFI-0002", subject="Closed RFI, no actions", state="Closed", scope=SCOPE
        )
        self.ids["waiting"] = make(
            "P123-RFI-0003",
            subject="Awaiting RFI",
            state="Awaiting response",
            scope=SCOPE,
            subtype="tq",
        )
        self.ids["secret"] = make(
            "P123-RFI-0004", subject="PRIVSECRET subject", state="Awaiting response", scope=SCOPE,
            confidentiality="privileged",
        )  # fmt: skip
        self.ids["restricted"] = make(
            "P123-RFI-0005", subject="RESTSECRET subject", state="Awaiting response", scope=SCOPE,
            confidentiality="restricted",
        )  # fmt: skip
        self.ids["draft"] = make("P123-RFI-0006", subject="Draft RFI", state="Draft", scope=SCOPE)
        self.ids["letter"] = self.corr.forge_item(
            "P123-COR-0001", subject="A letter", state="Received"
        )
        DocumentsWorld(self.db, work / "docs").register("ISO-1234")

    def events(self) -> int:
        return int(self.corr.scalar("SELECT count(*) FROM events"))

    def client(self, cookie: str | None = None) -> TestClient:
        client = TestClient(self.app, base_url=OWN, follow_redirects=False)
        if cookie is not None:
            client.headers["Cookie"] = f"tl_session={cookie}"
        original = client.request

        def recording(*args: Any, **kwargs: Any) -> Any:
            response = original(*args, **kwargs)
            self.answers.append(response)
            return response

        client.request = recording  # type: ignore[method-assign]
        return client

    def token(self, name: str) -> str:
        return sessions.sign_in(self.backend, username=name, password=PASSWORD)[1]

    def web(self, name: str) -> tuple[TestClient, str]:
        """A client with a web session of ``name`` and its CSRF token."""
        response = self.client().post("/web/sign-in", data={"username": name, "password": PASSWORD})
        expect(response.status_code == 303, f"sign-in of {name}: {response.status_code}")
        token = response.headers["set-cookie"].split(";")[0].partition("=")[2]
        return self.client(token), expected_csrf(token)

    def api(self, name: str) -> TestClient:
        return TestClient(
            self.app, base_url=OWN, headers={"Authorization": f"Bearer {self.token(name)}"}
        )

    def reads(self, name: str) -> WebReadClient:
        """A ``WebReadClient`` built the way a request builds it: inside the viewer's context."""
        principal = self.ctx.resolver.resolve(self.token(name))
        expect(principal is not None, "no principal")
        with use_viewer(viewer_for(principal)):
            return WebReadClient(self.ctx, principal)


def own_headers(csrf: str | None) -> dict[str, str]:
    return {"Origin": OWN, **({"X-CSRF-Token": csrf} if csrf else {})}


# --- (a) imports ------------------------------------------------------------------------------


def check_imports() -> None:
    allowed_core = ("tl_core.auth",)
    for path in sorted(WEB.rglob("*.py")):
        tree = ast.parse(path.read_text(), str(path))
        rel = path.relative_to(WEB)
        text = path.read_text()
        expect(not re.search(r"\bcur_\w+", text), f"{rel}: a cur_* name")
        for node in ast.walk(tree):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom) and not node.level
                else []
            )
            for name in names:
                expect(not name.startswith("sqlalchemy"), f"{rel} imports {name}")
                expect(
                    not name.startswith("tl_core") or name.startswith(allowed_core),
                    f"{rel} imports {name}",
                )
                if name.startswith("tl_tui"):
                    expect(rel.name == "present.py", f"{rel} imports {name}")
    code = (
        "import sys, importlib\nimport tl_web.app\n"
        "from tl_web.routers import PAGE_MODULES, _exists\n"
        "for n in PAGE_MODULES:\n    if _exists(n): importlib.import_module(n)\n"
        "assert 'textual' not in sys.modules, 'textual was imported'\nprint('clean')"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=ROOT
    )
    expect(out.returncode == 0 and "clean" in out.stdout, f"fresh interpreter: {out.stderr[-300:]}")
    passed(
        "a: no sqlalchemy, cur_*, tl_core beyond auth; only present.py imports tl_tui; no textual"
    )


# --- (b) MIRRORS ------------------------------------------------------------------------------


def check_mirrors(world: World) -> None:
    public = {
        name
        for name, member in vars(WebReadClient).items()
        if not name.startswith("_") and callable(member)
    }
    expect(public == set(MIRRORS), f"MIRRORS {sorted(set(MIRRORS) ^ public)}")
    operations = {
        op.get("operationId")
        for methods in world.app.openapi()["paths"].values()
        for op in methods.values()
    }
    for method, operation in MIRRORS.items():
        expect(operation in operations, f"{method}: no route with operation_id {operation}")
    client = world.reads("alice")
    for name in ("list_records", "get_tag", "nope", "__nope__"):
        try:
            getattr(client, name)
        except UnsupportedRead as exc:
            expect(isinstance(exc, AttributeError) and exc.name == name, "UnsupportedRead shape")
        else:
            raise AssertionError(f"{name} did not raise UnsupportedRead")
    # the renderers run against the seeded records with no UnsupportedRead (they swallow errors,
    # so the class is watched where it is raised)
    raised: list[str] = []
    original = WebReadClient.__getattr__

    def watch(self: WebReadClient, name: str) -> Any:
        try:
            return original(self, name)
        except UnsupportedRead:
            raised.append(name)
            raise

    from tl_tui import details, labels_load
    from tl_web import present

    with mock.patch.object(WebReadClient, "__getattr__", watch):
        as_client = present.as_client(client)
        labels = labels_load.load_labels(as_client, SCOPE, ("correspondence.TechnicalItem",))
        for key in ("P123-RFI-0001", "P123-COR-0001", "ISO-1234"):
            record = client.get_record(SCOPE, key)
            expect(record is not None, f"no record {key}")
            rows = details.details_for(as_client, PROJECT, record, labels, display.DisplayMode())
            expect(len(rows) > 0, f"no detail rows for {key}")
            expect(
                not any(r.label == details.NOTE_LABEL for r in rows), f"{key}: the renderer failed"
            )
    expect(not raised, f"UnsupportedRead raised for {raised}")
    try:
        client.list_accounts()
        raise AssertionError("a plain user listed accounts")
    except ForbiddenError:
        pass
    expect(len(world.reads("root").list_accounts()) >= 4, "an admin cannot list accounts")
    passed(
        "b: MIRRORS == methods, operation_ids exist, others raise UnsupportedRead, renderers run"
    )


# --- (c) reads parity -------------------------------------------------------------------------


def numbers(log: Any) -> list[str]:
    return [line.number for line in log.lines]


def check_reads(world: World) -> None:
    for name in ("root", "alice", "ctl"):
        mine = world.reads(name).list_rfis(PROJECT)
        route = world.api(name).get(f"/projects/{PROJECT}/rfis").json()
        expect(numbers(mine) == [r["number"] for r in route["lines"]], f"{name}: rows differ")
        expect(mine.total == route["total"] == len(mine.lines), f"{name}: count differs")
    admin, plain = (
        numbers(world.reads("root").list_rfis(PROJECT)),
        world.reads("alice").list_rfis(PROJECT),
    )
    expect("P123-RFI-0005" in admin and "P123-RFI-0005" not in numbers(plain), "restricted RFI")
    for hidden in ("P123-RFI-0004", "P123-RFI-0005"):
        expect(hidden not in numbers(plain), f"{hidden} in the plain rows")
    expect(plain.total == len(plain.lines) == 4, f"plain count {plain.total}")
    errors = []
    for number in ("P123-RFI-0004", "P123-RFI-9999"):
        try:
            world.reads("alice").get_rfi(PROJECT, number)
        except Exception as exc:  # noqa: BLE001
            errors.append((type(exc), str(exc).replace(number, "N")))
        else:
            raise AssertionError(f"{number} was read")
    expect(errors[0] == errors[1], f"hidden and unknown differ: {errors}")
    api = world.api("alice").get(f"/projects/{PROJECT}/rfis/P123-RFI-0004")
    expect(api.status_code == 404, "the JSON route")
    expect(
        world.reads("alice").get_record_by_id(world.ids["secret"]) is None, "hidden record by id"
    )
    passed("c: list_rfis equals the JSON rows; a plain user's rows and count leave the hidden out")


# --- (d) the page -----------------------------------------------------------------------------


def labels_for(world: World, name: str) -> Any:
    from tl_tui import labels_load
    from tl_web import present

    return labels_load.load_labels(
        present.as_client(world.reads(name)), SCOPE, ("correspondence.TechnicalItem",)
    )


def expected_rows(world: World, name: str, *, technical: bool) -> list[tuple[str, ...]]:
    labels = labels_for(world, name)
    return [
        rfi_text.rfi_cells(line, labels, technical=technical)
        for line in world.reads(name).list_rfis(PROJECT).lines
    ]


def check_page(world: World) -> None:
    alice, _ = world.web("alice")
    page = alice.get(f"/web/p/{PROJECT}/rfis")
    expect(page.status_code == 200, f"page {page.status_code}")
    doc = Doc(page.text)
    seen = [i for i in doc.ids if i in REGIONS]
    expect(seen == REGIONS, f"regions {seen}")
    expect(doc.headers[:3] == ["Number", "Subject", "State"], f"columns {doc.headers}")
    expect(set(doc.headers) < set(rfi_text.RFI_COLUMNS) | set(doc.headers), "unknown column")
    full = expected_rows(world, "alice", technical=False)
    positions = [rfi_text.RFI_COLUMNS.index(h) for h in doc.headers]
    expect(len(doc.rows) == len(full) == 4, f"{len(doc.rows)} rows")
    for row, cells in zip(doc.rows, full, strict=True):
        expect(row["cells"] == [cells[i] for i in positions], f"cells {row['cells']} != {cells}")
    for index, name in enumerate(rfi_text.RFI_COLUMNS):
        values = {cells[index] for cells in full}
        if index in positions and name not in ("Number", "Subject", "State"):
            expect(len(values) > 1, f"constant column {name} is shown")
        if index not in positions:
            expect(len(values) == 1, f"varying column {name} is dropped")
    expect("Kind" in doc.headers and "Discipline" not in doc.headers, f"columns {doc.headers}")
    expect(any(r["attrs"]["aria-selected"] == "true" for r in doc.rows), "no selected row")
    for secret in (
        "PRIVSECRET",
        "RESTSECRET",
        "P123-RFI-0004",
        "P123-RFI-0005",
        world.ids["secret"],
    ):
        expect(secret not in page.text, f"{secret} in the page")
    # the panel of the visible number carries the terminal's panel lines
    labels = labels_for(world, "alice")
    reader = world.reads("alice")
    from tl_web import present

    view = reader.get_rfi(PROJECT, "P123-RFI-0001")
    lines = plain_lines(
        rfi_text.rfi_page(
            view, labels, technical=False, client=present.as_client(reader), project=PROJECT
        )
    )
    panel = alice.get(f"/web/p/{PROJECT}/rfis/panel/P123-RFI-0001")
    expect(panel.status_code == 200, f"panel {panel.status_code}")
    got = Doc(panel.text)
    expect(got.texts.get("pre", "").split("\n") == lines, "the panel is not the terminal's lines")
    for oob in ("log-crumb", "log-actions", "log-status"):
        expect(
            f'id="{oob}"' in panel.text and "hx-swap-oob" in panel.text, f"{oob} not out of band"
        )
    expect("P123-RFI-0001: Answered RFI" in got.texts["log-crumb"], got.texts["log-crumb"])
    # hidden = unknown: identical status and bytes
    answers = [
        alice.get(f"/web/p/{PROJECT}/rfis/panel/{n}")
        for n in ("P123-RFI-0004", "P123-RFI-0005", "P123-RFI-9999", "nothing/at/all")
    ]
    answers.append(alice.get(f"/web/p/{PROJECT}/nolog/panel/P123-RFI-0001"))
    expect({a.status_code for a in answers} == {404}, [a.status_code for a in answers])
    expect(len({a.content for a in answers}) == 1, "the 404 pages differ")
    unknown = alice.get("/web/nowhere")
    expect(unknown.content == answers[0].content, "not the one 404 page")
    # the filter works on the rows
    found = Doc(alice.get(f"/web/p/{PROJECT}/rfis?q=awaiting").text)
    expect([r["cells"][0] for r in found.rows] == ["P123-RFI-0003"], "the filter")
    passed(
        "d: seven regions in order, columns rule, cells == rfi_cells, panel lines, hidden == 404"
    )


# --- (e) actions ------------------------------------------------------------------------------


def status_of(response: Any) -> str:
    return html.unescape(Doc(response.text).texts.get("log-status", "")).strip()


def check_actions(world: World) -> None:
    alice, csrf = world.web("alice")
    ids = world.ids
    api = world.api("alice")
    # the bar lists exactly the offered ones
    for key in ("answered", "waiting", "closed", "draft"):
        offered = [a["command"] for a in api.get(f"/records/{ids[key]}/actions").json()["actions"]]
        number = {"answered": "0001", "closed": "0002", "waiting": "0003", "draft": "0006"}[key]
        page = Doc(alice.get(f"/web/p/{PROJECT}/rfis?sel=P123-RFI-{number}").text)
        bar = [b["attrs"]["data-command"] for b in page.buttons]
        expect(bar == [o for o in offered if o in ACTION_UI], f"{key}: the bar {bar} != {offered}")
        part = Doc(alice.get(f"/web/p/{PROJECT}/rfis/panel/P123-RFI-{number}").text)
        expect(len(part.buttons) == len(page.buttons), f"{key}: the partial's bar")
    expect(
        api.get(f"/records/{ids['closed']}/actions").json()["actions"] == [],
        "the closed RFI is offered something",
    )
    do = lambda key, command, **form: alice.post(  # noqa: E731
        f"/web/p/{PROJECT}/records/{ids[key]}/do/{command}",
        data=form or None,
        headers=own_headers(csrf),
    )
    # in ACTION_UI but not offered: refused, no event
    before = world.events()
    for key, command in (
        ("closed", "CloseTechnical"),
        ("answered", "AnswerTechnical"),
        ("waiting", "SubmitTechnical"),
    ):
        response = do(key, command, answer="x", reason="x")
        expect(response.status_code == 409, f"{command} on {key}: {response.status_code}")
        said = status_of(response)
        expect(said == f"! {NOT_OFFERED}", f"{command} on {key}: {said!r}")
        expect(world.events() == before, f"{command} on {key} wrote an event")
    # a form field cannot make a command offered
    response = do("closed", "CloseTechnical", offered="CloseTechnical", allowed="CloseTechnical")
    expect(
        response.status_code == 409 and world.events() == before, "a form field offered a command"
    )
    # offered: runs and the state changes
    state = lambda key: api.get(f"/records/{ids[key]}").json()["status"]  # noqa: E731
    draft_before = state("draft")
    run = do("draft", "SubmitTechnical")
    expect(
        run.status_code == 200 and run.headers.get("HX-Refresh") == "true",
        f"{run.status_code} {run.text}",
    )
    expect(world.events() > before and state("draft") != draft_before, "the state did not change")
    form = alice.get(f"/web/p/{PROJECT}/records/{ids['waiting']}/do/AnswerTechnical/form")
    names = Doc(form.text).fields
    expect(
        form.status_code == 200
        and {"answer", "cost_impact", "schedule_impact", "csrf"} <= set(names),
        str(names),
    )
    missing = do("waiting", "AnswerTechnical", cost_impact="yes", schedule_impact="no")
    expect(
        missing.status_code == 422 and "required" in status_of(missing),
        f"{missing.status_code} {missing.text}",
    )
    waiting_before = state("waiting")
    run = do(
        "waiting", "AnswerTechnical", answer="Reroute it.", cost_impact="yes", schedule_impact="no"
    )
    expect(
        run.status_code == 200 and state("waiting") != waiting_before,
        f"answer {run.status_code} {run.text}",
    )
    expect(
        alice.get(f"/web/p/{PROJECT}/records/{ids['closed']}/do/CloseTechnical/form").status_code
        == 409,
        "a form for a command that is not offered",
    )
    # CSRF
    bare = alice.post(
        f"/web/p/{PROJECT}/records/{ids['answered']}/do/ReviewTechnicalAnswer",
        headers={"Origin": OWN},
    )
    expect(
        bare.status_code == 403 and bare.json()["error"] == "csrf_refused",
        f"csrf {bare.status_code}",
    )
    # a refusal of run_command is shown as it is: an offer that is stale or too wide
    principal = world.ctx.resolver.resolve(world.token("alice"))
    spec = command_spec("EscalateTechnical")
    assert spec is not None and principal is not None
    wide = RecordActions.model_validate(
        {
            "record_id": ids["answered"],
            "state": "Answered",
            "actions": [{"command": "EscalateTechnical", "label": "Escalate", "reason": "stale"}],
        }  # fmt: skip
    )
    try:
        with mock.patch.object(WebReadClient, "allowed_actions", lambda self, record_id: wide):
            built = ACTION_UI["EscalateTechnical"].build({}, ids["answered"], None)
            cmd = present.stamp(built, actor=principal.actor, scope=SCOPE)
            with use_viewer(viewer_for(principal)):
                run_command(world.ctx, spec, cmd, principal=principal)
            raise AssertionError("alice escalated")
    except ForbiddenError as exc:
        wanted = f"! {exc}"
    before = world.events()
    with mock.patch.object(WebReadClient, "allowed_actions", lambda self, record_id: wide):
        refused = do("answered", "EscalateTechnical")
    expect(refused.status_code == 403, f"module refusal status {refused.status_code}")
    expect(status_of(refused) == wanted, f"{status_of(refused)!r} != {wanted!r}")
    expect(world.events() == before, "the module refusal wrote an event")
    # not in ACTION_UI, not a command, hidden record, other project
    for command in ("SetPsetValues", "NoSuchCommand"):
        expect(do("answered", command).status_code == 404, f"{command} is not 404")
    hidden = alice.post(
        f"/web/p/{PROJECT}/records/{ids['secret']}/do/CloseTechnical", headers=own_headers(csrf)
    )
    unknown = alice.post(
        f"/web/p/{PROJECT}/records/01J00000000000000000000000/do/CloseTechnical",
        headers=own_headers(csrf),
    )
    expect(
        hidden.status_code == unknown.status_code == 404 and hidden.content == unknown.content,
        "hidden != unknown",
    )
    elsewhere = alice.post(
        f"/web/p/OTHER/records/{ids['answered']}/do/ReviewTechnicalAnswer",
        headers=own_headers(csrf),
    )
    expect(
        elsewhere.status_code == 404 and elsewhere.content == unknown.content,
        "a record of another project",
    )
    passed(
        "e: bar == offered; not offered refused, no event; offered runs; CSRF; refusal shown; 404s"
    )


# --- (f) mode, (g) plain walk -----------------------------------------------------------------


def check_mode(world: World) -> None:
    alice, _ = world.web("alice")
    root, _ = world.web("root")
    for path in (
        f"/web/p/{PROJECT}/rfis?mode=technical",
        f"/web/p/{PROJECT}/rfis/panel/P123-RFI-0001?mode=technical",
    ):
        doc = Doc(alice.get(path).text)
        expect(
            doc.texts["log-status"].strip() == display.REFUSAL,
            f"status {doc.texts.get('log-status')!r}",
        )
    plain = Doc(alice.get(f"/web/p/{PROJECT}/rfis?mode=technical").text)
    labels = labels_for(world, "alice")
    positions = [rfi_text.RFI_COLUMNS.index(h) for h in plain.headers]
    for row, line in zip(plain.rows, world.reads("alice").list_rfis(PROJECT).lines, strict=True):
        cells = rfi_text.rfi_cells(line, labels, technical=False)
        expect(row["cells"] == [cells[i] for i in positions], "a non-admin got technical rows")
    expect(
        "mode=technical" not in alice.get(f"/web/p/{PROJECT}/rfis?mode=technical").text,
        "mode carried for a non-admin",
    )
    technical = Doc(root.get(f"/web/p/{PROJECT}/rfis?mode=technical").text)
    expect(technical.texts["log-status"].strip() != display.REFUSAL, "an admin was refused")
    labels = labels_for(world, "root")
    lines = world.reads("root").list_rfis(PROJECT).lines
    positions = [rfi_text.RFI_COLUMNS.index(h) for h in technical.headers]
    kinds = {rfi_text.rfi_cells(line, labels, technical=True)[3] for line in lines}
    expect(
        kinds != {rfi_text.rfi_cells(line, labels, technical=False)[3] for line in lines},
        "no technical difference",
    )
    for row, line in zip(technical.rows, lines, strict=True):
        cells = rfi_text.rfi_cells(line, labels, technical=True)
        expect(
            row["cells"] == [cells[i] for i in positions], "the admin did not get technical rows"
        )
    expect(
        "mode=technical" in root.get(f"/web/p/{PROJECT}/rfis?mode=technical").text,
        "mode not carried on links",
    )
    expect("mode=technical" not in root.get(f"/web/p/{PROJECT}/rfis").text, "mode stored")
    passed(
        "f: ?mode=technical is plain + status text for a non-admin; an admin gets technical rows"
    )


def check_plain(world: World) -> None:
    alice, _ = world.web("alice")
    labels = labels_for(world, "alice")
    for path in (
        f"/web/p/{PROJECT}/rfis",
        f"/web/p/{PROJECT}/rfis?sel=P123-RFI-0001",
        f"/web/p/{PROJECT}/rfis/panel/P123-RFI-0001",
        f"/web/p/{PROJECT}/rfis/panel/P123-RFI-0003",
        f"/web/p/{PROJECT}/rfis?mode=technical",
    ):
        text = Doc(alice.get(path).text).text
        expect(
            display.find_technical(text, labels) == [],
            f"{path}: {display.find_technical(text, labels)}",
        )
    passed("g: find_technical finds nothing in the page and the panel as a plain user")


# --- (h) body limits, (i) markup --------------------------------------------------------------


def check_limits(world: World) -> None:
    alice, csrf = world.web("alice")
    big = "a=" + "x" * (100 * 1024)
    headers = {**own_headers(csrf), "Content-Type": "application/x-www-form-urlencoded"}
    response = alice.post("/web/p/x/records/y/do/z", content=big, headers=headers)
    expect(
        response.status_code == 413 and response.json()["error"] == "payload_too_large",
        f"{response.status_code}",
    )
    expect(
        world.client().post("/web/sign-in", content=big, headers=headers).status_code == 413,
        "sign-in 100 KiB",
    )
    middle = "a=" + "x" * (20 * 1024)
    expect(
        world.client().post("/web/sign-in", content=middle, headers=headers).status_code == 413,
        "sign-in 20 KiB",
    )
    expect(
        alice.post("/web/p/x/records/y/do/z", content=middle, headers=headers).status_code != 413,
        "20 KiB refused",
    )
    passed("h: /web/ bodies are cut at 64 KiB; /web/sign-in is still cut at 16 KiB")


def check_markup(world: World) -> None:
    expect(len(world.answers) > 50, f"only {len(world.answers)} answers")
    for response in world.answers:
        if not str(response.url).split("/web", 1)[-1] or "/web" not in str(response.url):
            continue
        expect(response.headers.get("content-security-policy") == CSP, f"CSP on {response.url}")
        if "text/html" in response.headers.get("content-type", ""):
            problems = Doc(response.text).inline_problems()
            expect(not problems, f"{response.url}: {problems}")
    script = (WEB / "static" / "tl.js").read_text()
    for word in ("eval(", "fetch(", "innerHTML"):
        expect(word not in script, f"tl.js has {word}")
    expect(len(script.splitlines()) <= 200, "tl.js is over 200 lines")
    expect(
        "htmx:configRequest" in script and "X-CSRF-Token" in script, "tl.js sends no CSRF header"
    )
    page = Doc(
        world.client(world.web("alice")[0].headers["Cookie"].split("=", 1)[1])
        .get(f"/web/p/{PROJECT}/rfis")
        .text
    )
    config = json.loads(page.meta("htmx-config") or "{}")
    expect(
        config.get("allowEval") is False
        and config.get("allowScriptTags") is False
        and config.get("includeIndicatorStyles") is False
        and config.get("selfRequestsOnly") is True,
        f"htmx-config {config}",
    )  # fmt: skip
    expect(bool(page.meta("csrf-token")), "no csrf-token meta")
    passed("i: no inline script/style/on*; CSP on every answer; tl.js clean and short")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        world = World(Path(tmp))
        try:
            check_imports()
            check_mirrors(world)
            check_reads(world)
            check_page(world)
            check_actions(world)
            check_mode(world)
            check_plain(world)
            check_limits(world)
            check_markup(world)
        finally:
            world.backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
