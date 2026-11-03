"""The awp routes (T03a, T03c): the eight GET routes, counts, timeline, reports, CSV."""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from tl_adapters.db import open_uow
from tl_api.routes import awp as routes
from tl_core.auth import sessions
from tl_mod_awp import reports
from tl_mod_awp.worker import build_worker, requeue_orphans

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
BASE = "/projects/P123/awp"
MADE_UP_ID = "01J0000000000000000000000Z"


def load_world() -> ModuleType:
    """The ``awp_world`` helper of the module tests (the seed ledger of S4), loaded by path."""
    name = "awp_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "awp_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def seed_awp(h: Harness, *, rollup: bool) -> Any:
    """The S4 seed on the harness ledger; ``rollup`` runs the worker on it as well."""
    target = h.target or h.db
    world = load_world().World(target)
    world.people()
    world.editions()
    world.seed()
    if rollup:
        requeue_orphans(target)
        with build_worker(target) as worker:
            worker.runner.run_until_idle()
    return world


class Rig:
    def __init__(self, h: Harness, world: Any) -> None:
        self.h = h
        self.world = world
        _, token = sessions.sign_in(h.backend, username="vera", password=PASSWORD)
        self.client = h.client_for(None)
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        self.anonymous = h.client_for(None)

    def get(self, path: str, **params: Any) -> Any:
        return self.client.get(f"{BASE}{path}", params=params)

    def ok(self, path: str, **params: Any) -> Any:
        response = self.get(path, **params)
        assert response.status_code == 200, (path, response.text)
        return response.json()


