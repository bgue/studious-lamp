"""New-record modal and the `n` key of the app (P0-I2-T16c). Provided; do not edit."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input
from tl_tui.app import TlApp
from tl_tui.widgets.new_record_form import NewRecordForm
from tl_tui.widgets.record_view import RecordView


class Host(App[None]):
    def __init__(self, client: FakeClient) -> None:
        super().__init__()
        self.client = client
        self.results: list[str | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        form = NewRecordForm(self.client, SCOPE, actor="user:t")
        self.push_screen(form, self.results.append)


def _fill(form: NewRecordForm, key: str, title: str, description: str = "") -> None:
    form.query_one("#new_key Input", Input).value = key
    form.query_one("#new_title Input", Input).value = title
    form.query_one("#new_description Input", Input).value = description


def test_form_shows_three_fields_with_required_markers() -> None:
    app = Host(FakeClient())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "New record" in text
        assert "Key ●" in text and "Title ●" in text and "Description" in text

    run_pilot(app, scenario, size=(100, 30))


def test_ctrl_s_creates_the_record_and_dismisses_with_its_key() -> None:
    client = FakeClient()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, NewRecordForm)
        _fill(form, "FV-3001", "New valve", "A description")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == ["FV-3001"]
        created = client.get_record(SCOPE, "FV-3001")
        assert created is not None
        assert created["title"] == "New valve" and created["description"] == "A description"
        assert created["type"] == "core.Record"
        history = client.history(created["id"])
        assert history[0].actor == "user:t" and history[0].source == "tui"

    run_pilot(app, scenario, size=(100, 30))


def test_an_empty_description_is_stored_as_none() -> None:
    client = FakeClient()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, NewRecordForm)
        _fill(form, "FV-3002", "No description")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        created = client.get_record(SCOPE, "FV-3002")
        assert created is not None and created["description"] is None

    run_pilot(app, scenario, size=(100, 30))


def test_missing_key_or_title_is_refused_with_inline_errors() -> None:
    client = FakeClient()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, NewRecordForm)
        _fill(form, "", "Only a title")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and client.list_records(SCOPE) == []
        text = screen_text(app)
        assert "Required" in text and "Fill in the required fields" in text

    run_pilot(app, scenario, size=(100, 30))


def test_a_duplicate_key_stays_open_and_explains() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, NewRecordForm)
        _fill(form, "FV-1001", "Again")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and isinstance(app.screen, NewRecordForm)
        assert "Not created: key 'FV-1001' is already used" in screen_text(app)

    run_pilot(app, scenario, size=(100, 30))


def test_escape_cancels() -> None:
    client = FakeClient()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [None] and client.list_records(SCOPE) == []

    run_pilot(app, scenario, size=(100, 30))


def test_n_in_the_app_creates_a_record_and_opens_it() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client, actor="user:dev")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        form = app.screen
        assert isinstance(form, NewRecordForm)
        _fill(form, "FV-3003", "Fresh valve")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, NewRecordForm)
        assert app.query_one(RecordView).key == "FV-3003"
        assert "FV-3003 · Fresh valve" in screen_text(app)
        assert "Created FV-3003" in screen_text(app)

    run_pilot(app, scenario, size=(120, 40))


def test_typing_n_into_a_field_does_not_open_another_form() -> None:
    app = TlApp(FakeClient.with_valve_example())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        form = app.screen
        assert isinstance(form, NewRecordForm)
        form.query_one("#new_key Input", Input).focus()
        await pilot.press("n", "e", "w")
        await pilot.pause()
        assert app.screen is form
        assert form.query_one("#new_key Input", Input).value == "new"

    run_pilot(app, scenario, size=(120, 40))
