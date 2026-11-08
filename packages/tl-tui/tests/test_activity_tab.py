"""The Activity tab of the record view (P2-INS-T02): the table, the revisions view, the related
rows, the filter, paging, errors, and the plain cells.

The assertions compare with the text functions' own output, never with pinned wording.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, static_of
from rich.text import Text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from textual.widgets import DataTable, Input
from tl_core.insights.types import ActivityPage, ActivityRow
from tl_core.services.errors import ServiceError
from tl_tui.display import find_technical
from tl_tui.messages import OpenRecord, StatusMessage
from tl_tui.record_activity_text import (
    activity_cells,
    activity_columns,
    filter_title,
    row_matches,
)
from tl_tui.record_text import history_cells, history_columns
from tl_tui.widgets import activity_tab
from tl_tui.widgets.activity_tab import ActivityTab
from tl_tui.widgets.insights_tab import InsightsTab


class Host(App[None]):
    def __init__(self, client: FakeClient, record: dict[str, Any]) -> None:
        super().__init__()
        self.client = client
        self.record = record
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield ActivityTab(self.client, SCOPE, actor="user:me", id="tab")

    def on_mount(self) -> None:
        tab = self.query_one(ActivityTab)
        tab.show_record(self.record)
        tab.focus()

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)

    def on_open_record(self, message: OpenRecord) -> None:
        self.seen.append(message)


def setup() -> tuple[FakeClient, dict[str, Any]]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    return client, record


def record_calls(client: FakeClient) -> list[dict[str, Any]]:
    """Wrap ``client.activity`` so each call's keyword arguments are kept, in call order."""
    calls: list[dict[str, Any]] = []
    real = client.activity

    def recording(record_id: str, **kwargs: Any) -> ActivityPage:
        calls.append(kwargs)
        return real(record_id, **kwargs)

    client.activity = recording  # type: ignore[method-assign]
    return calls


def table_of(app: App[Any]) -> DataTable[Any]:
    return app.query_one("#activity-table", DataTable)


def cells_of(table: DataTable[Any]) -> list[tuple[str, ...]]:
    return [
        tuple(cell.plain if isinstance(cell, Text) else str(cell) for cell in table.get_row_at(i))
        for i in range(table.row_count)
    ]


def columns_of(table: DataTable[Any]) -> list[str]:
    return [str(column.label) for column in table.columns.values()]