@pytest.fixture(scope="module")
def plain(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    """The seed ledger as it is after S4: no rollup rows."""
    h = Harness.build(tmp_path_factory.mktemp("api-awp-plain"))
    try:
        yield Rig(h, seed_awp(h, rollup=False))
    finally:
        h.close()


@pytest.fixture(scope="module")
def rolled(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-awp-rolled"))
    try:
        yield Rig(h, seed_awp(h, rollup=True))
    finally:
        h.close()


# --- the eight GET routes (T03a) ----------------------------------------------------------------


def test_the_eight_get_routes_answer_with_the_seed_counts(plain: Rig) -> None:
    assert len(plain.ok("/cwps")) == 6
    assert len(plain.ok("/cwas")) == 4
    assert len(plain.ok("/wbs")) == 9
    assert len(plain.ok("/path")["steps"]) == 4
    assert len(plain.ok("/path/versions")) == 1
    assert plain.ok("/packages") == []
    assert plain.ok("/wbs/1.1.1")["code"] == "1.1.1"
    assert plain.ok("/cwps/P123-CWP-PIP-0001")["number"] == "P123-CWP-PIP-0001"


def test_the_list_filters_reach_the_view(plain: Rig) -> None:
    assert [r["number"] for r in plain.ok("/cwps", state="Planned")] == [
        "P123-CWP-CIV-0002",
        "P123-CWP-PIP-0004",
    ]
    assert len(plain.ok("/cwps", discipline="CIV")) == 2
    assert [r["number"] for r in plain.ok("/cwps", cwa="A2")] == ["P123-CWP-PIP-0003"]
    assert [r["code"] for r in plain.ok("/wbs", depth=1)] == ["1"]
    assert plain.ok("/path", version=1)["version"] == 1


def test_the_detail_carries_link_and_file_counts_and_the_timeline(plain: Rig) -> None:
    detail = plain.ok("/cwps/P123-CWP-PIP-0001")
    assert detail["link_count"] == 2  # the area and the WBS node
    assert detail["file_count"] == 0
    timeline = detail["timeline"]
    assert timeline
    assert all(set(row) == {"date", "who", "event", "note"} for row in timeline)
    assert all(len(row["date"]) == 10 and row["date"][4] == "-" for row in timeline)
    assert {"CWP.Defined", "CWP.Released"} <= {row["event"] for row in timeline}
    assert any(row["who"] == "user:sue" and row["event"] == "CWP.Released" for row in timeline)


def test_the_timeline_note_is_the_reason_or_note_read_literally(plain: Rig) -> None:
    """D30: ``reason`` first, then ``note``; a reason that is not text gives "", as built."""
    assert routes._note({"reason": "scope change"}) == "scope change"
    assert routes._note({"note": "n"}) == "n"
    assert routes._note({"reason": "", "note": "n"}) == "n"
    assert routes._note({"reason": 5, "note": "n"}) == ""
    assert routes._note({}) == ""
    assert routes._note({"reason": "x" * 500}) == "x" * routes.NOTE_LIMIT


def test_a_returned_package_shows_its_reason_in_the_timeline(tmp_path: Path) -> None:
    h = Harness.build(tmp_path)
    try:
        world = seed_awp(h, rollup=False)
        cwp = world.rows("SELECT id FROM cur_core_record WHERE key = 'P123-CWP-PIP-0001'")[0]["id"]
        world.call("sue", "ReturnCwp", cwp=cwp, reason="scope change")
        rig = Rig(h, world)
        notes = [r["note"] for r in rig.ok("/cwps/P123-CWP-PIP-0001")["timeline"]]
        assert "scope change" in notes
    finally:
        h.close()


def test_a_wbs_total_is_null_without_rollup_rows(plain: Rig) -> None:
    """D30: the seed has no rollup rows, so a node mapped to cost codes has no total."""
    node = plain.ok("/wbs/1.1.1")
    assert node["total_hours"] is None
    assert node["by_cost_code"] == {}
    assert all(row["total_hours"] is None for row in plain.ok("/wbs"))


def test_a_wbs_total_follows_the_rollup_rows(rolled: Rig) -> None:
    node = rolled.ok("/wbs/1.1.1")
    assert float(node["total_hours"]) == 4200.0
    assert set(node["by_cost_code"]) == {"4210-PIP-WLD", "4210-PIP-ERC"}


def test_a_wbs_code_with_dots_is_one_path_segment(plain: Rig) -> None:
    assert plain.ok("/wbs/1.2.3")["parent_code"] == "1.2"


def test_a_bad_package_kind_is_a_422_before_the_view(plain: Rig) -> None:
    assert plain.get("/packages", kind="XWP").status_code == 422
    assert plain.get("/cwps", state="x" * 65).status_code == 422
    assert plain.get("/wbs", depth=0).status_code == 422
    assert plain.get("/path", version=0).status_code == 422


def test_a_missing_cwp_and_a_made_up_id_answer_alike(plain: Rig) -> None:
    for key in ("P123-CWP-9999", MADE_UP_ID):
        response = plain.get(f"/cwps/{key}")
        body = response.json()
        assert response.status_code == 404
        assert body["error"] == "record_not_found"
        assert body["message"] == f"no CWP {key!r}"


def test_a_missing_node_and_a_missing_path_version_are_404(plain: Rig) -> None:
    assert plain.get("/wbs/9.9.9").status_code == 404
    assert plain.get("/path", version=7).status_code == 404


def test_every_route_needs_a_token(plain: Rig) -> None:
    for path in ("/cwps", "/cwps/P123-CWP-PIP-0001", "/cwas", "/wbs", "/wbs/1", "/path"):
        assert plain.anonymous.get(f"{BASE}{path}").status_code == 401, path
    assert plain.anonymous.get(f"{BASE}/reports/cwp_status").status_code == 401


# --- the reports (T03c) -------------------------------------------------------------------------

COLUMNS = {
    "cwp_status": list(reports.StatusRow.model_fields),
    "wbs_vs_cost_code": list(reports.CostRow.model_fields),
    "cwa_sequence": list(reports.SequenceRow.model_fields),
}


@pytest.mark.parametrize("name", sorted(COLUMNS))
def test_a_report_is_a_report_view_in_json(rolled: Rig, name: str) -> None:
    body = rolled.ok(f"/reports/{name}")
    assert body["name"] == name
    assert body["columns"] == COLUMNS[name]
    assert body["rows"]
    assert all(len(row) == len(COLUMNS[name]) for row in body["rows"])
    assert all(isinstance(cell, str) for row in body["rows"] for cell in row)


def test_the_status_report_has_a_row_per_state_and_the_cwa_report_one_per_area(rolled: Rig) -> None:
    assert len(rolled.ok("/reports/cwa_sequence")["rows"]) == 4
    assert rolled.ok("/reports/cwp_status")["rows"]


@pytest.mark.parametrize("name", sorted(COLUMNS))
def test_the_csv_cells_equal_the_json_cells(rolled: Rig, name: str) -> None:
    response = rolled.get(f"/reports/{name}", format="csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    parsed = list(csv.reader(io.StringIO(response.text)))
    assert parsed[0] == COLUMNS[name]
    assert parsed[1:] == rolled.ok(f"/reports/{name}")["rows"]


def test_the_cost_report_cells_take_the_cost_system_hours(rolled: Rig) -> None:
    body = rolled.ok("/reports/wbs_vs_cost_code")
    assert any("4210-PIP-WLD" in row for row in body["rows"])


def test_an_unknown_report_name_is_a_404_and_a_bad_format_a_422(rolled: Rig) -> None:
    response = rolled.get("/reports/x")
    assert response.status_code == 404
    assert response.json()["error"] == "record_not_found"
    assert response.json()["message"] == "no report 'x'"
    assert rolled.get("/reports/cwp_status", format="xml").status_code == 422


def test_the_reports_are_the_report_functions_over_the_same_ledger(rolled: Rig) -> None:
    with open_uow(rolled.h.target or rolled.h.db, readonly=True) as uow:
        want = reports.cwa_sequence(uow.conn(), "project:P123")
    cells = [[reports.format_value(getattr(r, c)) for c in COLUMNS["cwa_sequence"]] for r in want]
    assert rolled.ok("/reports/cwa_sequence")["rows"] == cells
