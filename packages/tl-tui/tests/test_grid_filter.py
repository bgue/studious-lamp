"""`RecordGrid.apply_filter`: the grid shows what `query_records` returns (P0-I4).

Over the FakeClient, which parses with the real parser, so the position of a syntax error is the
real one. The filter bar widget (a separate ticket) calls this method and shows its result.
"""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from fakes_live import FakeFeed
from helpers import run_pilot
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.widgets.grid import FilterResult, RecordGrid


def build(extra_rows: int = 0) -> tuple[TlApp, FakeClient]:
    client = FakeClient.with_valve_example(extra_rows=extra_rows)
    return TlApp(client), client


def keys_of(grid: RecordGrid) -> list[str]:
    return [r["key"] for r in grid.rows]


def test_a_filter_narrows_the_rows_and_reports_the_count() -> None:
    app, client = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        assert keys_of(grid) == ["FV-1001", "FV-1002", "FV-1003"]
        result = grid.apply_filter("status:Design")
        assert result == FilterResult(True, 2)
        assert keys_of(grid) == ["FV-1001", "FV-1002"]
        assert grid.match_count == 2 and grid.filter_text == "status:Design"
        assert "query_records" in client.calls and "count_records" in client.calls

    run_pilot(app, scenario)


def test_a_syntax_error_reports_its_position_and_changes_nothing() -> None:
    app, client = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        grid.apply_filter("status:Design")
        rows = list(grid.rows)
        bad = grid.apply_filter("status:Design )")
        assert not bad.ok and bad.position == 14 and bad.message
        assert grid.rows == rows and grid.filter_text == "status:Design"
        unknown = grid.apply_filter("nosuch:1")
        assert not unknown.ok and unknown.position == 0

    run_pilot(app, scenario)


def test_blank_text_clears_the_filter() -> None:
    app, client = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        grid.apply_filter("status:Installed")
        assert keys_of(grid) == ["FV-1003"]
        result = grid.apply_filter("   ")
        assert result == FilterResult(True, None)
        assert grid.filter_text == "" and grid.match_count is None
        assert keys_of(grid) == ["FV-1001", "FV-1002", "FV-1003"]

    run_pilot(app, scenario)


def test_sort_and_paging_keep_the_filter() -> None:
    app, client = build(extra_rows=30)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        grid.page_size = 10
        grid.apply_filter("title~filler")
        assert len(grid.rows) == 10 and grid.match_count == 30 and not grid.exhausted
        grid.sort_by("key")
        grid.sort_by("key")  # descending
        assert all("Filler" in r["title"] for r in grid.rows)
        assert keys_of(grid) == sorted(keys_of(grid), reverse=True)
        await pilot.press("end")
        await pilot.pause(0.5)
        assert len(grid.rows) == 30 and all("Filler" in r["title"] for r in grid.rows)

    run_pilot(app, scenario)


def test_a_live_refresh_keeps_the_filter_and_the_count_current() -> None:
    client = FakeClient.with_valve_example()
    feed = FakeFeed()
    app = TlApp(client, feed=feed)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        grid.apply_filter("status:Design")
        assert grid.match_count == 2
        record = client.get_record("project:P123", "FV-1003")
        assert record is not None
        # Someone moves FV-1003 into the filter: the live refresh must pick it up through the query.
        client._records[record["id"]]["status"] = "Design"  # pyright: ignore[reportPrivateUsage]
        event = client._next_event(  # pyright: ignore[reportPrivateUsage]
            client._records[record["id"]],
            "Workflow.Transitioned",
            {},
            "user:bob",  # pyright: ignore
        )
        feed.push(event)
        for _ in range(100):
            if grid.match_count == 3:
                break
            await pilot.pause(0.02)
        assert grid.match_count == 3 and "FV-1003" in keys_of(grid)
        assert grid.is_marked(record["id"])

    run_pilot(app, scenario)
