"""The scaffold read routes (P2-I4B-T09b1): the list, one scaffold, the due list and the export.

The ledger is built by the scaffold module's commands (``scaffold_world.py``, loaded by path as
``test_api_punch.py`` loads its world). One scaffold is hidden: its request serves a restricted
correspondence item. Its hidden subject is set by a projection write, as
``packages/tl-modules/scaffold/tests/test_views.py::hidden_scaffold`` does (an IWP is not
confidential today). The standing scaffolds' next-due day is set by a projection write too, so the
due list, which takes the clock from the route, has them due. The last test dismantles a scaffold,
so it runs last in this module.
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
import tl_api.routes.scaffold as scaffold_routes
from harness import Harness
from sqlalchemy import text
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import ForbiddenError
from tl_mod_scaffold import views as scaffold_views
from tl_mod_scaffold.views import EXPORT_COLUMNS

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
PROJECT = "/projects/P123"
BASE = f"{PROJECT}/scaffolds"
DUE = f"{PROJECT}/scaffold-due"
EXPORT = f"{PROJECT}/scaffold-export"
OTHER = "/projects/P999/scaffolds"
MISSING = "P123-SCF-9999"
IWP = "awp.IWP"
#: The next-due day the seed writes on the standing scaffolds: before any day the tests run.
PAST_DUE = "2026-01-01"


def load_world() -> ModuleType:
    """The scaffold module's ``scaffold_world`` helper, loaded by path."""
    name = "scaffold_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "scaffold" / "tests" / "scaffold_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Seeded:
    """The keys and tokens the tests read by."""

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

    def scaffolds(self, who: str, **params: Any) -> dict[str, Any]:
        return self.ok(who, BASE, **params)

    def keys_of(self, who: str, **params: Any) -> list[str]:
        return [r["key"] for r in self.scaffolds(who, **params)["rows"]]

    def due_keys(self, who: str) -> list[str]:
        return [r["key"] for r in self.ok(who, DUE)]

    def export(self, who: str, **params: Any) -> Any:
        return self.get(who, EXPORT, **params)


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
            label="scaffold",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    s = Seeded(h, world)
    s.tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("ada", "uma", "rob", "dora", "sue", "vera")
    }
    s.tokens["bot"] = agent_token

    iwp = world.record(IWP, "IWP-1")
    # 1 Requested; 2 Designed, its request serves an IWP; 3 Erecting
    s.ids["requested"] = world.register(location_text="Unit 1")
    two = world.request(for_record_id=iwp)
    s.ids["designed"] = world.register(two, location_text="Unit 2")
    world.advance_as(s.ids["designed"], "Designed", "uma")
    s.ids["erecting"] = world.register(location_text="Unit 3")
    world.advance_as(s.ids["erecting"], "Erecting", "uma")
    # 4 Inspected (green, backdated); 5 In Use after a conditional inspection (yellow)
    s.ids["inspected"] = world.register(location_text="Unit 4")
    world.advance_as(s.ids["inspected"], "Erecting", "uma")
    world.call("sue", "TagScaffoldGreen", scaffold=s.ids["inspected"])
    s.ids["in_use"] = world.register(location_text="Unit 5")
    world.advance_as(s.ids["in_use"], "Erecting", "uma")
    world.call("sue", "TagScaffoldGreen", scaffold=s.ids["in_use"])
    world.call("uma", "ReleaseScaffold", scaffold=s.ids["in_use"])
    world.call(
        "uma",
        "InspectScaffold",
        scaffold=s.ids["in_use"],
        result="conditional",
        note="Toe boards",
    )
    # 6 Requested with a subject that a spreadsheet would read as a formula
    formula = world.request()
    s.ids["formula"] = str(
        world.call(
            "uma", "RegisterScaffold", request_id=formula, title="=SUM(A1)", location_text="Unit 6"
        ).stream_id
    )
    # 7 hidden: its request serves a restricted record (the projection write of test_views.py)
    request = world.request()
    subject = world.hidden_record()
    with h.backend(False) as uow:
        uow.conn().execute(
            text("UPDATE cur_requisitions_scaffold_request SET for_record_id = :s WHERE id = :i"),
            {"s": subject, "i": request},
        )
    s.ids["hidden"] = world.register(request, who="dora")
    world.advance_as(s.ids["hidden"], "Erecting", "dora")
    world.call("dora", "TagScaffoldGreen", scaffold=s.ids["hidden"])
    # The clock: an inspection cannot be dated before its scaffold's registration day, so the
    # standing scaffolds are made due by a projection write of their next-due day (as the views
    # test makes a hidden scaffold); the inspections above are real commands.
    with h.backend(False) as uow:
        uow.conn().execute(
            text("UPDATE cur_scaffold_scaffold SET next_due_on = :d WHERE id IN (:a, :b, :c)"),
            {
                "d": PAST_DUE,
                "a": s.ids["inspected"],
                "b": s.ids["in_use"],
                "c": s.ids["hidden"],
            },
        )
    for name, record in s.ids.items():
        s.keys[name] = str(
            world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=record)
        )
    return s


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-scaffold"))
    try:
        yield Rig(seed(h))
    finally:
        h.close()


