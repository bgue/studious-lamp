"""The inspection and checklist read routes (P2-INSP-T06): five GET routes and their readers.

The ledger is built by the quality module's commands (``insp_world.py``, loaded by path as
``test_api_punch.py`` loads ``punch_world.py``), never by a projection write. An inspection on a
restricted correspondence item is hidden from the lowest-clearance reader; a document controller
sees it. The five readers are ``uma`` (no clearance), ``dora`` (cleared for restricted records),
``vera`` (a viewer), ``ada`` (the company admin) and ``bot`` (an agent token).
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
from tl_core.auth import accounts, module_roles, sessions
from tl_mod_quality import insp_views as views
from tl_mod_quality.insp_views import MAX_LIMIT

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
PROJECT = "P123"
BASE = "/quality/inspections"
EXPORT = "/quality/inspections/export"
CHECKLISTS = "/quality/checklists"
MISSING_INSPECTION = "P123-INS-9999"
MISSING_CHECKLIST = "P123-CHK-9999"
READERS = ("uma", "dora", "vera", "ada", "bot")


def _load(name: str) -> ModuleType:
    """A quality-module test helper, loaded by path (the module is not on the import path)."""
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def insp_world() -> ModuleType:
    """``insp_world`` imports ``punch_world`` by name, so the punch helper is loaded first."""
    _load("punch_world")
    return _load("insp_world")


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

    def keys_of(self, who: str, **params: Any) -> list[str]:
        page = self.ok(who, BASE, **{"project": PROJECT, **params})
        return [r["key"] for r in page["rows"]]


def seed(h: Harness) -> Seeded:
    target = h.target or h.db
    world = insp_world().InspWorld(target)
    world.people()
    world.person("vic", ("user",))  # a user whose quality.view word the test withdraws
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
            label="inspections",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    s = Seeded(h, world)
    s.tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("uma", "rob", "dora", "vera", "ada", "vic")
    }
    s.tokens["bot"] = agent_token

    checklist = world.checklist(discipline="Mechanical")
    draft = world.checklist(publish=False, title="Draft pressure test", discipline="Civil")
    iwp = world.record(insp_world().IWP, "IWP-1")
    secret = world.hidden_record()

    s.ids["planned"] = world.plan(iwp)
    s.ids["scheduled"] = world.scheduled(iwp, checklist=checklist)
    s.ids["done"] = world.scheduled(iwp, checklist=checklist)
    world.recorded(s.ids["done"], answers=insp_world().answers(q1="no"))
    s.ids["secret"] = world.scheduled(secret, checklist=checklist, who="dora")
    s.ids["secret_subject"] = secret
    s.ids["checklist"] = checklist
    s.ids["draft"] = draft
    for name, record in s.ids.items():
        s.keys[name] = str(
            world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=record)
        )
    return s


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-insp"))
    try:
        yield Rig(seed(h))
    finally:
        h.close()


# --- the routes and their readers ---------------------------------------------------------------


def test_the_five_routes_are_registered(rig: Rig) -> None:
    paths = rig.h.app.openapi()["paths"]
    assert {
        "/quality/inspections",
        "/quality/inspections/export",
        "/quality/inspections/{key}",
        "/quality/checklists",
        "/quality/checklists/{key}",
    } <= set(paths)
    assert paths["/quality/inspections"]["get"]["operationId"] == "list_inspections"
    assert paths["/quality/inspections/export"]["get"]["operationId"] == "export_inspections"
    assert paths["/quality/inspections/{key}"]["get"]["operationId"] == "get_inspection"
    assert paths["/quality/checklists"]["get"]["operationId"] == "list_checklists"
    assert paths["/quality/checklists/{key}"]["get"]["operationId"] == "get_checklist"


def test_no_token_is_401_on_every_route(rig: Rig) -> None:
    for path in (BASE, EXPORT, CHECKLISTS, f"{BASE}/{rig.s.keys['planned']}"):
        response = rig.get(None, path, project=PROJECT)
        assert response.status_code == 401, path


def test_a_person_without_quality_view_gets_403_before_any_read(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = module_roles.holds_word

    def without_view(conn: Any, holder: Any, **kwargs: Any) -> bool:
        return False if holder.actor == "user:vic" else real(conn, holder, **kwargs)

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("an inspection read ran before the word check")

    monkeypatch.setattr(module_roles, "holds_word", without_view)
    for function in ("inspection_list", "inspection_detail", "checklist_list", "checklist_detail"):
        monkeypatch.setattr(views, function, boom)
    for path in (BASE, EXPORT, CHECKLISTS, f"{BASE}/{MISSING_INSPECTION}"):
        response = rig.get("vic", path, project=PROJECT)
        assert response.status_code == 403, path
        assert response.json()["error"] == "forbidden", path


def test_every_reader_gets_the_checklist_routes(rig: Rig) -> None:
    key = rig.s.keys["checklist"]
    for who in READERS:
        assert rig.ok(who, CHECKLISTS, project=PROJECT)["total"] == 2, who
        assert rig.ok(who, f"{CHECKLISTS}/{key}", project=PROJECT)["row"]["key"] == key, who


def test_the_lowest_reader_sees_no_restricted_inspection(rig: Rig) -> None:
    secret = rig.s.keys["secret"]
    page = rig.ok("uma", BASE, project=PROJECT)
    assert secret not in [r["key"] for r in page["rows"]]
    assert page["total"] == len(page["rows"]) == 3
    assert rig.get("uma", f"{BASE}/{secret}", project=PROJECT).status_code == 404


def test_the_cleared_reader_and_the_admin_see_the_restricted_inspection(rig: Rig) -> None:
    secret = rig.s.keys["secret"]
    for who in ("dora", "ada"):
        assert secret in rig.keys_of(who), who
        assert rig.ok(who, f"{BASE}/{secret}", project=PROJECT)["row"]["key"] == secret


def test_a_hidden_inspection_answers_as_an_unknown_key(rig: Rig) -> None:
    secret = rig.s.keys["secret"]
    for who in ("uma", "vera", "bot"):
        hidden = rig.get(who, f"{BASE}/{secret}", project=PROJECT)
        missing = rig.get(who, f"{BASE}/{MISSING_INSPECTION}", project=PROJECT)
        assert hidden.status_code == missing.status_code == 404, who
        assert hidden.json() == missing.json(), who
        assert "record_not_found" in hidden.text
        assert secret not in hidden.text


def test_a_hidden_inspection_is_not_counted_or_exported(rig: Rig) -> None:
    secret = rig.s.keys["secret"]
    total = rig.ok("uma", BASE, project=PROJECT)["total"]
    assert total == 3
    export = rig.get("uma", EXPORT, project=PROJECT, format="jsonl")
    assert export.status_code == 200
    assert secret not in export.text


# --- the list, its filters and its detail -------------------------------------------------------


def test_the_list_filters_each_reach_the_view(rig: Rig) -> None:
    planned = rig.s.keys["planned"]
    scheduled = rig.s.keys["scheduled"]
    done = rig.s.keys["done"]
    assert rig.keys_of("uma", project=PROJECT, state="Planned") == [planned]
    assert rig.keys_of("uma", project=PROJECT, state="Scheduled") == [scheduled]
    assert rig.keys_of("uma", project=PROJECT, state="Done") == [done]
    assert rig.keys_of("uma", project=PROJECT, state="Cancelled") == []
    assert set(rig.keys_of("uma", project=PROJECT, point="hold")) == {planned, scheduled, done}
    assert set(rig.keys_of("uma", project=PROJECT, inspector="M. Okafor")) == {scheduled, done}
    secret = rig.s.keys["secret"]
    subject = rig.s.keys["secret_subject"]
    assert rig.keys_of("dora", project=PROJECT, subject=subject) == [secret]
    assert rig.keys_of("uma", project=PROJECT, subject=subject) == []


def test_the_list_limit_bounds_the_rows_and_total_counts_the_matches(rig: Rig) -> None:
    page = rig.ok("uma", BASE, project=PROJECT, limit=1)
    assert len(page["rows"]) == 1
    assert page["total"] == 3


def test_the_detail_carries_the_answers_of_a_done_inspection(rig: Rig) -> None:
    detail = rig.ok("uma", f"{BASE}/{rig.s.keys['done']}", project=PROJECT)
    assert detail["row"]["state"] == "Done"
    assert detail["answers"]
    # the failed question raised one punch item, named by key on the detail
    assert detail["row"]["punch_count"] == len(detail["punch_keys"]) == 1


def test_export_rows_equal_the_list_rows_in_csv_and_jsonl(rig: Rig) -> None:
    listed = rig.keys_of("uma", project=PROJECT)
    response = rig.get("uma", EXPORT, project=PROJECT, format="csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    csv_keys = [row["number"] for row in csv.DictReader(io.StringIO(response.text))]
    assert csv_keys == listed

    response = rig.get("uma", EXPORT, project=PROJECT, format="jsonl")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    jsonl_keys = [json.loads(line)["number"] for line in response.text.splitlines()]
    assert jsonl_keys == listed


def test_export_is_not_read_as_a_key(rig: Rig) -> None:
    response = rig.get("uma", EXPORT, project=PROJECT)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


# --- bad arguments ------------------------------------------------------------------------------


def test_a_bad_state_or_point_is_422(rig: Rig) -> None:
    assert rig.get("uma", BASE, project=PROJECT, state="Bogus").status_code == 422
    assert rig.get("uma", BASE, project=PROJECT, point="Bogus").status_code == 422
    assert rig.get("uma", EXPORT, project=PROJECT, state="Bogus").status_code == 422
    assert rig.get("uma", CHECKLISTS, project=PROJECT, state="Bogus").status_code == 422
    assert rig.get("uma", EXPORT, project=PROJECT, format="xml").status_code == 422


def test_a_limit_above_the_maximum_is_422(rig: Rig) -> None:
    over = MAX_LIMIT + 1
    assert rig.get("uma", BASE, project=PROJECT, limit=over).status_code == 422
    assert rig.get("uma", BASE, project=PROJECT, limit=0).status_code == 422
    assert rig.get("uma", CHECKLISTS, project=PROJECT, limit=over).status_code == 422