def test_the_table_has_one_row_per_page_row_newest_first() -> None:
    client, record = setup()
    app = Host(client, record)
    expected = client.activity(record["id"]).rows
    seqs_in_events = sorted((e.seq for e in client.history(record["id"])), reverse=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        table = table_of(app)
        assert table.row_count == len(expected)
        seqs = [row.event.seq for row in app.query_one(ActivityTab).shown]
        assert seqs == seqs_in_events
        assert cells_of(table) == [
            activity_cells(row, app.query_one(ActivityTab).labels, technical=False, with_why=False)
            for row in expected
        ]
        assert columns_of(table) == list(activity_columns(expected, technical=False))

    run_pilot(app, scenario)


def test_v_shows_the_history_oldest_first_and_reads_revisions_only() -> None:
    client, record = setup()
    calls = record_calls(client)
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tab = app.query_one(ActivityTab)
        await pilot.press("v")
        await pilot.pause()
        assert calls[-1]["revisions_only"] is True
        assert calls[-1]["related"] is False
        table = table_of(app)
        assert columns_of(table) == list(history_columns(False))
        expected = [
            history_cells(e, tab.labels, technical=False) for e in client.history(record["id"])
        ]
        assert cells_of(table) == expected
        assert "· oldest first" in static_of(app, "#activity-title")

    run_pilot(app, scenario)


def test_r_toggles_related_in_the_call_and_in_the_title() -> None:
    client, record = setup()
    calls = record_calls(client)
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert calls[-1]["related"] is True
        assert static_of(app, "#activity-title") == (
            filter_title(False, True, "") + " · newest first"
        )
        await pilot.press("r")
        await pilot.pause()
        assert calls[-1]["related"] is False
        assert static_of(app, "#activity-title") == (
            filter_title(False, False, "") + " · newest first"
        )

    run_pilot(app, scenario)


def test_slash_filters_the_full_mode_by_a_cell_of_one_row() -> None:
    client, record = setup()
    app = Host(client, record)
    rows = client.activity(record["id"]).rows

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tab = app.query_one(ActivityTab)
        await pilot.press("slash")
        await pilot.pause()
        box = app.query_one("#activity-filter", Input)
        assert app.focused is box
        needle = activity_cells(rows[0], tab.labels, technical=False, with_why=False)[3]
        box.value = needle
        await pilot.pause()
        expected = [row for row in rows if row_matches(row, needle, tab.labels)]
        assert rows[0] in expected
        assert table_of(app).row_count == len(expected)
        box.value = "no such activity text anywhere"
        await pilot.pause()
        assert table_of(app).row_count == 0

    run_pilot(app, scenario)


def test_o_appends_the_older_page_below(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activity_tab, "PAGE_SIZE", 2)
    client, record = setup()
    full = client.activity(record["id"], limit=1000).rows
    assert len(full) >= 3, "the valve example needs more than one small page"
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert table_of(app).row_count == 2
        assert "o older" in static_of(app, "#activity-hint")
        await pilot.press("o")
        await pilot.pause()
        assert table_of(app).row_count == min(4, len(full))
        assert [row.event.seq for row in app.query_one(ActivityTab).shown] == [
            row.event.seq for row in full[: min(4, len(full))]
        ]

    run_pilot(app, scenario)


def test_a_client_error_posts_a_status_line_and_keeps_the_rows() -> None:
    client, record = setup()
    app = Host(client, record)

    def refused(record_id: str, **kwargs: Any) -> ActivityPage:
        raise ServiceError("activity is refused")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        before = cells_of(table_of(app))
        assert before
        client.activity = refused  # type: ignore[method-assign]
        await pilot.press("r")  # reloads from the first page; the read is refused
        await pilot.pause()
        assert cells_of(table_of(app)) == before
        assert any(
            isinstance(m, StatusMessage) and m.severity == "error" and "refused" in m.text
            for m in app.seen
        )

    run_pilot(app, scenario)


def test_enter_on_a_related_row_opens_its_record_and_on_another_row_nothing() -> None:
    client, record = setup()
    real = client.activity

    def with_related(record_id: str, **kwargs: Any) -> ActivityPage:
        page = real(record_id, **kwargs)
        first = page.rows[0]
        related = ActivityRow(
            event=first.event, kind=first.kind, related=True, from_id="REC-X", from_key="X-1"
        )
        return ActivityPage(rows=[related, *page.rows[1:]], next_before_seq=page.next_before_seq)

    client.activity = with_related  # type: ignore[method-assign]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        table_of(app).focus()
        await pilot.press("enter")
        await pilot.pause()
        opened = [m for m in app.seen if isinstance(m, OpenRecord)]
        assert len(opened) == 1
        assert opened[0].key == "X-1" and opened[0].scope == SCOPE and opened[0].follow is True
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert len([m for m in app.seen if isinstance(m, OpenRecord)]) == 1

    run_pilot(app, scenario)


def test_refresh_for_display_mode_makes_no_client_call() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        before = client.calls.count("activity")
        app.query_one(ActivityTab).refresh_for_display_mode()
        await pilot.pause()
        assert client.calls.count("activity") == before

    run_pilot(app, scenario)


def test_the_plain_cells_show_no_technical_token() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tab = app.query_one(ActivityTab)
        table = table_of(app)
        assert table.row_count > 0
        for cells in cells_of(table):
            for cell in cells:
                assert find_technical(cell, tab.labels) == []

    run_pilot(app, scenario)


def test_the_insights_stub_keeps_the_record_and_draws_its_word() -> None:
    _, record = setup()
    stub = InsightsTab()
    assert stub.record is None
    stub.show_record(record)
    assert stub.record is record

    class InsightsHost(App[None]):
        def compose(self) -> ComposeResult:
            yield InsightsTab(id="insights")

    app = InsightsHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert static_of(app, "#insights-body") == "Insights"

    run_pilot(app, scenario)
