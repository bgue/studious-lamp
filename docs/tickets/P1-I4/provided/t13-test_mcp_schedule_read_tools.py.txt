"""The schedule and cost read tools (P1-I4-T13)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from tl_mod_cost.testing import CostWorld, row
from tl_mod_schedule.testing import ScheduleWorld

NAMES = (
    "list_schedules",
    "get_schedule",
    "list_schedule_activities",
    "get_schedule_activity",
    "compare_schedule_snapshots",
    "get_look_ahead",
    "resolve_schedule_activity",
    "get_activity_float_trend",
    "list_orphaned_links",
    "get_record_activity_links",
    "list_cost_codes",
    "get_cost_code",
    "list_cost_snapshots",
)


class Env:
    def __init__(self, harness: McpHarness, links: dict[str, str], record_ids: dict[str, str]):
        self.h = harness
        self.links = links
        self.records = record_ids

    def structured(self, tool: str, **arguments: Any) -> Any:
        return self.h.structured(tool, project="P123", **arguments)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    """Schedule MAIN with both demo files published (REC-A on A1230, REC-B on A1990, which the
    second file lacks and the worker has flagged), and two cost periods."""
    harness = McpHarness.build(tmp_path)
    try:
        world = ScheduleWorld(harness.db, tmp_path / "objects")
        world.define()
        one, two = world.two_weeks()
        world.publish(one)
        records = {key: world.record(key) for key in ("REC-A", "REC-B")}
        links = {
            "A1230": world.link(records["REC-A"], "A1230").stream_id,
            "A1990": world.link(records["REC-B"], "A1990").stream_id,
        }
        world.publish(two)
        cost = CostWorld(harness.db)
        cost.import_snapshot(
            [
                row("4210", "Piping", hours_budget=1000, amount_budget=80000),
                row("4210-PIP", "Pipe installation", "4210", uom="in-dia", hours_budget=600),
            ]
        )
        cost.import_snapshot(
            [row("4210-PIP", "Pipe installation", hours_budget=600, hours_actual=250)],
            period="2026-08",
            as_of="2026-08-31",
        )
        yield Env(harness, links, records)
    finally:
        harness.close()


def test_the_thirteen_tools_are_registered_read_only_and_described(env: Env) -> None:
    tools = {t.name: t for t in asyncio.run(env.h.server.list_tools())}
    for name in NAMES:
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint is True
        assert annotations.destructive_hint is False and tools[name].description
        assert "project" in tools[name].input_schema["properties"]
    assert set(tools["compare_schedule_snapshots"].input_schema["properties"]) == {
        "project",
        "schedule",
        "new",
        "old",
        "limit",
    }
    assert tools["get_look_ahead"].input_schema["properties"]["weeks"]["maximum"] == 26


def test_list_schedules_and_get_schedule_give_the_state_of_the_series(env: Env) -> None:
    [first] = env.structured("list_schedules")["result"]
    assert (first["code"], first["current_snapshot_number"], first["snapshot_count"]) == (
        "MAIN",
        2,
        2,
    )
    detail = env.structured("get_schedule", schedule="MAIN")
    assert [(s["number"], s["state"], s["is_current"]) for s in detail["snapshots"]] == [
        (2, "Published", True),
        (1, "Superseded", False),
    ]
    assert env.h.structured("list_schedules", project="OTHER")["result"] == []


def test_activities_come_in_pages_with_filters(env: Env) -> None:
    page = env.structured("list_schedule_activities", schedule="MAIN", limit=2, offset=1)
    assert (page["snapshot_number"], page["total"], page["offset"]) == (2, 21, 1)
    assert [a["activity_id"] for a in page["rows"]] == ["A1010", "A1020"]
    critical = env.structured("list_schedule_activities", schedule="MAIN", critical=True)
    assert critical["total"] == 10 and all(a["critical"] for a in critical["rows"])
    done = env.structured("list_schedule_activities", schedule="MAIN", status="completed")
    assert done["total"] == 8
    valves = env.structured("list_schedule_activities", schedule="MAIN", search="valves")
    assert [a["activity_id"] for a in valves["rows"]] == ["A1100", "A1110", "A1120", "A1250"]
    first = env.structured("list_schedule_activities", schedule="MAIN", snapshot=1, limit=1)
    assert first["snapshot_number"] == 1


def test_one_activity_has_its_predecessors_and_successors(env: Env) -> None:
    detail = env.structured("get_schedule_activity", schedule="MAIN", activity_id="A1230")
    assert detail["activity"]["name"] == "Install pipe rack supports"
    assert [r["pred_activity_id"] for r in detail["predecessors"]] == ["A1220"]
    assert [r["succ_activity_id"] for r in detail["successors"]] == ["A1240", "A2500"]
    earlier = env.structured(
        "get_schedule_activity", schedule="MAIN", activity_id="A1990", snapshot=1
    )
    assert earlier["snapshot_number"] == 1
    with pytest.raises(ToolError, match="has no activity 'A1990'"):
        env.h.call("get_schedule_activity", project="P123", schedule="MAIN", activity_id="A1990")


def test_compare_gives_the_shifts_and_the_erosion_of_the_week(env: Env) -> None:
    c = env.structured("compare_schedule_snapshots", schedule="MAIN", limit=3)
    assert (c["old"]["number"], c["new"]["number"], c["data_date_shift_days"]) == (1, 2, 7)
    assert c["totals"]["date_shifts"] == 9 and len(c["date_shifts"]) == 3 and c["cut"] is True
    assert [a["activity_id"] for a in c["added"]] == ["A2500"]
    assert [a["activity_id"] for a in c["removed"]] == ["A1990"]
    erosion = {f["activity_id"]: (f["old_days"], f["new_days"]) for f in c["float_changes"]}
    assert erosion["A1230"] == (9.0, 4.0)
    named = env.structured("compare_schedule_snapshots", schedule="MAIN", new=1, old=2)
    assert named["data_date_shift_days"] == -7
    with pytest.raises(ToolError, match="has no earlier snapshot to compare"):
        env.h.call("compare_schedule_snapshots", project="P123", schedule="MAIN", new=1)


def test_the_look_ahead_starts_at_the_data_date(env: Env) -> None:
    ahead = env.structured("get_look_ahead", schedule="MAIN")
    assert (ahead["window_start"], ahead["window_end"], ahead["weeks"]) == (
        "2026-10-12",
        "2026-11-09",
        4,
    )
    assert [r["activity_id"] for r in ahead["rows"]] == [
        "A1110",
        "A1140",
        "A1230",
        "A1150",
        "A2500",
        "A1240",
    ]
    assert ahead["counts"]["total"] == 6
    one = env.structured("get_look_ahead", schedule="MAIN", weeks=1)
    assert one["window_end"] == "2026-10-19" and one["counts"]["total"] == 4


def test_an_activity_resolves_now_as_of_a_snapshot_and_after_it_left(env: Env) -> None:
    now = env.structured("resolve_schedule_activity", schedule="MAIN", activity_id="A1230")
    assert (now["state"], now["snapshot_number"]) == ("current", 2)
    then = env.structured(
        "resolve_schedule_activity", schedule="MAIN", activity_id="A1230", as_of="1"
    )
    assert (then["state"], then["snapshot_number"]) == ("as_of", 1)
    by_date = env.structured(
        "resolve_schedule_activity", schedule="MAIN", activity_id="A1230", as_of="2026-10-08"
    )
    assert (by_date["state"], by_date["snapshot_number"]) == ("as_of", 1)
    left = env.structured("resolve_schedule_activity", schedule="MAIN", activity_id="A1990")
    assert (left["state"], left["activity"]) == ("orphaned", None)
    never = env.structured("resolve_schedule_activity", schedule="MAIN", activity_id="A9999")
    assert never["state"] == "unknown_activity"


def test_the_float_trend_and_the_orphaned_links(env: Env) -> None:
    trend = env.structured("get_activity_float_trend", schedule="MAIN", activity_id="A1230")
    assert [(p["snapshot_number"], p["total_float_days"]) for p in trend["result"]] == [
        (1, 9.0),
        (2, 4.0),
    ]
    [orphan] = env.structured("list_orphaned_links", schedule="MAIN")["result"]
    assert (orphan["link_id"], orphan["activity_id"]) == (env.links["A1990"], "A1990")
    assert orphan["from_id"] == env.records["REC-B"]


def test_a_record_lists_its_activity_links_and_what_they_resolve_to(env: Env) -> None:
    [kept] = env.structured("get_record_activity_links", record_id=env.records["REC-A"])["result"]
    assert (kept["link_id"], kept["ref_key"], kept["resolution"]["state"]) == (
        env.links["A1230"],
        "MAIN/A1230",
        "current",
    )
    [gone] = env.structured("get_record_activity_links", record_id=env.records["REC-B"])["result"]
    assert (gone["status"], gone["resolution"]["state"]) == ("stale", "orphaned")


def test_cost_codes_snapshots_and_one_codes_history(env: Env) -> None:
    codes = env.structured("list_cost_codes")["result"]
    assert [c["code"] for c in codes] == ["4210", "4210-PIP"]
    assert codes[1]["figures"]["hours_actual"] == 250.0
    assert [c["code"] for c in env.structured("list_cost_codes", parent="4210")["result"]] == [
        "4210-PIP"
    ]
    assert [c["code"] for c in env.structured("list_cost_codes", search="piping")["result"]] == [
        "4210"
    ]
    assert len(env.structured("list_cost_codes", limit=1)["result"]) == 1
    detail = env.structured("get_cost_code", code="4210")
    assert detail["children"] == ["4210-PIP"] and len(detail["history"]) == 1
    pip = env.structured("get_cost_code", code="4210-PIP")
    assert [h["period"] for h in pip["history"]] == ["2026-07", "2026-08"]
    snapshots = env.structured("list_cost_snapshots")["result"]
    assert [s["key"] for s in snapshots] == ["2026-08@1", "2026-07@1"]


def test_a_missing_thing_is_a_tool_error_and_another_project_sees_nothing(env: Env) -> None:
    with pytest.raises(ToolError, match="no schedule 'NOPE'"):
        env.h.call("get_schedule", project="P123", schedule="NOPE")
    with pytest.raises(ToolError, match="no schedule 'MAIN'"):
        env.h.call("get_schedule", project="OTHER", schedule="MAIN")
    with pytest.raises(ToolError, match="no cost code 'NOPE'"):
        env.h.call("get_cost_code", project="P123", code="NOPE")
    with pytest.raises(ToolError, match="less than or equal to 26"):
        env.h.call("get_look_ahead", project="P123", schedule="MAIN", weeks=40)
    # a record of another project is not readable through this one
    assert (
        env.h.structured(
            "get_record_activity_links", project="OTHER", record_id=env.records["REC-A"]
        )["result"]
        == []
    )


def test_every_tool_looks_only_in_its_own_project(env: Env) -> None:
    bound = {
        "get_schedule": {},
        "list_schedule_activities": {},
        "get_schedule_activity": {"activity_id": "A1230"},
        "compare_schedule_snapshots": {},
        "get_look_ahead": {},
        "resolve_schedule_activity": {"activity_id": "A1230"},
        "get_activity_float_trend": {"activity_id": "A1230"},
        "list_orphaned_links": {},
    }
    for tool, more in bound.items():
        with pytest.raises(ToolError, match="no schedule 'MAIN'"):
            env.h.call(tool, project="OTHER", schedule="MAIN", **more)
    with pytest.raises(ToolError, match="no cost code '4210'"):
        env.h.call("get_cost_code", project="OTHER", code="4210")
    assert env.h.structured("list_cost_codes", project="OTHER")["result"] == []
    assert env.h.structured("list_cost_snapshots", project="OTHER")["result"] == []


def test_the_tools_ask_the_authorizer_with_document_read_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, str]] = []

    def hook(actor: str, action: str, resource: str) -> None:
        seen.append((action, resource))

    harness = McpHarness.build(tmp_path, authorize_hook=hook)
    try:
        world = ScheduleWorld(harness.db, tmp_path / "objects")
        world.define()
        harness.call("list_schedules", project="P123")
        harness.call("get_schedule", project="P123", schedule="MAIN")
        harness.call("list_cost_snapshots", project="P123")
        with harness.factory(True) as uow:
            before = len(uow.ledger.read_after(0, limit=10_000))
        harness.call("list_schedules", project="P123")
        with harness.factory(True) as uow:
            assert len(uow.ledger.read_after(0, limit=10_000)) == before
    finally:
        harness.close()
    assert ("mcp.list_schedules", "schedules:P123") in seen
    assert ("mcp.get_schedule", "schedule:P123/MAIN") in seen
    assert ("mcp.list_cost_snapshots", "cost:P123") in seen
