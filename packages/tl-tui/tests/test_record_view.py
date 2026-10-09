"""Record view: header, Details and History tabs, keys (P0-I2-T14). Provided; do not edit."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from textual.widgets import DataTable, TabbedContent
from tl_core.services.commands import UpdateRecord
from tl_tui.app import TlApp
from tl_tui.messages import CloseRecord, RecordChanged, StatusMessage, StepRecord
from tl_tui.widgets.main_area import MainArea
from tl_tui.widgets.psets_tab import PsetsTab
from tl_tui.widgets.record_view import RecordView, details_text, event_summary


class Host(App[None]):
    def __init__(self, client: FakeClient, key: str = "FV-1001") -> None:
        super().__init__()
        self.client = client
        self.key = key
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield RecordView(self.client, SCOPE, self.key, id="record")

    def on_close_record(self, message: CloseRecord) -> None:
        self.seen.append(message)

    def on_step_record(self, message: StepRecord) -> None:
        self.seen.append(message)

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)


def test_details_text_lists_the_envelope_with_aligned_values() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    lines = details_text(record).splitlines()
    assert lines[0] == "Key          FV-1001"
    assert lines[1] == "Type         core.Record"
    assert lines[2] == "Title        Control valve FCV on 6in discharge"
    assert lines[3] == "Description  —"
    assert lines[4] == "Status       Design"
    assert lines[5] == "Scope        project:P123"
    assert lines[6] == "Version      3"
    assert lines[7].startswith("Created      2026-10-09 09:")
    assert lines[8].startswith("Updated      2026-10-09 09:")
    assert lines[9] == "Conformance  ✓ ok"
    assert lines[10] == "Schema       #a91f…3c"
    assert len(lines) == 11


def test_event_summary_per_event_type() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    events = client.history(record["id"])
    assert [event_summary(e) for e in events] == [
        "created: Control valve FCV on 6in discharge",
        "valve_data (standard): body_material, fail_action, seat_leakage, size_in",
        "valve_data (custom): x.fat_witness_by",
    ]
    update = client.update_record(
        UpdateRecord(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=record["version"],
            changes={"title": "New", "description": "d"},
        )
    )
    assert event_summary(update.events[0]) == "changed: description, title"


def test_view_shows_header_tabs_details_and_history_newest_first() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        view = app.query_one(RecordView)
        assert view.record is not None and view.record["key"] == "FV-1001"
        text = screen_text(app)
        assert "FV-1001 · Control valve FCV on 6in discharge" in text
        assert "Design · v3 · ✓ ok" in text
        for title in ("Details", "Psets", "History"):
            assert title in text
        assert "Description  —" in text
        tabs = app.query_one("#rv-tabs", TabbedContent)
        assert tabs.active == "tab-details"
        assert isinstance(app.query_one("#psets-tab"), PsetsTab)
        table = app.query_one("#rv-history", DataTable)
        assert table.row_count == 3
        assert [str(c) for c in table.get_row_at(0)][0:3] == [
            "3",
            "2026-10-09 09:03:00",
            "Pset.ValuesSet",
        ]
        assert str(table.get_row_at(2)[2]) == "Record.Created"

    run_pilot(app, scenario, size=(120, 40))


def test_h_opens_the_history_tab() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("h")
        await pilot.pause()
        assert app.query_one("#rv-tabs", TabbedContent).active == "tab-history"
        assert "created: Control valve FCV on 6in discharge" in screen_text(app)

    run_pilot(app, scenario, size=(120, 40))


def test_escape_and_brackets_post_close_and_step_messages() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("]", "[", "escape")
        await pilot.pause()
        kinds = [type(m).__name__ for m in app.seen]
        assert kinds == ["StepRecord", "StepRecord", "CloseRecord"]
        deltas = [m.delta for m in app.seen if isinstance(m, StepRecord)]
        assert deltas == [1, -1]

    run_pilot(app, scenario, size=(120, 40))


def test_unknown_key_shows_not_found_and_an_error_status() -> None:
    app = Host(FakeClient.with_valve_example(), key="NOPE-1")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert app.query_one(RecordView).record is None
        assert "NOPE-1 · not found" in screen_text(app)
        statuses = [m for m in app.seen if isinstance(m, StatusMessage)]
        assert [(s.text, s.severity) for s in statuses] == [("No record NOPE-1", "error")]

    run_pilot(app, scenario, size=(120, 40))


def test_record_changed_reloads_the_view_and_literal_brackets_survive() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        record = client.get_record(SCOPE, "FV-1001")
        assert record is not None
        client.update_record(
            UpdateRecord(
                actor="user:t",
                source="tui",
                scope=SCOPE,
                stream_id=record["id"],
                expected_version=record["version"],
                changes={"title": "[bold]Renamed[/bold]"},
            )
        )
        app.query_one(RecordView).post_message(RecordChanged("some-other-id"))
        await pilot.pause()
        assert "Renamed" not in screen_text(app)  # a different record: ignored
        app.query_one(RecordView).post_message(RecordChanged(record["id"]))
        await pilot.pause()
        text = screen_text(app)
        assert "FV-1001 · [bold]Renamed[/bold]" in text
        assert "v4" in text
        assert app.query_one("#rv-history", DataTable).row_count == 4

    run_pilot(app, scenario, size=(120, 40))


def test_the_app_opens_steps_and_closes_the_view() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        main = app.query_one(MainArea)
        await pilot.press("enter")
        await pilot.pause()
        assert main.showing_record
        assert app.query_one(RecordView).key == "FV-1001"
        await pilot.press("]")
        await pilot.pause()
        assert app.query_one(RecordView).key == "FV-1002"
        assert "FV-1002 · Manual valve MV on 4in vent" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert not main.showing_record
        assert "Key" in screen_text(app).splitlines()[1]

    run_pilot(app, scenario, size=(120, 40))
