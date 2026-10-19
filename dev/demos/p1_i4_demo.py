"""Driver for dev/demos/P1-I4.sh: the parts of the demo that are not a `tl` command.

Modes (first argument):

* ``prepare DIR``: write the files the script feeds to `tl xer` and `tl cost`: three synthetic XER
  updates a week apart (``tl_xer.synth``: no real project), one file that is not a schedule, and
  two cost exports.
* ``lose``: the typed rows and the job queue are lost, as after a restore from the archive.
* ``lake``: the lake answers with the float trend of A1230 (9 days, then 4: eroded).
* ``propose``: an agent proposes to publish snapshot 4 over MCP; nothing is published.
* ``reads``: the API, the TUI screens (F12, the comparison, the activities) and an agent's MCP read
  tools agree on the schedule.

Reads TL_DB (SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and, per mode,
TL_DEMO_AGENT_TOKEN, TL_OBJECT_ROOT, TL_LAKE_DIR. Every expectation is an assert: a failing demo
exits non-zero. Nothing printed holds a password or a token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int | str, text: str) -> None:
    print(f"PASS {clause}: {text}")


COST_JULY = """code,description,parent,uom,quantity_budget,quantity_actual,quantity_eac,hours_budget
4210,Piping,,,1000,400,1100,5000
4210-PIP,Pipe installation,4210,in-dia,600,450,600,3000
4210-WLD,Welding,4210,,400,150,500,2000
4220,Supports,,,,,,
"""
COST_AUGUST = """code,description,quantity_budget,quantity_actual,quantity_eac
4210-PIP,Pipe installation,600,520,640
4210-WLD,Welding,400,230,520
"""


def prepare(directory: str) -> None:
    from tl_xer.synth import make_xer, next_week, week_pair

    out = Path(directory)
    first, second = week_pair()
    third = next_week(second, 1, 2)  # a week on: the seeded slips, week 2 (no extra inspection)
    for name, scenario in (
        ("update-1.xer", first),
        ("update-2.xer", second),
        ("update-3.xer", third),
    ):
        (out / name).write_bytes(make_xer(scenario))
    (out / "not-a-schedule.xer").write_bytes(b"ERMHDR\t19.12\r\n%T\tTASK\r\n%F\tbad\x00column\r\n")
    (out / "cost-2026-07.csv").write_text(COST_JULY, encoding="utf-8")
    (out / "cost-2026-08.csv").write_text(COST_AUGUST, encoding="utf-8")
    say(
        f"wrote 3 XER updates (data dates {first.data_date}, {second.data_date}, {third.data_date})"
    )


def lose() -> None:
    from sqlalchemy import text
    from tl_adapters.db import open_uow

    with open_uow(os.environ["TL_DB"]) as uow:
        for table in (
            "sched_activity", "sched_relationship", "sched_wbs", "sched_calendar",
            "sched_activity_code", "sched_udf_value", "job_queue",
        ):  # fmt: skip
            uow.conn().execute(text(f"DELETE FROM {table}"))
    say("the typed rows of every snapshot and the job queue are gone")


def lake() -> None:
    from tl_lake import LakeConfig, LakeQueryService

    answer = LakeQueryService(LakeConfig.at(os.environ["TL_LAKE_DIR"])).query(
        "SELECT snapshot_number, total_float_days, previous_float_days, float_change_days, eroded "
        "FROM mart_float_trend WHERE activity_id = 'A1230' ORDER BY snapshot_number",
        caller="demo",
    )
    rows = [list(r) for r in answer.rows]
    say(f"mart_float_trend for A1230: {rows}")
    assert rows[0] == [1, 9.0, None, None, False], rows
    assert rows[1] == [2, 4.0, 9.0, -5.0, True], rows
    xer = LakeQueryService(LakeConfig.at(os.environ["TL_LAKE_DIR"])).query(
        "SELECT count(*) AS n FROM xer_task", caller="demo"
    )
    say(f"xer_task (bronze): {xer.rows[0][0]} rows from the files themselves")
    assert xer.rows[0][0] >= 42
    passed(
        8, "the lake holds the snapshots, the XER tables and the float trend of A1230 (9 to 4 days)"
    )


def agent_session(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp"],
        env={
            "TL_AGENT_TOKEN": os.environ["TL_DEMO_AGENT_TOKEN"],
            "TL_DB": os.environ["TL_DB"],
            "TL_ENV": os.environ.get("TL_ENV", "dev"),
            "TL_OBJECT_ROOT": os.environ["TL_OBJECT_ROOT"],
            "PATH": os.environ.get("PATH", ""),
        },
    )

    async def session() -> dict[str, Any]:
        async with Client(params) as mcp:
            names = {t.name for t in (await mcp.list_tools()).tools}
            assert {"propose_publish_schedule_snapshot", "compare_schedule_snapshots"} <= names
            result = await mcp.call_tool(name, arguments)
            assert not result.is_error and result.structured_content is not None, result
            return result.structured_content

    return asyncio.run(session())


def propose() -> None:
    from sqlalchemy import text
    from tl_adapters.db import open_uow

    found = agent_session(
        "propose_publish_schedule_snapshot", {"project": PROJECT, "schedule": "MAIN", "number": 4}
    )
    proposal = found["proposal"]
    assert proposal["status"] == "pending", proposal
    assert proposal["tool"] == "propose_publish_schedule_snapshot", proposal
    with open_uow(os.environ["TL_DB"], readonly=True) as uow:
        current = (
            uow.conn()
            .execute(
                text(
                    "SELECT current_snapshot_number FROM cur_schedule_schedule WHERE code = 'MAIN'"
                )
            )
            .scalar_one()
        )
    assert int(current) == 2, current
    Path(os.environ["TL_DEMO_STATE"]).write_text(proposal["proposal_id"])
    say(f"the agent's proposal {proposal['proposal_id']} is pending; snapshot 2 is still current")


async def screens(db: str) -> dict[str, Any]:
    from textual.widgets import DataTable
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.activity_screen import ActivityScreen
    from tl_tui.widgets.compare_screen import CompareScreen
    from tl_tui.widgets.schedule_screen import ScheduleScreen

    client = EmbeddedClient.for_target(db, actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo", is_admin=True)
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("f12")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ScheduleScreen)
            assert [v.code for v in screen.shown] == ["MAIN"]
            snapshots = screen.query_one("#sc-snapshots", DataTable).row_count
            assert screen.detail is not None
            current = next(s for s in screen.detail.snapshots if s.is_current)
            seen: dict[str, Any] = {"snapshots": snapshots, "current": current.number}
            # the table lists the newest first (4, 3, 2, 1): move to snapshot 2
            await pilot.press("tab", "down", "down")
            await pilot.pause()
            highlighted = screen.current_snapshot()
            assert highlighted is not None and highlighted.number == 2
            await pilot.press("c")
            await pilot.pause()
            compare = app.screen
            assert isinstance(compare, CompareScreen) and compare.comparison is not None
            seen["added"] = compare.comparison.totals["added"]
            seen["eroded"] = sum(1 for f in compare.comparison.float_changes if f.eroded)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            activities = app.screen
            assert isinstance(activities, ActivityScreen) and activities.page is not None
            seen["activities"] = activities.page.total
            return seen
    finally:
        client.close()


def reads() -> None:
    from tl_api.client import ApiClient
    from tl_api.client.auth import sign_in

    db, url = os.environ["TL_DB"], os.environ["TL_DEMO_URL"]
    api = ApiClient(url, sign_in(url, *DEMO).token)
    try:
        detail = api.get_schedule(PROJECT, "MAIN")
        comparison = api.compare_snapshots(PROJECT, "MAIN", new=2, old=1)
        page = api.list_activities(PROJECT, "MAIN", snapshot=2)
    finally:
        api.close()
    say(
        f"API: MAIN has {detail.snapshot_count} snapshots, "
        f"current {detail.current_snapshot_number}; "
        f"{comparison.totals['added']} added, {comparison.totals['removed']} removed"
    )
    shown = asyncio.run(screens(db))
    say(f"TUI (F12, comparison, activities): {shown}")
    assert shown["snapshots"] == detail.snapshot_count
    assert shown["current"] == detail.current_snapshot_number == 2
    assert shown["activities"] == page.total
    assert shown["added"] == comparison.totals["added"]
    mcp = agent_session("get_schedule", {"project": PROJECT, "schedule": "MAIN"})
    assert mcp["snapshot_count"] == detail.snapshot_count
    assert mcp["current_snapshot_number"] == detail.current_snapshot_number
    changes = agent_session(
        "compare_schedule_snapshots", {"project": PROJECT, "schedule": "MAIN", "new": 2, "old": 1}
    )
    assert changes["totals"]["date_shifts"] == comparison.totals["date_shifts"]
    float_old = {f["activity_id"]: f["old_days"] for f in changes["float_changes"]}
    assert float_old["A1230"] == 9.0
    now = agent_session(
        "resolve_schedule_activity",
        {"project": PROJECT, "schedule": "MAIN", "activity_id": "A1230", "as_of": "1"},
    )
    assert now["state"] == "as_of" and now["snapshot_number"] == 1
    say(
        f"MCP: {mcp['code']} has {mcp['snapshot_count']} snapshots; A1230 as of 1 is {now['state']}"
    )
    passed(
        "7",
        "the API, the TUI screens and an agent's MCP read tools agree on the schedule",
    )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "prepare":
        prepare(sys.argv[2])
    elif mode == "lose":
        lose()
    elif mode == "lake":
        lake()
    elif mode == "propose":
        propose()
    elif mode == "reads":
        reads()
    else:
        sys.exit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