def _visible(rig: Rig) -> list[str]:
    """The six keys a lowest reader sees (all but the hidden one), in key order."""
    names = ("requested", "designed", "erecting", "inspected", "in_use", "formula")
    return sorted(rig.s.keys[n] for n in names)


# --- the routes and their readers ---------------------------------------------------------------


def test_the_four_routes_are_registered(rig: Rig) -> None:
    paths = rig.h.app.openapi()["paths"]
    assert {
        "/projects/{project}/scaffolds",
        "/projects/{project}/scaffolds/{key}",
        "/projects/{project}/scaffold-due",
        "/projects/{project}/scaffold-export",
    } <= set(paths)
    assert paths["/projects/{project}/scaffolds"]["get"]["operationId"] == "list_scaffolds"
    assert paths["/projects/{project}/scaffolds/{key}"]["get"]["operationId"] == "get_scaffold"
    assert paths["/projects/{project}/scaffold-due"]["get"]["operationId"] == "list_scaffolds_due"
    assert paths["/projects/{project}/scaffold-export"]["get"]["operationId"] == "export_scaffolds"


def test_no_token_is_401_on_each_route(rig: Rig) -> None:
    key = rig.s.keys["inspected"]
    for path in (BASE, f"{BASE}/{key}", DUE, EXPORT):
        assert rig.get(None, path).status_code == 401, path


def test_an_agent_holds_read_and_sees_the_lowest_rows(rig: Rig) -> None:
    assert rig.scaffolds("bot")["total"] == 6
    assert rig.keys_of("bot") == _visible(rig)
    assert rig.export("bot").status_code == 200
    assert rig.get("bot", f"{BASE}/{MISSING}").status_code == 404


def test_the_lowest_reader_sees_the_visible_rows_and_not_the_hidden_one(rig: Rig) -> None:
    page = rig.scaffolds("rob")
    assert page["total"] == len(page["rows"]) == 6
    assert [r["key"] for r in page["rows"]] == _visible(rig)
    assert rig.s.keys["hidden"] not in [r["key"] for r in page["rows"]]
    assert rig.s.keys["hidden"] not in rig.due_keys("rob")
    assert rig.s.keys["hidden"] not in rig.export("rob").text
    assert rig.get("rob", f"{BASE}/{rig.s.keys['hidden']}").status_code == 404


def test_a_cleared_reader_sees_the_hidden_scaffold(rig: Rig) -> None:
    page = rig.scaffolds("dora")
    assert page["total"] == 7 and rig.s.keys["hidden"] in [r["key"] for r in page["rows"]]
    assert rig.s.keys["hidden"] in rig.due_keys("dora")
    detail = rig.ok("dora", f"{BASE}/{rig.s.keys['hidden']}")
    assert detail["row"]["key"] == rig.s.keys["hidden"]
    assert rig.s.keys["hidden"] in rig.export("dora").text


def test_a_plain_user_is_the_lowest_reader_for_restricted_items(rig: Rig) -> None:
    # The class rule: a restricted record is read by a document controller or an admin only.
    # A restricted-subject reader is not a separate level in the code (see the report).
    assert rig.s.keys["hidden"] not in rig.keys_of("uma")
    assert rig.s.keys["hidden"] in rig.keys_of("ada")


def test_a_company_admin_sees_what_the_class_rule_gives_the_admin(rig: Rig) -> None:
    assert rig.scaffolds("ada")["total"] == rig.scaffolds("dora")["total"] == 7
    assert rig.keys_of("ada") == rig.keys_of("dora")


