"""Record view and context panel in plain words; technical mode shows what plain hides (P1-UX-T08).

Pilot tests on ``FakeClient`` (as ``test_record_view.py``), plus pure checks of ``context_text``.
The History tab is checked with the leak finder (``find_technical``) on the rendered screen.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import DataTable, TabbedContent
from tl_core.services.commands import UpdateRecord
from tl_tui.app import TlApp
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.labels_load import load_labels
from tl_tui.widgets.context_panel import ContextPanel, context_text
from tl_tui.widgets.record_view import RecordView

RECORD: dict[str, Any] = {
    "id": "R1",
    "key": "FV-1001",
    "type": "core.Record",
    "title": "T",
    "status": "Design",
    "version": 3,
    "conformance": "warning",
    "effective_schema_hash": "a91f" + "0" * 56 + "3c",
    "psets": {
        "valve_data": {"size_in": 6.0, "x": {"fat_witness_by": "@p"}},
        "prj": {"shutdown_tie_in": {"window": "SD-1"}},
    },
}


class Host(App[None]):
    def __init__(self, client: FakeClient, key: str = "FV-1001") -> None:
        super().__init__()
        self.client = client
        self.key = key
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        yield RecordView(self.client, SCOPE, self.key, id="record")


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


def test_plain_header_has_no_version_and_technical_has_it() -> None:
    app = Host(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        view = app.query_one(RecordView)
        text = screen_text(app)
        assert "Design · ✓ ok" in text
        assert "v3" not in text
        app.display_mode.technical = True
        view.refresh_for_display_mode()
        await pilot.pause()
        assert "Design · v3 · ✓ ok" in screen_text(app)
        app.display_mode.technical = False
        view.refresh_for_display_mode()
        await pilot.pause()
        assert "v3" not in screen_text(app)

    run_pilot(app, scenario, size=(120, 40))


def test_plain_history_has_words_names_and_no_event_type_or_actor_id() -> None:
    client = FakeClient.with_valve_example()
    _updated_valve(client)
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.query_one("#rv-tabs", TabbedContent).active = "tab-history"
        await pilot.pause()
        await pilot.pause()
        table = app.query_one("#rv-history", DataTable)
        assert [str(c.label) for c in table.columns.values()] == ["When", "What", "By", "Summary"]
        first = [str(c) for c in table.get_row_at(0)]
        assert first[1:] == ["Changed", "dev", "changed: Description, Title"]
        assert table.row_count == 4
        assert str(table.get_row_at(table.row_count - 1)[1]) == "Created"
        text = screen_text(app)
        assert "Record." not in text and "user:" not in text and "svc:" not in text
        assert find_technical(text, load_labels(client, SCOPE, ("core.Record",))) == []

    run_pilot(app, scenario, size=(120, 40))


def test_technical_history_keeps_the_event_type_and_actor_and_toggles_back() -> None:
    client = FakeClient.with_valve_example()
    _updated_valve(client)
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        view = app.query_one(RecordView)
        app.display_mode.technical = True
        view.refresh_for_display_mode()
        await pilot.pause()
        table = app.query_one("#rv-history", DataTable)
        assert [str(c.label) for c in table.columns.values()] == [
            "#",
            "When",
            "Event",
            "Actor",
            "Summary",
        ]
        assert [str(c) for c in table.get_row_at(0)][2:4] == ["Record.Updated", "user:dev"]
        app.display_mode.technical = False
        view.refresh_for_display_mode()
        await pilot.pause()
        table = app.query_one("#rv-history", DataTable)
        assert [str(c.label) for c in table.columns.values()] == ["When", "What", "By", "Summary"]
        assert str(table.get_row_at(0)[1]) == "Changed"

    run_pilot(app, scenario, size=(120, 40))


def test_context_text_plain_and_technical() -> None:
    labels = Labels(type_titles={"core.Record": "Record"})
    plain = context_text(RECORD, labels, technical=False)
    assert plain == "\n".join(
        [
            "FV-1001",
            "T",
            "Design · Record",
            "! warning",
            "── Properties ──",
            "Window  SD-1",
            "Size in  6",
            "Fat witness by  @p",
        ]
    )
    assert "v3" not in plain and "#a91f" not in plain and "Schema" not in plain
    technical = context_text(RECORD)
    assert technical == "\n".join(
        [
            "FV-1001  v3",
            "T",
            "Design · core.Record",
            "! warning",
            "── Psets ──",
            "prj.shutdown_tie_in.window  SD-1",
            "valve_data.size_in  6",
            "valve_data.x.fat_witness_by  @p",
            "── Schema ──",
            "#a91f…3c",
        ]
    )
    assert context_text(RECORD, labels, technical=True) == technical


def test_context_panel_refreshes_on_the_mode_switch() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        panel = app.query_one(ContextPanel)
        record = client.get_record(SCOPE, "FV-1001")
        assert record is not None
        panel.show_record(record)
        await pilot.pause()
        assert "v3" not in panel.text and "── Schema ──" not in panel.text
        assert "── Properties ──" in panel.text
        app.display_mode.technical = True
        panel.refresh_for_display_mode()
        await pilot.pause()
        assert "FV-1001  v3" in panel.text and "── Schema ──" in panel.text
        assert "FV-1001  v3" in screen_text(app)
        app.display_mode.technical = False
        panel.refresh_for_display_mode()
        await pilot.pause()
        assert "v3" not in panel.text

    run_pilot(app, scenario, size=(120, 40))
