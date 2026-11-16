"""The permit read routes (P2-PTW-T07): the register, the board, the export and one permit.

The ledger is built by the permits module's ``permit_world`` helper, loaded by path as
``test_api_punch.py`` loads its world, never by a projection write. A permit for a restricted
record is the one the lowest-clearance reader must not see; a document controller must. Readers
here: no token (401), the lowest clearance (``uma``), a cleared reader (``dora``) and an agent
(``bot``). A person with no permits word (403) is not built; see the report.
"""

from __future__ import annotations

import csv
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
from tl_core.auth import accounts, sessions

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
PROJECT = "P123"
LIST = "/permits"
BOARD = "/permits/board"
EXPORT = "/permits/export"
MISSING = "P123-PTW-9999"
NOT_FOUND = "no permit"


def load_world() -> ModuleType:
    """The permits module's ``permit_world`` helper (the ledger of its tests), loaded by path."""
    name = "permit_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "permits" / "tests" / "permit_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Seeded:
    """The ids, keys and tokens the tests read by."""

    def __init__(self, h: Harness, world: Any) -> None:
        self.h = h
        self.world = world
        self.ids: dict[str, str] = {}
        self.keys: dict[str, str] = {}
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
        return self.client(who).get(path, params={"project": PROJECT, **params})

    def ok(self, who: str, path: str, **params: Any) -> Any:
        response = self.get(who, path, **params)
        assert response.status_code == 200, (path, response.text)
        return response.json()

    def keys_of(self, who: str, **params: Any) -> list[str]:
        return [r["key"] for r in self.ok(who, LIST, **params)["rows"]]


def seed(h: Harness) -> Seeded:
    target = h.target or h.db
    world = load_world().World(target)
    world.people()
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
            label="permits",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    s = Seeded(h, world)
    s.tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("uma", "dora")
    }
    s.tokens["bot"] = agent_token

    s.ids["active"] = world.active("general")
    s.ids["lapsed"] = world.active_many(1, valid_until=datetime(2025, 1, 1, tzinfo=UTC))[0]
    s.ids["requested"] = world.request("rob")
    s.ids["secret"] = world.hidden_record()
    s.ids["from_secret"] = world.request("dora", for_record_id=s.ids["secret"])
    world.person("eve", ("document_controller",), grant="superuser")
    world.call("eve", "ApprovePermit", permit=s.ids["from_secret"])
    world.issue(s.ids["from_secret"], who="eve")
    for name, record in s.ids.items():
        if name == "secret":
            continue
        s.keys[name] = str(
            world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=record)
        )
    s.keys["secret"] = str(
        world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=s.ids["secret"])
    )
    return s


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-permits"))
    try:
        yield Rig(seed(h))
    finally:
        h.close()


def _routes(rig: Rig) -> list[tuple[str, dict[str, Any]]]:
    key = rig.s.keys["active"]
    return [
        (LIST, {}),
        (BOARD, {}),
        (EXPORT, {"format": "csv"}),
        (f"/permits/{key}", {}),
        (f"/permits/{MISSING}", {}),
    ]


# --- the five readers ----------------------------------------------------------------------------


def test_no_token_is_401_on_every_route(rig: Rig) -> None:
    for path, params in _routes(rig):
        assert rig.get(None, path, **params).status_code == 401, path


def test_the_lowest_clearance_reader_gets_no_restricted_permit(rig: Rig) -> None:
    secret = rig.s.keys["from_secret"]
    lowest = rig.ok("uma", LIST)
    cleared = rig.ok("dora", LIST)
    assert secret not in [r["key"] for r in lowest["rows"]]
    assert secret in [r["key"] for r in cleared["rows"]]
    assert lowest["total"] == len(lowest["rows"])
    assert cleared["total"] == lowest["total"] + 1


def test_the_restricted_permit_is_left_out_of_the_board_counts(rig: Rig) -> None:
    lowest = rig.ok("uma", BOARD)
    cleared = rig.ok("dora", BOARD)
    assert cleared["counts"]["Active"] == lowest["counts"]["Active"] + 1
    lowest_keys = [r["key"] for area in lowest["areas"] for r in area["rows"]]
    cleared_keys = [r["key"] for area in cleared["areas"] for r in area["rows"]]
    assert rig.s.keys["from_secret"] not in lowest_keys
    assert rig.s.keys["from_secret"] in cleared_keys


