"""Edit form modal and the `e` key of the record view (P0-I2-T16b). Provided; do not edit."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient, get_path
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from textual.widgets import Input
from tl_core.ledger import ConcurrencyError
from tl_schema.forms import FormMetadata
from tl_tui.app import TlApp
from tl_tui.messages import StatusMessage
from tl_tui.widgets.edit_form import EditForm, editor_id
from tl_tui.widgets.form_fields import FieldEditor
from tl_tui.widgets.record_view import RecordView

SIZE = editor_id("psets.valve_data.size_in")
WITNESS = editor_id("psets.valve_data.x.fat_witness_by")
TITLE = editor_id("title")


class Host(App[None]):
    def __init__(self, client: FakeClient, record: dict[str, Any], meta: FormMetadata) -> None:
        super().__init__()
        self.client = client
        self.record = record
        self.meta = meta
        self.results: list[bool | None] = []
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        form = EditForm(self.client, SCOPE, self.record, self.meta, actor="user:t")
        self.push_screen(form, self.results.append)

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)


def _setup(key: str = "FV-1001") -> tuple[FakeClient, dict[str, Any], FormMetadata]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, key)
    assert record is not None
    return client, record, client.form_metadata(SCOPE, "core.Record")


def _set(form: EditForm, editor: str, text: str) -> None:
    form.query_one(f"#{editor} Input", Input).value = text


def test_editor_id_replaces_dots() -> None:
    assert editor_id("psets.valve_data.x.fat_witness_by") == "f_psets_valve_data_x_fat_witness_by"
    assert editor_id("title") == "f_title"


def test_form_lists_writable_fields_with_current_values_and_skips_read_only_ones() -> None:
    client, record, meta = _setup()
    app = Host(client, record, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        text = screen_text(app)
        assert "Edit FV-1001" in text and "Details" in text
        assert form.headings == [
            "Details",
            "valve_data   co.acme.engineering 3.2.0",
            "prj.shutdown_tie_in   prj.P123 1.4.0",
        ]  # the enrichment group has only read-only fields, so it is left out
        paths = [e.meta.path for e in form.query(FieldEditor)]
        assert paths[:2] == ["title", "description"]
        assert "psets.valve_data.size_in" in paths
        assert "psets.enrich.ai_classifier.valve_type" not in paths
        assert form.query_one(f"#{SIZE} Input", Input).value == "6.0"
        assert (
            form.query_one(f"#{TITLE} Input", Input).value == "Control valve FCV on 6in discharge"
        )
        assert not any(e.changed for e in form.query(FieldEditor))

    run_pilot(app, scenario, size=(120, 50))


def test_ctrl_s_saves_core_and_pset_changes_and_dismisses_true() -> None:
    client, record, meta = _setup()
    app = Host(client, record, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        _set(form, TITLE, "Renamed valve")
        _set(form, SIZE, "8")
        _set(form, WITNESS, "@party:acme")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [True]
        saved = client.get_record_by_id(record["id"])
        assert saved is not None and saved["title"] == "Renamed valve"
        assert get_path(saved["psets"], "valve_data.size_in") == 8.0
        assert get_path(saved["psets"], "valve_data.x.fat_witness_by") == "@party:acme"
        layers = [(c.pset, c.layer, c.actor) for c in client.set_pset_commands]
        assert layers == [("valve_data", "standard", "user:t"), ("valve_data", "custom", "user:t")]
        assert client.set_pset_commands[0].values == {"size_in": 8.0}
        assert client.set_pset_commands[1].values == {"x.fat_witness_by": "@party:acme"}

    run_pilot(app, scenario, size=(120, 50))


def test_save_button_does_the_same_as_ctrl_s() -> None:
    client, record, meta = _setup()
    app = Host(client, record, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        _set(form, SIZE, "9")
        await pilot.pause()
        await pilot.click("#save")
        await pilot.pause()
        assert app.results == [True] and len(client.set_pset_commands) == 1

    run_pilot(app, scenario, size=(120, 50))


def test_invalid_input_blocks_the_save_and_shows_the_field_error() -> None:
    client, record, meta = _setup()
    app = Host(client, record, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        _set(form, SIZE, "abc")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and isinstance(app.screen, EditForm)
        text = screen_text(app)
        assert "Enter a number" in text and "Fix 1 field(s) first" in text
        assert client.set_pset_commands == [] and "update_record" not in client.calls

    run_pilot(app, scenario, size=(120, 50))


def test_saving_without_changes_says_so_and_stays_open() -> None:
    client, record, meta = _setup()
    app = Host(client, record, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [] and "No changes to save" in screen_text(app)

    run_pilot(app, scenario, size=(120, 50))


def test_escape_cancels_without_sending_anything() -> None:
    client, record, meta = _setup()
    app = Host(client, record, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        _set(form, SIZE, "7")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [False]
        assert client.set_pset_commands == []

    run_pilot(app, scenario, size=(120, 50))


def test_a_stale_record_stays_open_with_the_reason_and_applies_nothing() -> None:
    client, record, meta = _setup()
    stale = {**record, "version": record["version"] - 1}
    app = Host(client, stale, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        _set(form, SIZE, "8")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == []
        assert "Not saved: this record changed since you opened it" in screen_text(app)

    run_pilot(app, scenario, size=(120, 50))


def test_a_partial_save_dismisses_true_and_reports_what_was_applied() -> None:
    client, record, meta = _setup()
    original = client.set_pset_values
    calls = {"n": 0}

    def flaky(cmd: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConcurrencyError("x")
        return original(cmd)

    client.set_pset_values = flaky  # type: ignore[method-assign]
    app = Host(client, record, meta)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        _set(form, SIZE, "8")
        _set(form, WITNESS, "@party:acme")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.results == [True]
        texts = [(m.text, m.severity) for m in app.seen if isinstance(m, StatusMessage)]
        assert texts == [
            (
                "Saved valve_data/standard; failed valve_data/custom: "
                "this record changed since you opened it; reload and try again",
                "error",
            )
        ]

    run_pilot(app, scenario, size=(120, 50))


def test_e_in_the_record_view_opens_the_form_and_a_save_refreshes_the_view() -> None:
    client = FakeClient.with_valve_example()
    app = TlApp(client, actor="user:dev")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert "e edit" in RecordView.KEY_HINTS
        await pilot.press("e")
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        _set(form, TITLE, "Edited from the view")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, EditForm)
        assert "FV-1001 · Edited from the view" in screen_text(app)
        assert client.get_record(SCOPE, "FV-1001")["version"] == 4  # type: ignore[index]

    run_pilot(app, scenario, size=(120, 50))


def test_e_without_pset_services_warns() -> None:
    class NoServices(FakeClient):
        def form_metadata(self, scope: str, record_type: str):  # noqa: ANN202
            raise NotImplementedError

    client = NoServices.with_valve_example()
    app = TlApp(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert not isinstance(app.screen, EditForm)
        assert "Editing needs the pset services" in screen_text(app)

    run_pilot(app, scenario, size=(120, 40))
