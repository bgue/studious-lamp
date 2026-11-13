"""P2-I5-T11a2: the weekly-plan, miss-reason and look-ahead reads of the awp module, over the HTTP
routes as the viewer ``vera`` reads them (the ``Rig`` and ``seed_awp`` of test_api_awp)."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from test_api_awp import BASE, Rig, load_world, seed_awp
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_mod_awp.names import WEEKLY_PLAN
from tl_mod_schedule.testing import BASE as SCHEDULE_BASE
from tl_mod_schedule.testing import ScheduleWorld
from tl_xer.synth import make_xer, week_pair

ROOT = Path(__file__).resolve().parents[3]
PLAN_DAY = "2026-11-02"
WEEK = "2026-W45"
CLASS_TABLE = "api_week_class"
WEEK_ROW_KEYS = {"id", "key", "week", "week_start", "state", "ppc", "closed_at"}
WEEK_DETAIL_KEYS = WEEK_ROW_KEYS | {"version", "commitments", "notes"}
COMMIT_KEYS = {
    "iwp_id",
    "iwp_key",
    "iwp_state",
    "foreman",
    "committed_hours",
    "outcome",
    "miss_reason",
}
LOOK_AHEAD_IWP_KEYS = {
    "id",
    "number",
    "state",
    "planned_start",
    "need_by",
    "evaluated",
    "ready",
    "checks_ok",
    "checks_total",
    "open_blocking",
}


def _progress_world() -> ModuleType:
    """``progress_world`` loaded by path (it imports ``awp_world`` by that name)."""
    name = "progress_world"
    if name in sys.modules:
        return sys.modules[name]
    load_world()
    path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "progress_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """The S4 seed, one closed plan of one committed IWP (done), and a published demo schedule
    with that IWP linked to activity A1230."""
    h = Harness.build(tmp_path_factory.mktemp("api-awp-weeks"))
    saved = dict(SCHEDULE_BASE)
    try:
        world = seed_awp(h, rollup=False)
        target = h.target or h.db
        progress = _progress_world()
        ww = progress.WeekWorld(progress.ProgressWorld(world))
        ww.standards()
        plan = ww.open(PLAN_DAY)
        iwp = ww.issued()
        ww.commit(plan, iwp, hours="40.0")
        ww.outcome(plan, iwp, "done")
        ww.close(plan)
        SCHEDULE_BASE["actor"] = "user:sue"
        sw = ScheduleWorld(target, h.root / "sched_objects")
        sw.define()
        first, _ = week_pair()
        sw.publish(sw.upload(make_xer(first)))
        sw.link(iwp, "A1230")
        yield {
            "rig": Rig(h, world),
            "target": target,
            "plan": plan,
            "number": str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=iwp)),
        }
    finally:
        SCHEDULE_BASE.clear()
        SCHEDULE_BASE.update(saved)
        h.close()


@contextmanager
def hidden_plan(target: DbTarget, plan_id: str) -> Iterator[None]:
    """The plan is restricted: the lowest viewer cannot open it (a test source, as the progress
    test uses), so it is absent from the list and answers as a missing week."""
    with open_uow(target) as uow:
        conn = uow.conn()
        conn.execute(
            text(f"CREATE TABLE IF NOT EXISTS {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT)")
        )
        conn.execute(text(f"DELETE FROM {CLASS_TABLE}"))
        ids = [
            str(r[0])
            for r in conn.execute(
                text("SELECT id FROM cur_core_record WHERE type = :t"), {"t": WEEKLY_PLAN}
            )
        ]
        for row_id in ids:
            cls = "restricted" if row_id == plan_id else "internal"
            conn.execute(
                text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                {"i": row_id, "c": cls},
            )
    source = ConfidentialSource(
        record_types=frozenset({WEEKLY_PLAN}),
        table=CLASS_TABLE,
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
    try:
        yield
    finally:
        cf.confidential_sources = real  # type: ignore[attr-defined]


# --- the weekly-plan list and detail -----------------------------------------------------------


def test_the_list_has_the_plan_with_its_ppc(rig: dict[str, Any]) -> None:
    body = rig["rig"].ok("/weeks")
    [row] = [r for r in body if r["week"] == WEEK]
    assert set(row) == WEEK_ROW_KEYS
    assert row["ppc"] is not None


def test_the_detail_has_one_commitment_with_the_declared_keys(rig: dict[str, Any]) -> None:
    body = rig["rig"].ok(f"/weeks/{WEEK}")
    assert set(body) == WEEK_DETAIL_KEYS
    [commitment] = body["commitments"]
    assert set(commitment) == COMMIT_KEYS
    assert commitment["iwp_key"] == rig["number"]
    assert commitment["outcome"] == "done"


def test_an_unknown_week_and_a_hidden_plan_answer_the_same_404(rig: dict[str, Any]) -> None:
    client = rig["rig"]
    unknown = client.get("/weeks/2026-W01")
    with hidden_plan(rig["target"], rig["plan"]):
        hidden = client.get(f"/weeks/{WEEK}")
        assert all(r["week"] != WEEK for r in client.get("/weeks").json())
    assert unknown.status_code == hidden.status_code == 404
    assert unknown.json()["error"] == hidden.json()["error"] == "record_not_found"
    assert unknown.json()["message"].replace("2026-W01", "W") == (
        hidden.json()["message"].replace(WEEK, "W")
    )
    assert client.get(f"/weeks/{WEEK}").status_code == 200


def test_a_week_that_is_not_an_iso_week_is_422(rig: dict[str, Any]) -> None:
    assert rig["rig"].get("/weeks/2026-45").status_code == 422


# --- the miss reasons and the look-ahead -------------------------------------------------------


def test_miss_reasons_are_keys(rig: dict[str, Any]) -> None:
    keys = rig["rig"].ok("/miss-reasons")
    assert "Weather" in keys
    assert all(isinstance(key, str) and " " not in key for key in keys)


def test_the_look_ahead_lists_the_linked_iwp_with_evaluated(rig: dict[str, Any]) -> None:
    body = rig["rig"].ok("/look-ahead", schedule="MAIN")
    [item] = [i for i in body["items"] if i["row"]["activity_id"] == "A1230"]
    [iwp] = item["iwps"]
    assert set(iwp) == LOOK_AHEAD_IWP_KEYS
    assert iwp["number"] == rig["number"]
    assert iwp["evaluated"] is False


def test_look_ahead_weeks_zero_is_422(rig: dict[str, Any]) -> None:
    assert rig["rig"].get("/look-ahead", schedule="MAIN", weeks=0).status_code == 422


# --- the token ---------------------------------------------------------------------------------


def test_no_token_is_401(rig: dict[str, Any]) -> None:
    anonymous = rig["rig"].anonymous
    for path in ("/weeks", f"/weeks/{WEEK}", "/miss-reasons", "/look-ahead?schedule=MAIN"):
        assert anonymous.get(f"{BASE}{path}").status_code == 401, path
