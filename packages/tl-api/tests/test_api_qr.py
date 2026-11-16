"""The QR read routes (P2-QR-T06): the register of one record's codes, its export and a resolve.

The ledger is built by the QR module's world (``packages/tl-modules/qr/tests/qr_world.py``, loaded
by path as ``test_api_punch.py`` loads its world). Five kinds of reader: a signed-in person with no
clearance, a document controller (restricted records), a company admin, an agent token and a
signed-in person with no role (no ``qr.view``). The agent is refused before any lookup; a hidden,
unknown or other-project record answers the same 404; a resolve miss is one byte-identical 404.
"""

from __future__ import annotations

import csv
import dataclasses
import importlib.util
import io
import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import Connection, text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.qr import registry
from tl_core.settings import resolver
from tl_mod_qr import routes as qr_routes
from tl_mod_qr import service
from tl_mod_qr.codes import code_hash, new_code, normalise_code
from tl_mod_qr.views import CodeRow

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
BASE = "https://tl.example.com"
LIST = "/qr/codes"
EXPORT = "/qr/codes/export"
RESOLVE = "/qr/resolve"
NO_STORE = "no-store"
LIST_FIELDS = [
    "id",
    "label_text",
    "size",
    "issued_by",
    "issued_at",
    "expires_on",
    "state",
    "revoked_at",
    "replaced_by_id",
]


def load_world() -> ModuleType:
    """The QR module's ``qr_world`` helper (the ledger of the T01 and S2 tests), loaded by path."""
    name = "qr_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "qr" / "tests" / "qr_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


qw = load_world()
FakeProvider = qw.FakeProvider
SECRET = qw.SECRET
providers_of = qw.providers_of


class Seeded:
    """The ids, keys, codes and tokens the tests read by."""

    def __init__(self, h: Harness, world: Any) -> None:
        self.h = h
        self.world = world
        self.keys: dict[str, str] = {}
        self.ids: dict[str, str] = {}
        self.codes: dict[str, str] = {}
        self.tokens: dict[str, str] = {}


class Rig:
    def __init__(self, seeded: Seeded) -> None:
        self.s = seeded
        self.h = seeded.h

    def client(self, who: str | None) -> Any:
        """A client that sends ``who``'s token (``None``: no token)."""
        client = self.h.client_for(None)
        if who is not None:
            client.headers.update({"Authorization": f"Bearer {self.s.tokens[who]}"})
        return client

    def get(self, who: str | None, path: str, **params: Any) -> Any:
        return self.client(who).get(path, params=params)

    def register(self, who: str | None, record: str, **more: Any) -> Any:
        return self.get(who, LIST, project=PROJECT, record=record, **more)

    def export(self, who: str | None, record: str, fmt: str) -> Any:
        return self.get(who, EXPORT, project=PROJECT, record=record, format=fmt)

    def resolve(self, who: str | None, code: str) -> Any:
        return self.client(who).get(f"{RESOLVE}/{code}")

    def rows(self, who: str, record: str) -> list[dict[str, Any]]:
        response = self.register(who, record)
        assert response.status_code == 200, response.text
        return response.json()


