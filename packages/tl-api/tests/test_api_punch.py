"""The punch routes (P2-PUNCH-T03): the three GET routes, the command door and five kinds of reader.

The ledger is built by the quality module's commands (``punch_world.py``, loaded by path as
``test_api_awp.py`` loads its world), never by a projection write. A restricted correspondence item
is the source of one punch item; the lowest-clearance reader must not see it, a document controller
must.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from tl_core.auth import accounts, sessions
from tl_mod_quality.handlers.punch import MSG_SELF_VERIFY

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
PROJECT = "/projects/P123"
BASE = f"{PROJECT}/punch"
COUNTS = f"{PROJECT}/punch-counts"
MISSING = "P123-PUN-9999"
TODAY_OVERDUE = "2026-01-01"  # before the day the tests run, so an Open item with it is overdue


def load_world() -> ModuleType:
    """The quality module's ``punch_world`` helper (the ledger of the S2 tests), loaded by path."""
    name = "punch_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / "punch_world.py"
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
        return self.client(who).get(path, params=params)

    def ok(self, who: str, path: str, **params: Any) -> Any:
        response = self.get(who, path, **params)
        assert response.status_code == 200, (path, response.text)
        return response.json()

    def post(self, who: str, name: str, body: dict[str, Any]) -> Any:
        return self.client(who).post(f"/commands/{name}", json={"scope": "project:P123", **body})

    def rows(self, who: str, **params: Any) -> list[dict[str, Any]]:
        return self.ok(who, BASE, **params)["rows"]

    def keys_of(self, who: str, **params: Any) -> list[str]:
        return [r["key"] for r in self.rows(who, **params)]


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
            label="punch",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    s = Seeded(h, world)
    s.tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("uma", "rob", "dora")
    }
    s.tokens["bot"] = agent_token

    s.ids["open"] = world.raise_item(
        "uma",
        "Stair guard missing",
        area="L2",
        system="HVAC",
        due_on=TODAY_OVERDUE,
        assignee="Ferrari",
        category="A",
    )
    s.ids["cleared"] = world.raise_item("uma", "Door closer loose")
    world.call("uma", "ClearPunchItem", punch_item=s.ids["cleared"], note="Tightened")
    s.ids["verified"] = world.raise_item("uma", "Cable tray gap")
    world.call("uma", "ClearPunchItem", punch_item=s.ids["verified"], note="Closed")
    world.call("rob", "VerifyPunchItem", punch_item=s.ids["verified"])
    s.ids["secret"] = world.hidden_record()
    s.ids["from_secret"] = str(
        world.call(
            "dora", "RaisePunchItem", subject="From the secret", from_record_id=s.ids["secret"]
        ).stream_id
    )
    for name, record in s.ids.items():
        s.keys[name] = str(
            world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=record)
        )
    return s


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-punch"))
    try:
        yield Rig(seed(h))
    finally:
        h.close()


# --- the routes and their five readers ----------------------------------------------------------


def _paths(rig: Rig) -> list[str]:
    key = rig.s.keys["open"]
    return [BASE, f"{BASE}/{key}", COUNTS, f"{BASE}/{MISSING}"]


def test_the_three_routes_are_registered(rig: Rig) -> None:
    paths = rig.h.app.openapi()["paths"]
    assert {
        "/projects/{project}/punch",
        "/projects/{project}/punch/{key}",
        "/projects/{project}/punch-counts",
    } <= set(paths)
    assert paths["/projects/{project}/punch"]["get"]["operationId"] == "list_punch_items"
    assert paths["/projects/{project}/punch/{key}"]["get"]["operationId"] == "get_punch_item"
    assert paths["/projects/{project}/punch-counts"]["get"]["operationId"] == "get_punch_counts"


def test_no_token_is_401_on_every_route(rig: Rig) -> None:
    for path in _paths(rig):
        assert rig.get(None, path).status_code == 401, path


def test_an_agent_holds_read(rig: Rig) -> None:
    assert rig.ok("bot", BASE)["total"] == 3
    assert rig.ok("bot", COUNTS)["Open"] == 1
    assert rig.get("bot", f"{BASE}/{MISSING}").status_code == 404


def test_the_lowest_clearance_reader_sees_the_rows_and_not_the_secret(rig: Rig) -> None:
    page = rig.ok("uma", BASE)
    assert page["total"] == len(page["rows"]) == 3
    assert rig.ok("uma", COUNTS) == {"Open": 1, "Cleared": 1, "Verified": 1, "Void": 0}
    assert rig.keys_of("uma", **{"from": rig.s.keys["secret"]}) == []


def test_a_cleared_reader_sees_the_same_rows_and_the_secret_item(rig: Rig) -> None:
    lowest = rig.keys_of("uma")
    cleared = rig.keys_of("dora")
    assert [k for k in cleared if k != rig.s.keys["from_secret"]] == lowest
    assert rig.s.keys["from_secret"] in cleared
    assert rig.ok("dora", COUNTS)["Open"] == 2
    assert (
        rig.ok("dora", f"{BASE}/{rig.s.keys['from_secret']}")["row"]["key"]
        == (rig.s.keys["from_secret"])
    )


