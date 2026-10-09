"""RecordGrid: paging, cursor, sort, selection, messages, TSV (P0-I2-T13)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from tl_core.services.errors import ServiceError
from tl_tui.messages import OpenRecord, RecordHighlighted, SelectionChanged, StatusMessage
from tl_tui.widgets import grid as grid_module
from tl_tui.widgets.grid import (
    DEFAULT_COLUMNS,
    GridColumn,
    RecordGrid,
    available_columns,
    cell_text,
    fit_cell,
    to_tsv,
)


class Host(App[None]):
    def __init__(self, client: FakeClient, **grid_args: Any) -> None:
        super().__init__()
        self.client = client
        self.grid_args = grid_args
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield RecordGrid(self.client, SCOPE, id="grid", **self.grid_args)

    def on_open_record(self, message: OpenRecord) -> None:
        self.seen.append(message)

    def on_record_highlighted(self, message: RecordHighlighted) -> None:
        self.seen.append(message)

    def on_selection_changed(self, message: SelectionChanged) -> None:
        self.seen.append(message)

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)


def _keys(grid: RecordGrid) -> list[str]:
    return [str(r["key"]) for r in grid.rows]


def test_pure_helpers() -> None:
    assert fit_cell("abc", 5) == "abc  "
    assert fit_cell("abc", 5, "right") == "  abc"
    assert fit_cell("abcdefgh", 5) == "abcd…"
    record = {"conformance": "nonconformant", "psets": {"valve_data": {"size_in": 6.0}}}
    assert cell_text(record, GridColumn("conformance", "C", 15)) == "✗ nonconformant"
    assert cell_text(record, GridColumn("psets.valve_data.size_in", "S", 8)) == "6"
    assert cell_text(record, GridColumn("psets.valve_data.fail_action", "F", 8)) == "—"
    rows = [{"key": "A", "title": "x\ty", "psets": {}}]
    cols = [GridColumn("key", "Key", 5), GridColumn("title", "Title", 5)]
    assert to_tsv(cols, rows) == "Key\tTitle\nA\tx y\n"


def test_tsv_exports_raw_values_not_display_symbols() -> None:
    record = {
        "conformance": "nonconformant",
        "version": 3,
        "updated_at": "2026-10-09T09:05:30+00:00",
        "status": None,
        "psets": {"valve_data": {"size_in": 6.0, "flag": True, "x": {"a": 1}}},
    }
    cols = [
        GridColumn("conformance", "Conf", 5),
        GridColumn("version", "Ver", 5),
        GridColumn("updated_at", "Upd", 5),
        GridColumn("status", "Status", 5),
        GridColumn("psets.valve_data.size_in", "Size", 5),
        GridColumn("psets.valve_data.flag", "Flag", 5),
        GridColumn("psets.valve_data.x", "X", 5),
        GridColumn("psets.valve_data.missing", "Missing", 5),
    ]
    line = to_tsv(cols, [record]).splitlines()[1]
    assert line == 'nonconformant\t3\t2026-10-09T09:05:30+00:00\t\t6.0\ttrue\t{"a":1}\t'


def test_available_columns_include_pset_properties() -> None:
    client = FakeClient.with_valve_example()
    keys = [c.key for c in available_columns(client.form_metadata(SCOPE, "core.Record"))]
    assert "key" in keys and "psets.valve_data.size_in" in keys
    assert "psets.valve_data.x.fat_witness_by" in keys
    assert [c.key for c in available_columns(None)][:5] == [c.key for c in DEFAULT_COLUMNS]


def test_loads_rows_and_renders_them() -> None:
    client = FakeClient.with_valve_example()
    host = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        assert _keys(grid) == ["FV-1001", "FV-1002", "FV-1003"]
        text = screen_text(host)
        assert "Key" in text.splitlines()[0]
        assert "FV-1002" in text and "✗ nonconformant" in text and "! warning" in text
        assert "▶[ ] FV-1001" in text

    run_pilot(host, scenario)


def test_cursor_moves_and_posts_highlight_messages() -> None:
    host = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("down", "down", "down", "up")
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        assert grid.cursor_row == 1
        keys = [m.record["key"] for m in host.seen if isinstance(m, RecordHighlighted) and m.record]
        assert keys == ["FV-1001", "FV-1002", "FV-1003", "FV-1002"]
        await pilot.press("end")
        assert grid.cursor_row == 2
        await pilot.press("home")
        assert grid.cursor_row == 0

    run_pilot(host, scenario)


def test_enter_opens_the_record_under_the_cursor() -> None:
    host = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        opened = [m for m in host.seen if isinstance(m, OpenRecord)]
        assert [(m.scope, m.key) for m in opened] == [(SCOPE, "FV-1002")]

    run_pilot(host, scenario)


def test_selection_space_extend_and_select_all() -> None:
    host = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        await pilot.press("space")
        assert [r["key"] for r in grid.selected_records()] == ["FV-1001"]
        await pilot.press("space")
        assert grid.selected_records() == []
        await pilot.press("shift+down", "shift+down")
        assert [r["key"] for r in grid.selected_records()] == ["FV-1001", "FV-1002", "FV-1003"]
        await pilot.press("space")  # cursor is on FV-1003, toggles it off
        assert [r["key"] for r in grid.selected_records()] == ["FV-1001", "FV-1002"]
        await pilot.press("ctrl+a")
        assert len(grid.selected_ids) == 3
        counts = [m.count for m in host.seen if isinstance(m, SelectionChanged)]
        assert counts[-1] == 3
        assert grid.summary() == "3 rows · 3 selected"
        assert "▶[x]" in screen_text(host)

    run_pilot(host, scenario)


def test_sort_cycles_ascending_descending_and_unsorted() -> None:
    host = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        await pilot.press("right", "right", "s")  # status column: Design, Design, Installed
        assert _keys(grid) == ["FV-1001", "FV-1002", "FV-1003"]
        assert grid.sort_key == "status" and not grid.sort_descending
        assert "Status ▲" in screen_text(host)
        await pilot.press("s")
        assert _keys(grid) == ["FV-1003", "FV-1001", "FV-1002"] and grid.sort_descending
        assert grid.summary() == "3 rows · sorted Status ▼"
        await pilot.press("s")
        assert grid.sort_key is None and _keys(grid) == ["FV-1001", "FV-1002", "FV-1003"]

    run_pilot(host, scenario)


def test_sort_keeps_the_cursor_on_the_same_record() -> None:
    host = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        await pilot.press("down", "s", "s")  # key column descending, cursor was on FV-1002
        assert _keys(grid) == ["FV-1003", "FV-1002", "FV-1001"]
        record = grid.cursor_record
        assert record is not None and record["key"] == "FV-1002"

    run_pilot(host, scenario)


def test_pages_in_more_rows_when_the_cursor_nears_the_end() -> None:
    client = FakeClient.with_valve_example(extra_rows=37)  # 40 rows
    host = Host(client, page_size=8)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        assert len(grid.rows) == 8 and not grid.exhausted
        for _ in range(7):
            await pilot.press("down")
        assert len(grid.rows) > 8
        await pilot.press("end")
        await host.workers.wait_for_complete()
        await pilot.pause()
        assert len(grid.rows) == 40 and grid.exhausted
        assert grid.cursor_row == 39
        assert client.calls.count("list_records") >= 5
        assert grid.summary().startswith("40 rows")

    run_pilot(host, scenario)


def test_scrolls_to_keep_the_cursor_visible_in_a_short_terminal() -> None:
    host = Host(FakeClient.with_valve_example(extra_rows=30))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        for _ in range(20):
            await pilot.press("down")
        await pilot.pause()
        assert grid.scroll_offset.y > 0
        assert "▶" in screen_text(host)

    run_pilot(host, scenario, size=(80, 12))


def test_neighbor_key_and_copy_text() -> None:
    host = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        assert grid.neighbor_key("FV-1001", 1) == "FV-1002"
        assert grid.neighbor_key("FV-1001", -1) is None
        assert grid.neighbor_key("FV-1003", 1) is None
        assert grid.neighbor_key("nope", 1) is None
        await pilot.press("space", "down", "space")
        lines = grid.copy_text().splitlines()
        assert lines[0].split("\t")[:3] == ["Key", "Title", "Status"]
        assert [line.split("\t")[0] for line in lines[1:]] == ["FV-1001", "FV-1002"]

    run_pilot(host, scenario)


def test_set_columns_shows_pset_columns() -> None:
    client = FakeClient.with_valve_example()
    host = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        grid.set_columns(
            [DEFAULT_COLUMNS[0], GridColumn("psets.valve_data.size_in", "size_in", 8, "right")]
        )
        await pilot.pause()
        text = screen_text(host)
        assert "size_in" in text and "     6" in text

    run_pilot(host, scenario)


def test_client_errors_become_status_messages() -> None:
    class Broken(FakeClient):
        def list_records(self, scope: str, **kwargs: Any) -> list[dict[str, Any]]:
            from tl_core.services.errors import ServiceError

            raise ServiceError("ledger unavailable")

    host = Host(Broken())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        statuses = [m for m in host.seen if isinstance(m, StatusMessage)]
        assert statuses and statuses[0].text == "ledger unavailable"
        assert statuses[0].severity == "error"

    run_pilot(host, scenario)


def test_mouse_click_header_sorts_and_double_click_opens() -> None:
    host = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        await pilot.click(RecordGrid, offset=(8, 0))  # inside the Key column header
        assert grid.sort_key == "key"
        await pilot.click(RecordGrid, offset=(8, 2))
        assert grid.cursor_row == 1
        await pilot.click(RecordGrid, offset=(8, 2), times=2)
        await pilot.pause()
        assert any(isinstance(m, OpenRecord) for m in host.seen)

    run_pilot(host, scenario)


def test_sort_is_requested_from_the_server_and_loads_only_one_page() -> None:
    client = FakeClient.with_valve_example(extra_rows=37)  # 40 rows
    host = Host(client, page_size=8)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        await pilot.press("s")  # Key ascending
        assert client.orders[-1] == [("key", "asc")]
        assert len(grid.rows) == 8 and not grid.exhausted
        await pilot.press("s")
        assert client.orders[-1] == [("key", "desc")]
        assert grid.rows[0]["key"] == "FV-2036"
        await pilot.press("s")  # third press: back to server order
        assert client.orders[-1] is None and grid.sort_key is None

    run_pilot(host, scenario)


def test_sort_on_unsupported_columns_explains_instead_of_sorting() -> None:
    client = FakeClient.with_valve_example()
    host = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        grid.set_columns(
            [
                GridColumn("psets.valve_data.size_in", "size_in", 8),
                GridColumn("conformance", "Conformance", 15),
            ]
        )
        await pilot.press("s")
        await pilot.press("right", "s")
        await pilot.pause()
        texts = [m.text for m in host.seen if isinstance(m, StatusMessage)]
        assert texts == [
            "Sort on pset columns arrives with the query language",
            "Sorting by Conformance is not available",
        ]
        assert grid.sort_key is None and client.orders == [None]

    run_pilot(host, scenario)


def test_end_pages_in_a_worker_reports_progress_and_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(grid_module, "END_CAP", 30)
    client = FakeClient.with_valve_example(extra_rows=57)  # 60 rows
    host = Host(client, page_size=8)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        await pilot.press("end")
        await host.workers.wait_for_complete()
        await pilot.pause()
        assert len(grid.rows) == 30 and not grid.exhausted
        assert grid.cursor_row == 29
        texts = [m.text for m in host.seen if isinstance(m, StatusMessage)]
        assert "Loading rows…" in texts
        assert any(t.startswith("Loading rows… ") for t in texts)
        assert texts[-1] == "Capped at 30 rows; narrow the list to see more"
        assert grid.summary().startswith("30+ rows")

    run_pilot(host, scenario)


def test_select_all_selects_loaded_rows_only_and_says_so() -> None:
    client = FakeClient.with_valve_example(extra_rows=37)
    host = Host(client, page_size=8)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert len(grid.selected_ids) == 8
        texts = [m.text for m in host.seen if isinstance(m, StatusMessage)]
        assert texts == ["8 loaded rows selected; more not loaded"]

    run_pilot(host, scenario)


def test_a_failed_page_fetch_keeps_the_list_open_and_a_later_move_retries() -> None:
    class Flaky(FakeClient):
        fail_offset: int | None = None

        def list_records(self, scope: str, **kwargs: Any) -> list[dict[str, Any]]:
            if kwargs.get("offset") == self.fail_offset:
                raise ServiceError("page unavailable")
            return super().list_records(scope, **kwargs)

    client = Flaky.with_valve_example(extra_rows=37)  # 40 rows
    assert isinstance(client, Flaky)
    host = Host(client, page_size=8)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)
        client.fail_offset = 8
        for _ in range(7):
            await pilot.press("down")
        await pilot.pause()
        assert len(grid.rows) == 8 and not grid.exhausted
        errors = [m for m in host.seen if isinstance(m, StatusMessage)]
        assert {(e.text, e.severity) for e in errors} == {("page unavailable", "error")}
        client.fail_offset = None
        await pilot.press("up", "down")  # still near the end: the next move retries and succeeds
        assert len(grid.rows) > 8

    run_pilot(host, scenario)


def test_a_failed_reload_leaves_the_rows_untouched() -> None:
    client = FakeClient.with_valve_example()
    host = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = host.query_one(RecordGrid)

        def boom(scope: str, **kwargs: Any) -> list[dict[str, Any]]:
            raise ServiceError("down")

        client.list_records = boom  # type: ignore[method-assign]
        await pilot.press("r")
        await pilot.pause()
        assert _keys(grid) == ["FV-1001", "FV-1002", "FV-1003"]

    run_pilot(host, scenario)