def test_a_restricted_permit_answers_as_an_unknown_key_on_the_detail_route(rig: Rig) -> None:
    hidden = rig.get("uma", f"/permits/{rig.s.keys['from_secret']}")
    missing = rig.get("uma", f"/permits/{MISSING}")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    assert "record_not_found" in hidden.text
    assert NOT_FOUND in hidden.text
    assert rig.s.keys["from_secret"] not in hidden.text
    assert (
        rig.ok("dora", f"/permits/{rig.s.keys['from_secret']}")["row"]["key"]
        == (rig.s.keys["from_secret"])
    )


def test_the_agent_reader_gets_no_restricted_permit(rig: Rig) -> None:
    assert rig.s.keys["from_secret"] not in rig.keys_of("bot")
    assert rig.get("bot", f"/permits/{rig.s.keys['from_secret']}").status_code == 404


# --- lapsed, the board and the export ------------------------------------------------------------


def test_a_lapsed_permit_shows_lapsed_on_every_read_and_leads_the_board(rig: Rig) -> None:
    lapsed = rig.s.keys["lapsed"]
    rows = {r["key"]: r for r in rig.ok("uma", LIST, limit=500)["rows"]}
    assert rows[lapsed]["state"] == "Lapsed"
    assert rig.ok("uma", f"/permits/{lapsed}")["row"]["state"] == "Lapsed"
    board = rig.ok("uma", BOARD)
    assert board["areas"][0]["rows"][0]["key"] == lapsed
    assert board["areas"][0]["rows"][0]["state"] == "Lapsed"


def test_the_export_rows_equal_the_list_rows(rig: Rig) -> None:
    listed = [(r["key"], r["state"]) for r in rig.ok("uma", LIST)["rows"]]
    csv_response = rig.get("uma", EXPORT, format="csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    from_csv = [
        (row["number"], row["state"]) for row in csv.DictReader(io.StringIO(csv_response.text))
    ]
    jsonl_response = rig.get("uma", EXPORT, format="jsonl")
    assert jsonl_response.status_code == 200
    assert jsonl_response.headers["content-type"].startswith("application/x-ndjson")
    from_jsonl = [
        (row["number"], row["state"])
        for row in (json.loads(line) for line in jsonl_response.text.splitlines() if line)
    ]
    assert from_csv == listed
    assert from_jsonl == listed


def test_the_export_filters_reach_the_list_view(rig: Rig) -> None:
    listed = rig.keys_of("uma", state="Lapsed")
    csv_rows = list(
        csv.DictReader(io.StringIO(rig.get("uma", EXPORT, format="csv", state="Lapsed").text))
    )
    assert [row["number"] for row in csv_rows] == listed == [rig.s.keys["lapsed"]]


def test_the_fixed_paths_are_not_taken_for_a_key(rig: Rig) -> None:
    assert "areas" in rig.ok("uma", BOARD)
    assert rig.get("uma", EXPORT, format="csv").headers["content-type"].startswith("text/csv")


# --- bad values ----------------------------------------------------------------------------------


def test_bad_state_format_and_limit_are_422(rig: Rig) -> None:
    assert rig.get("uma", LIST, state="Bogus").status_code == 422
    assert rig.get("uma", EXPORT, format="csv", state="Bogus").status_code == 422
    assert rig.get("uma", EXPORT, format="xml").status_code == 422
    assert rig.get("uma", LIST, limit=0).status_code == 422
    assert rig.get("uma", LIST, limit=501).status_code == 422
    assert rig.get("uma", LIST, offset=-1).status_code == 422


# --- the routes are declared and documented ------------------------------------------------------


def test_the_four_routes_are_in_the_openapi_document(rig: Rig) -> None:
    paths = rig.h.app.openapi()["paths"]
    assert paths["/permits"]["get"]["operationId"] == "list_permits"
    assert paths["/permits/board"]["get"]["operationId"] == "get_permit_board"
    assert paths["/permits/export"]["get"]["operationId"] == "export_permits"
    assert paths["/permits/{key}"]["get"]["operationId"] == "get_permit"
