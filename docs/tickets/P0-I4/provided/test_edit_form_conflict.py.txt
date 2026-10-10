"""Edit form conflict banner (P0-I4-T63). Provided; do not edit."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input, Static
from tl_core.services.commands import UpdateRecord
from tl_schema.forms import FormMetadata
from tl_tui.widgets.edit_form import EditForm, editor_id

TITLE = editor_id("title")


class Host(App[None]):
    def __init__(self, client: FakeClient, record: dict[str, Any], meta: FormMetadata) -> None:
        super().__init__()
        self.client = client
        self.record = record
        self.meta = meta
        self.results: list[bool | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        form = EditForm(self.client, SCOPE, self.record, self.meta, actor="user:t")
        self.push_screen(form, self.results.append)


def setup() -> tuple[FakeClient, dict[str, Any], Host]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    return client, record, Host(client, record, client.form_metadata(SCOPE, "core.Record"))


def type_title(form: EditForm, text: str) -> None:
    form.query_one(f"#{TITLE} Input", Input).value = text


def bob_changes_the_title(client: FakeClient, record: dict[str, Any]) -> int:
    result = client.update_record(
        UpdateRecord(
            actor="user:bob",
            source="test",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=record["version"],
            changes={"title": "Bob was here"},
        )
    )
    return result.version


def test_the_banner_is_hidden_and_saving_works_until_a_conflict_is_marked() -> None:
    client, record, app = setup()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        assert not form.conflict and not form.query_one("#form-conflict", Static).display
        assert form.opened_version == record["version"]
        type_title(form, "Mine")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [True]

    run_pilot(app, scenario)


def test_mark_conflict_names_the_writer_and_both_versions_and_blocks_saving() -> None:
    client, record, app = setup()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        type_title(form, "Mine")
        version = bob_changes_the_title(client, record)
        form.mark_conflict("user:bob", version)
        await pilot.pause()
        assert form.conflict and form.query_one("#form-conflict", Static).display
        text = screen_text(app)
        assert "✗ Conflict: user:bob changed this record" in text
        assert f"now v{version}, you opened v{record['version']}" in text
        client.calls.clear()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "edit_record" not in client.calls  # nothing was sent
        assert app.results == [] and isinstance(app.screen, EditForm)
        assert "Not saved: the record changed" in screen_text(app)
        assert form.query_one(f"#{TITLE} Input", Input).value == "Mine"  # what was typed is kept
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [False]

    run_pilot(app, scenario, size=(120, 50))


def test_mark_conflict_without_details_still_says_what_happened() -> None:
    client, record, app = setup()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        form.mark_conflict()
        await pilot.pause()
        text = screen_text(app)
        assert "✗ Conflict: this record changed" in text and "now v" not in text

    run_pilot(app, scenario, size=(120, 50))


def test_a_save_refused_by_the_ledger_shows_the_banner_and_keeps_the_values() -> None:
    client, record, app = setup()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        type_title(form, "Mine")
        bob_changes_the_title(client, record)  # the form does not hear about it
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert form.conflict
        text = screen_text(app)
        assert "Not saved: this record changed since you opened it" in text
        assert "✗ Conflict: this record changed" in text
        assert app.results == [] and form.query_one(f"#{TITLE} Input", Input).value == "Mine"

    run_pilot(app, scenario, size=(120, 50))


def test_the_banner_text_is_not_read_as_markup() -> None:
    client, record, app = setup()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        form.mark_conflict("user:[bold]x[/]", 9)
        await pilot.pause()
        assert "user:[bold]x[/] changed this record" in screen_text(app)

    run_pilot(app, scenario, size=(120, 50))