def test_a_hidden_scaffold_answers_as_a_missing_key_and_as_another_project(rig: Rig) -> None:
    hidden = rig.get("rob", f"{BASE}/{rig.s.keys['hidden']}")
    missing = rig.get("rob", f"{BASE}/{MISSING}")
    other = rig.get("rob", f"{OTHER}/{rig.s.keys['inspected']}")
    assert hidden.status_code == missing.status_code == other.status_code == 404
    assert hidden.json() == missing.json() == other.json()
    assert "record_not_found" in hidden.text
    assert rig.s.keys["hidden"] not in hidden.text


# --- the list, its filters and the bounds ------------------------------------------------------


def test_the_list_filters_each_reach_the_view(rig: Rig) -> None:
    inspected = rig.s.keys["inspected"]
    in_use = rig.s.keys["in_use"]
    assert rig.keys_of("rob", state="Inspected") == [inspected]
    assert rig.keys_of("rob", state="In Use") == [in_use]
    assert rig.keys_of("rob", state="Dismantle") == []
    assert rig.keys_of("rob", tag="green") == [inspected]
    assert rig.keys_of("rob", tag="yellow") == [in_use]
    assert rig.keys_of("rob", overdue="true") == sorted([inspected, in_use])
    assert rig.keys_of("dora", tag="green") == sorted([inspected, rig.s.keys["hidden"]])


def test_bad_query_values_are_422(rig: Rig) -> None:
    assert rig.get("rob", BASE, state="x").status_code == 422
    assert rig.get("rob", BASE, tag="blue").status_code == 422
    assert rig.get("rob", BASE, limit=0).status_code == 422
    assert rig.get("rob", BASE, limit=501).status_code == 422
    assert rig.get("rob", EXPORT, format="xml").status_code == 422


def test_detail_carries_the_inspections_of_a_visible_scaffold(rig: Rig) -> None:
    detail = rig.ok("rob", f"{BASE}/{rig.s.keys['in_use']}")
    assert detail["row"]["state"] == "In Use" and detail["inspection_count"] == 2
    assert [i["result"] for i in detail["inspections"]] == ["pass", "conditional"]


# --- the export ----------------------------------------------------------------------------------


def test_the_csv_export_has_the_header_one_line_per_visible_row_and_no_id(rig: Rig) -> None:
    response = rig.export("rob")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == "attachment; filename=scaffolds-P123.csv"
    lines = response.text.split("\n")
    assert lines[0] == ",".join(EXPORT_COLUMNS) and "id" not in lines[0].split(",")
    assert len(lines) == 8 and lines[-1] == ""
    assert "\r" not in response.text


def test_a_subject_starting_with_equals_is_guarded_in_the_csv(rig: Rig) -> None:
    parsed = list(csv.DictReader(io.StringIO(rig.export("rob").text)))
    subjects = {row["key"]: row["subject"] for row in parsed}
    assert subjects[rig.s.keys["formula"]] == "'=SUM(A1)"


def test_the_jsonl_export_is_one_object_per_line(rig: Rig) -> None:
    response = rig.export("rob", format="jsonl")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["content-disposition"] == "attachment; filename=scaffolds-P123.jsonl"
    lines = response.text.split("\n")
    assert lines[-1] == "" and len(lines) == 7
    first = json.loads(lines[0])
    assert list(first) == list(EXPORT_COLUMNS)


# --- the due list and the word check -------------------------------------------------------------


def test_the_due_list_holds_the_standing_scaffolds_past_their_day(rig: Rig) -> None:
    assert rig.due_keys("rob") == sorted([rig.s.keys["inspected"], rig.s.keys["in_use"]])


def test_the_route_refuses_before_any_lookup_when_the_word_is_refused(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def refuse(*_args: Any, **_kw: Any) -> None:
        raise ForbiddenError("scaffold.view refused")

    def spy(*_args: Any, **_kw: Any) -> None:
        calls.append("view")

    monkeypatch.setattr(scaffold_routes, "require_word", refuse)
    monkeypatch.setattr(scaffold_views, "scaffold_list", spy)
    assert rig.get("rob", BASE).status_code == 403
    assert calls == []


# --- the dismantle (last: it changes the ledger the other tests read) -----------------------


def test_the_due_list_drops_a_scaffold_after_dismantling(rig: Rig) -> None:
    before = rig.due_keys("rob")
    rig.s.world.call("uma", "DismantleScaffold", scaffold=rig.s.ids["inspected"], reason="Done")
    assert rig.due_keys("rob") == [k for k in before if k != rig.s.keys["inspected"]]
