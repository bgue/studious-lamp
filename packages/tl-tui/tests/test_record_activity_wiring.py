"""The record view's Activity tab (where History was) and the Insights pane (P2-INS T02b).

Pilot tests on ``FakeClient``. ``4`` and ``h`` open the Activity tab, ``9`` the Insights pane;
``v`` on the Activity tab shows the record's revisions as the History table drew them before.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.pilot import Pilot
from textual.widgets import DataTable, TabbedContent
from tl_core.insights.types import ActivityRow
from tl_core.ledger import Event
from tl_core.services.commands import UpdateRecord
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.labels_load import load_labels
from tl_tui.record_activity_text import TECHNICAL_COLUMNS, what_text
from tl_tui.record_text import history_cells, history_columns
from tl_tui.widgets.activity_tab import ActivityTab
from tl_tui.widgets.insights_tab import InsightsTab
from tl_tui.widgets.record_view import RecordView


class Host(App[None]):
    def __init__(
        self, client: FakeClient, *, actor: str = "user:dev", is_admin: bool = False
    ) -> None:
        super().__init__()
        self.client = client
        self.actor = actor
        self.is_admin = is_admin
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        yield RecordView(self.client, SCOPE, "FV-1001", id="record")


def _tabs(app: App[None]) -> TabbedContent:
    return app.query_one("#rv-tabs", TabbedContent)


def _updated_valve(client: FakeClient) -> None:
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    client.update_record(
        UpdateRecord(
            actor="user:dev",
            source="tui",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=record["version"],
            changes={"title": "New title", "description": "d"},
        )
    )


def _event(event_type: str, changes: Any) -> Event:
    when = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
    return Event(
        event_type=event_type,
        payload={} if changes is None else {"changes": changes},
        seq=1,
        event_id="E1",
        stream_id="S1",
        stream_type="core.Record",
        stream_version=2,
        scope=SCOPE,
        actor="user:dev",
        recorded_at=when,
        effective_at=when,
        correlation_id="C1",
        causation_id=None,
        source="tui",
        prev_hash=None,
        hash="H1",
    )


def test_4_and_h_open_the_activity_tab() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        assert _tabs(app).active == "tab-activity"
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("h")
        await pilot.pause()
        assert _tabs(app).active == "tab-activity"

    run_pilot(app, scenario, size=(120, 40))


def test_9_opens_the_insights_pane_with_the_record() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("9")
        await pilot.pause()
        assert _tabs(app).active == "tab-insights"
        insights = app.query_one("#insights-tab", InsightsTab)
        assert insights.record is not None and insights.record["key"] == "FV-1001"
        assert "Insights" in screen_text(app)

    run_pilot(app, scenario, size=(120, 40))


def test_activity_rows_for_a_record_with_history_and_v_shows_the_history_cells() -> None:
    client = FakeClient.with_valve_example()
    _updated_valve(client)
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        await pilot.pause()
        tab = app.query_one(ActivityTab)
        table = app.query_one("#activity-table", DataTable)
        events = client.history(app.query_one(RecordView).record["id"])  # type: ignore[index]
        assert table.row_count == len(events) == 4
        tab.action_revisions()  # v
        await pilot.pause()
        # Today's History cells, one per event, newest first; Revisions shows the same cells
        # in the Activity order (oldest first, activity_tab.py), so the rows are reversed.
        today = [history_cells(e, tab.labels, technical=False) for e in reversed(events)]
        shown = [tuple(str(c) for c in table.get_row_at(i)) for i in range(table.row_count)]
        assert shown == list(reversed(today))
        assert [str(c.label) for c in table.columns.values()] == list(history_columns(False))

    run_pilot(app, scenario, size=(120, 40))


def _plain_walk(actor: str, is_admin: bool) -> None:
    client = FakeClient.with_valve_example()
    _updated_valve(client)
    app = Host(client, actor=actor, is_admin=is_admin)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        await pilot.pause()
        text = screen_text(app)
        labels = load_labels(client, SCOPE, ("core.Record",))
        assert find_technical(text, labels) == []
        assert "Record." not in text and "user:" not in text

    run_pilot(app, scenario, size=(120, 40))


def test_the_plain_activity_walk_finds_no_technical_words_as_a_user_or_an_admin() -> None:
    _plain_walk("user:kim", is_admin=False)
    _plain_walk("user:admin", is_admin=True)


def test_n_and_I_are_not_bound_on_the_record_view() -> None:
    keys: set[str] = set()
    for binding in RecordView.BINDINGS:
        keys.update(binding.key.split(",") if isinstance(binding, Binding) else [binding[0]])
    assert "n" not in keys and "I" not in keys
    assert {"4", "9", "h"} <= keys


def test_technical_activity_columns_are_the_history_columns_and_from() -> None:
    assert TECHNICAL_COLUMNS == (*history_columns(True), "From")


def test_an_update_with_no_changes_reads_as_its_label_alone() -> None:
    labels = Labels()
    empty = ActivityRow(event=_event("Record.Updated", {}), kind="change")
    none = ActivityRow(event=_event("Record.Updated", None), kind="change")
    assert what_text(empty, labels, technical=False) == "Changed"
    assert what_text(none, labels, technical=False) == "Changed"
    assert what_text(empty, labels, technical=True) == "Record.Updated"
    changed = ActivityRow(event=_event("Record.Updated", {"title": "x"}), kind="change")
    assert what_text(changed, labels, technical=False) == "changed: Title"