def seed(h: Harness, mp: pytest.MonkeyPatch) -> Seeded:
    target = h.target or h.db
    world = load_world().World(target)
    world.people()
    world.person("vic", ("user",))
    world.base(BASE)
    with h.backend(False) as uow:
        bot = accounts.create_account(
            uow,
            username="bot",
            display_name="Bot",
            kind="agent",
            roles=["user"],
            password=None,
            by="svc:test",
        )
        _, agent_token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="qr",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )

    # the public address the service reads for a code's link, and the provider of the cards
    real = resolver.value_of

    def value_of(conn: Connection, key: str, **kwargs: Any) -> Any:
        return world.public if key == service.BASE_URL else real(conn, key, **kwargs)

    mp.setattr(service, "value_of", value_of)
    fake = providers_of(FakeProvider(), FakeProvider(SECRET))
    mp.setattr(registry, "load_scan_cards", lambda *a, **k: fake)

    s = Seeded(h, world)
    s.tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("ada", "uma", "dora", "vic")
    }
    s.tokens["bot"] = agent_token

    s.ids["open"] = world.record(key="PUN-1")
    s.ids["secret"] = world.hidden_record("restricted")
    s.keys["open"] = "PUN-1"
    s.keys["secret"] = str(
        world.rows("SELECT key FROM cur_core_record WHERE id = :id", id=s.ids["secret"])[0]["key"]
    )

    # three codes on the open record: live, revoked, expired (the expiry is set after the issue,
    # since an issue refuses a past expiry)
    live = world.serve(
        service.issue, "uma", "IssueScanCode", target_id=s.ids["open"], label_text="Pump"
    )
    s.codes["live"] = live.code
    revoked = world.serve(service.issue, "uma", "IssueScanCode", target_id=s.ids["open"])
    s.codes["revoked"] = revoked.code
    world.call("ada", "RevokeScanCode", code_id=revoked.result.stream_id, reason="lost")
    expired = world.serve(service.issue, "uma", "IssueScanCode", target_id=s.ids["open"])
    s.codes["expired"] = expired.code
    with open_uow(target) as uow:
        uow.conn().execute(
            text("UPDATE cur_qr_scan_code SET expires_on = :d WHERE id = :i"),
            {
                "d": (datetime.now(UTC).date() - timedelta(days=2)).isoformat(),
                "i": expired.result.stream_id,
            },
        )
    # one code on the restricted record, issued by the document controller
    hidden = world.serve(service.issue, "dora", "IssueScanCode", target_id=s.ids["secret"])
    s.codes["hidden"] = hidden.code
    return s


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-qr"))
    mp = pytest.MonkeyPatch()
    try:
        yield Rig(seed(h, mp))
    finally:
        mp.undo()
        h.close()


def _plain(code: str) -> str:
    plain = normalise_code(code)
    assert plain is not None
    return plain


# --- the routes and their readers ----------------------------------------------------------------


def test_the_three_routes_are_registered(rig: Rig) -> None:
    paths = rig.h.app.openapi()["paths"]
    assert {"/qr/codes", "/qr/codes/export", "/qr/resolve/{code}"} <= set(paths)
    assert paths["/qr/codes"]["get"]["operationId"] == "list_qr_codes"
    assert paths["/qr/codes/export"]["get"]["operationId"] == "export_qr_codes"
    assert paths["/qr/resolve/{code}"]["get"]["operationId"] == "resolve_qr_code"


def test_no_token_is_401_on_every_route(rig: Rig) -> None:
    assert rig.register(None, "PUN-1").status_code == 401
    assert rig.export(None, "PUN-1", "csv").status_code == 401
    assert rig.resolve(None, rig.s.codes["live"]).status_code == 401


