"""EditForm refuses fields users cannot write instead of crashing."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input
from tl_tui.widgets.edit_form import EditForm, editor_id


def test_a_writable_looking_enrichment_field_is_reported_not_raised() -> None:
    client = FakeClient.with_valve_example()
    meta = client.form_metadata(SCOPE, "core.Record").model_copy(deep=True)
    meta.psets[2].fields[0].readonly = False  # a faulty schema: enrichment field left writable
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None

    class Host(App[None]):
        def compose(self) -> ComposeResult:
            return iter(())

        def on_mount(self) -> None:
            self.push_screen(EditForm(client, SCOPE, record, meta))

    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        path = "psets.enrich.ai_classifier.valve_type"
        form.query_one(f"#{editor_id(path)} Input", Input).value = "ball"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, EditForm)
        assert "Not saved: " in screen_text(app) and "read-only" in screen_text(app)
        assert client.set_pset_commands == []

    run_pilot(app, scenario, size=(120, 50))