def test_a_hidden_item_answers_as_a_missing_key(rig: Rig) -> None:
    hidden = rig.get("uma", f"{BASE}/{rig.s.keys['from_secret']}")
    missing = rig.get("uma", f"{BASE}/{MISSING}")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    assert "record_not_found" in hidden.text
    assert rig.s.keys["from_secret"] not in hidden.text


# --- the list, its filters and its detail -------------------------------------------------------


def test_the_list_filters_each_reach_the_view(rig: Rig) -> None:
    open_key = rig.s.keys["open"]
    cleared_key = rig.s.keys["cleared"]
    verified_key = rig.s.keys["verified"]
    assert rig.keys_of("uma", state="Open") == [open_key]
    assert rig.keys_of("uma", state="Cleared") == [cleared_key]
    assert rig.keys_of("uma", state="Verified") == [verified_key]
    assert rig.keys_of("uma", state="Void") == []
    assert rig.keys_of("uma", category="A") == [open_key]
    assert rig.keys_of("uma", area="L2") == [open_key]
    assert rig.keys_of("uma", system="HVAC") == [open_key]
    assert rig.keys_of("uma", assignee="Ferrari") == [open_key]
    assert rig.keys_of("uma", overdue="true") == [open_key]
    assert rig.keys_of("dora", **{"from": rig.s.keys["secret"]}) == [rig.s.keys["from_secret"]]
    assert rig.keys_of("uma", **{"from": "P123-SRC-NOPE"}) == []


def test_total_counts_the_visible_matches_before_the_limit(rig: Rig) -> None:
    page = rig.ok("uma", BASE, limit=1)
    assert page["total"] == 3 and len(page["rows"]) == 1
    assert rig.ok("dora", BASE)["total"] == 4


def test_bad_query_values_are_422(rig: Rig) -> None:
    assert rig.get("uma", BASE, state="x").status_code == 422
    assert rig.get("uma", BASE, category="D").status_code == 422
    assert rig.get("uma", BASE, limit=0).status_code == 422
    assert rig.get("uma", BASE, limit=501).status_code == 422


def test_detail_carries_the_row_and_the_clear_and_verify_facts(rig: Rig) -> None:
    cleared = rig.ok("uma", f"{BASE}/{rig.s.keys['cleared']}")
    assert cleared["row"]["state"] == "Cleared"
    assert (cleared["cleared_by"], cleared["clear_note"]) == ("user:uma", "Tightened")
    verified = rig.ok("uma", f"{BASE}/{rig.s.keys['verified']}")
    assert verified["verified_by"] == "user:rob" and verified["row"]["state"] == "Verified"
    opened = rig.ok("uma", f"{BASE}/{rig.s.keys['open']}")
    assert (opened["row"]["area"], opened["row"]["system"]) == ("L2", "HVAC")
    assert opened["row"]["due_on"] == TODAY_OVERDUE and opened["reopen_count"] == 0


def test_the_command_door_writes_what_the_routes_read(rig: Rig) -> None:
    before = rig.ok("uma", COUNTS)
    raised = rig.post("uma", "RaisePunchItem", {"subject": "Via the door", "category": "B"})
    assert raised.status_code == 200, raised.text
    mine = [r for r in rig.rows("uma", state="Open") if r["subject"] == "Via the door"]
    assert len(mine) == 1
    item = mine[0]["id"]
    assert rig.ok("uma", COUNTS)["Open"] == before["Open"] + 1

    assert rig.post("uma", "VerifyPunchItem", {"punch_item": item}).status_code == 403
    assert (
        rig.post("uma", "ClearPunchItem", {"punch_item": item, "note": "Done"}).status_code == 200
    )
    assert rig.post("uma", "VerifyPunchItem", {"punch_item": item}).status_code == 403
    verified = rig.post("rob", "VerifyPunchItem", {"punch_item": item})
    assert verified.status_code == 200, verified.text
    assert rig.ok("uma", COUNTS)["Verified"] == before["Verified"] + 1


def test_the_clearer_may_not_verify_through_the_door(rig: Rig) -> None:
    raised = rig.post("uma", "RaisePunchItem", {"subject": "Cleared by rob"})
    assert raised.status_code == 200, raised.text
    item = [r for r in rig.rows("uma", state="Open") if r["subject"] == "Cleared by rob"][0]["id"]
    assert (
        rig.post("rob", "ClearPunchItem", {"punch_item": item, "note": "Mine"}).status_code == 200
    )
    refused = rig.post("rob", "VerifyPunchItem", {"punch_item": item})
    assert refused.status_code == 403 and MSG_SELF_VERIFY in refused.text


def test_the_door_refuses_a_raised_by_field(rig: Rig) -> None:
    response = rig.post("uma", "RaisePunchItem", {"subject": "Forged", "raised_by": "user:rob"})
    assert response.status_code == 422