def test_an_agent_is_refused_before_any_lookup(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    looked: list[str] = []

    def spy(name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            looked.append(name)
            raise AssertionError(f"{name} ran for an agent")

        return call

    monkeypatch.setattr(qr_routes, "get_record", spy("get_record"))
    monkeypatch.setattr(qr_routes, "codes_for_record", spy("codes_for_record"))
    monkeypatch.setattr(qr_routes, "resolve", spy("resolve"))
    for response in (
        rig.register("bot", "PUN-1"),
        rig.export("bot", "PUN-1", "csv"),
        rig.resolve("bot", rig.s.codes["live"]),
    ):
        assert response.status_code == 403, response.text
        assert response.json()["error"] == "forbidden"
    assert looked == []


def test_a_reader_who_cannot_see_the_record_gets_the_unknown_key_answer(rig: Rig) -> None:
    unknown = rig.register("uma", "NO-SUCH-KEY")
    hidden = rig.register("uma", rig.s.keys["secret"])
    assert unknown.status_code == hidden.status_code == 404
    assert unknown.text == hidden.text
    assert "no such record" in hidden.text
    assert rig.s.keys["secret"] not in hidden.text
    export_unknown = rig.export("uma", "NO-SUCH-KEY", "jsonl")
    export_hidden = rig.export("uma", rig.s.keys["secret"], "jsonl")
    assert export_unknown.status_code == export_hidden.status_code == 404
    assert export_unknown.text == export_hidden.text


def test_the_lowest_reader_sees_the_visible_codes_only(rig: Rig) -> None:
    rows = rig.rows("uma", "PUN-1")
    assert len(rows) == 3
    assert [row["state"] for row in rows].count("revoked") == 1
    assert [row["state"] for row in rows].count("expired") == 1
    assert all(set(row) == set(LIST_FIELDS) for row in rows)


def test_a_cleared_reader_sees_the_restricted_codes(rig: Rig) -> None:
    assert len(rig.rows("dora", rig.s.keys["secret"])) == 1


def test_the_company_admin_sees_the_visible_codes(rig: Rig) -> None:
    assert len(rig.rows("ada", "PUN-1")) == 3


def test_the_view_word_is_checked_on_the_project_before_any_read(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every account holds ``read`` (``schema/settings/module-roles.yaml`` derives ``user`` for
    all modules), so no seeded person lacks ``qr.view``; a refusal is simulated at the one
    ``require_word`` call. The check names ``qr.view`` on ``project:P123``; no read may run."""
    asked: list[dict[str, Any]] = []
    looked: list[str] = []

    def refuse(conn: Any, holder: Any, **kwargs: Any) -> None:
        asked.append(kwargs)
        raise ForbiddenError(f"{kwargs['what']} needs the {kwargs['word']} access word")

    def spy(*args: Any, **kwargs: Any) -> Any:
        looked.append("read")
        raise AssertionError("a read ran without the view word")

    monkeypatch.setattr(qr_routes, "require_word", refuse)
    monkeypatch.setattr(qr_routes, "get_record", spy)
    for response in (rig.register("vic", "PUN-1"), rig.export("vic", "PUN-1", "csv")):
        assert response.status_code == 403, response.text
        assert response.json()["error"] == "forbidden"
    assert looked == []
    # ``qr.view`` resolves to the table word ``read`` (``normalise_word``)
    assert {(a["scope"], a["module"], a["word"], a["what"]) for a in asked} == {
        (SCOPE, "qr", "read", "qr.view")
    }


def test_the_list_rows_equal_the_export_rows(rig: Rig) -> None:
    rows = rig.rows("uma", "PUN-1")
    reader = csv.DictReader(io.StringIO(rig.export("uma", "PUN-1", "csv").text))
    csv_rows = list(reader)
    assert reader.fieldnames == LIST_FIELDS
    expected = [{k: ("" if v is None else str(v)) for k, v in r.items()} for r in rows]
    assert csv_rows == expected
    jsonl = rig.export("uma", "PUN-1", "jsonl")
    assert jsonl.headers["content-type"].startswith("application/x-ndjson")
    assert [json.loads(line) for line in jsonl.text.splitlines()] == rows
    assert rig.export("uma", "PUN-1", "csv").headers["content-type"].startswith("text/csv")


def test_no_answer_carries_a_code_or_its_hash(rig: Rig) -> None:
    bodies = [
        rig.register("uma", "PUN-1").text,
        rig.export("uma", "PUN-1", "csv").text,
        rig.export("uma", "PUN-1", "jsonl").text,
        rig.resolve("uma", rig.s.codes["live"]).text,
    ]
    for code in rig.s.codes.values():
        plain = _plain(code)
        for body in bodies:
            assert plain not in body
            assert code not in body
            assert code_hash(plain) not in body


def test_a_live_code_resolves_to_its_card_with_no_store(rig: Rig) -> None:
    response = rig.resolve("uma", rig.s.codes["live"])
    assert response.status_code == 200, response.text
    card = response.json()
    assert {"banner", "key", "lines"} <= set(card)
    assert response.headers["cache-control"] == NO_STORE


def test_every_resolve_miss_is_one_404(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    misses = [
        rig.resolve("uma", "not a code"),
        rig.resolve("uma", new_code()),
        rig.resolve("uma", rig.s.codes["revoked"]),
        rig.resolve("uma", rig.s.codes["expired"]),
        rig.resolve("uma", rig.s.codes["hidden"]),
    ]
    # a viewer that holds no word (the LOWEST viewer) is the same miss as the others
    monkeypatch.setattr(qr_routes, "current_viewer", lambda: cf.LOWEST)
    misses.append(rig.resolve("uma", rig.s.codes["live"]))
    for response in misses:
        assert response.status_code == 404
        assert response.headers["cache-control"] == NO_STORE
        assert response.text == misses[0].text
    assert json.loads(misses[0].text)["error"] == "record_not_found"
    assert json.loads(misses[0].text)["message"] == "no such code"


def test_the_three_routes_are_in_the_openapi_document(rig: Rig) -> None:
    paths = rig.h.app.openapi()["paths"]
    assert "get" in paths["/qr/codes"]
    assert "get" in paths["/qr/codes/export"]
    assert "get" in paths["/qr/resolve/{code}"]


def test_the_row_fields_are_the_view_fields() -> None:
    assert [f.name for f in dataclasses.fields(CodeRow)] == LIST_FIELDS
