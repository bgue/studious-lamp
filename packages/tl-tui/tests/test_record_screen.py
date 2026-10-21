"""The full record screen a register opens from a row (P1-UX-S2).

A minimal register stand-in (a ModalScreen with a table) calls ``open_record`` on Enter, the way
the registers of the screen tickets will.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.pilot import Pilot
from textual.screen import ModalScreen
from textual.widgets import DataTable, TabbedContent
from tl_adapters.sqlite.uow import create_schema
from tl_core.confidentiality import LOWEST, use_viewer
from tl_core.files.service import FileService
from tl_mod_correspondence.confseed import seed_hidden_world
from tl_tui.display import DisplayMode, find_technical
from tl_tui.embedded import EmbeddedClient
from tl_tui.messages import OpenRecord
from tl_tui.widgets.psets_tab import PsetsTab
from tl_tui.widgets.record_screen import RecordScreen, open_record
from tl_tui.widgets.record_view import RecordView

PROJECT = "P123"
ACTOR = "user:t"


class Register(ModalScreen[None]):
    """A stand-in register: one row per record, Enter opens the record screen."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("enter", "open", show=False, priority=True)]

    def __init__(self, client: Any, rows: list[tuple[str, str]]) -> None:
        super().__init__()
        self.client = client
        self.rows = rows  # (record id, label)

    def compose(self) -> ComposeResult:
        yield DataTable(id="reg", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#reg", DataTable)
        table.add_column("Record")
        for record_id, label in self.rows:
            table.add_row(label, key=record_id)
        table.focus()

    def action_open(self) -> None:
        table = self.query_one("#reg", DataTable)
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        open_record(self, self.client, SCOPE, PROJECT, ACTOR, str(row_key.value))


class Host(App[None]):
    def __init__(self, client: Any, rows: list[tuple[str, str]]) -> None:
        super().__init__()
        self.client = client
        self.rows = rows
        self.actor = ACTOR
        self.display_mode = DisplayMode()
        self.reached: list[OpenRecord] = []  # OpenRecord messages that got as far as the app

    def on_mount(self) -> None:
        self.push_screen(Register(self.client, self.rows))

    def on_open_record(self, message: OpenRecord) -> None:
        self.reached.append(message)


def world() -> tuple[FakeClient, list[tuple[str, str]]]:
    """Two core records and the document ISO-1234 (a record of type documents.Document)."""
    client = FakeClient.with_valve_example()
    client.seed_documents(PROJECT)
    client._seed("ISO-1234", "Isometric, line 47-P-101", "Issued")  # noqa: SLF001
    doc = client.get_record(SCOPE, "ISO-1234")
    assert doc is not None
    client._records[doc["id"]]["type"] = "documents.Document"  # noqa: SLF001
    ids = [client.get_record(SCOPE, k) for k in ("FV-1001", "FV-1002", "ISO-1234")]
    return client, [(r["id"], r["key"]) for r in ids if r is not None]


def current(app: Host) -> RecordScreen:
    assert isinstance(app.screen, RecordScreen), type(app.screen)
    return app.screen


def test_open_record_shows_details_with_labels_not_ids() -> None:
    client, rows = world()
    app = Host(client, rows)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.screen.query_one("#reg", DataTable).move_cursor(row=2)
        await pilot.press("enter")
        await pilot.pause()
        screen = current(app)
        assert screen.view is not None
        text = screen_text(app)
        for label in ("Number", "Document type", "Current revision", "Conformance"):
            assert label in screen.view.details, label
        assert "Isometric, line 47-P-101" in text and "B (IFC)" in text
        assert "Properties" in text and "Psets" not in text
        assert find_technical(text) == []
        assert rows[2][0] not in text  # the record id never shows
        assert "Schema hash" not in screen.view.details and "Key" not in screen.view.details

    run_pilot(app, scenario, size=(140, 40))


def test_escape_dismisses_and_the_register_keeps_its_row() -> None:
    client, rows = world()
    app = Host(client, rows)
    done: list[Any] = []

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        register = app.screen
        assert isinstance(register, Register)
        register.query_one("#reg", DataTable).move_cursor(row=1)
        await pilot.press("enter")
        await pilot.pause()
        current(app)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is register
        assert register.query_one("#reg", DataTable).cursor_row == 1
        # the callback of push_screen runs: the screen closes with dismiss, not pop_screen
        app.push_screen(RecordScreen(client, SCOPE, PROJECT, rows[0][0], ACTOR), done.append)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert done == [None] and app.screen is register

    run_pilot(app, scenario, size=(140, 40))


def test_escape_closes_the_screen_of_a_missing_record_too() -> None:
    client, rows = world()
    app = Host(client, rows)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        register = app.screen
        app.push_screen(RecordScreen(client, SCOPE, PROJECT, "01NOSUCHRECORD", ACTOR))
        await pilot.pause()
        assert "No record" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is register

    run_pilot(app, scenario, size=(100, 30))


def _text_of_record_screen(client: Any, record_id: str, tmp: Path) -> str:
    app = Host(client, [])
    seen: list[str] = []

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.push_screen(RecordScreen(client, SCOPE, PROJECT, record_id, ACTOR))
        await pilot.pause()
        seen.append(screen_text(app))

    with use_viewer(LOWEST):
        run_pilot(app, scenario, size=(100, 30))
    return seen[0]


def test_a_hidden_record_reads_exactly_like_a_missing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_adapters.objectstore.fs import FsObjectStore

    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    db = tmp_path / "tl.db"
    create_schema(db)
    service = FileService(FsObjectStore(tmp_path / "objects", secret=b"k"), secret=b"s")
    hidden = seed_hidden_world(db, service, tmp_path)
    client = EmbeddedClient.for_sqlite(db)
    fake = "01J000000000000000000000"
    for kind in ("restricted", "privileged", "bogus"):
        record_id = hidden.ids[kind]
        as_hidden = _text_of_record_screen(client, record_id, tmp_path)
        as_missing = _text_of_record_screen(client, fake, tmp_path)
        assert "No record" in as_hidden
        assert as_hidden == as_missing, kind
        assert record_id not in as_hidden and hidden.numbers[kind] not in as_hidden
    readable = _text_of_record_screen(client, hidden.ids["open"], tmp_path)
    assert "No record" not in readable and hidden.numbers["open"] in readable


def test_following_a_link_inside_the_screen_retargets_it() -> None:
    client, rows = world()
    app = Host(client, rows)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = current(app)
        assert screen.view is not None and screen.view.key == "FV-1001"
        screen.view.post_message(OpenRecord(SCOPE, "FV-1002", follow=True))
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen) and app.screen is screen
        assert screen.view is not None and screen.view.key == "FV-1002"
        assert "Manual valve" in screen.view.details
        assert app.reached == []  # the app's own handler was not reached
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, Register)

    run_pilot(app, scenario, size=(140, 40))


def test_technical_rows_appear_only_in_technical_mode() -> None:
    client, rows = world()
    for technical in (False, True):
        app = Host(client, rows)
        app.display_mode.technical = technical
        seen: list[str] = []

        async def scenario(pilot: Pilot[Any], app: Host = app, seen: list[str] = seen) -> None:
            await pilot.pause()
            app.screen.query_one("#reg", DataTable).move_cursor(row=2)
            await pilot.press("enter")
            await pilot.pause()
            view = current(app).view
            assert view is not None
            seen.append(view.details)

        run_pilot(app, scenario, size=(140, 40))
        details = seen[0]
        for label in ("Key", "Version", "Scope", "Schema hash"):
            assert (label in details) is technical, (technical, label)
        assert "Number" in details  # the plain rows are there in both modes


def test_refresh_for_display_mode_rerenders_details_and_properties() -> None:
    client, rows = world()
    app = Host(client, rows)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = current(app)
        view = screen.view
        assert isinstance(view, RecordView)
        view.show_tab("psets")
        await pilot.pause()
        props = view.query_one(PsetsTab)
        assert "Schema hash" not in view.details and "Effective schema" not in props.text
        reads = client.calls.count("form_metadata")
        app.display_mode.technical = True
        screen.refresh_for_display_mode()
        await pilot.pause()
        assert "Schema hash" in view.details
        assert "Effective schema" in props.text
        assert view.query_one(TabbedContent).active == "tab-psets"
        assert client.calls.count("form_metadata") == reads  # Properties draws from what it has
        app.display_mode.technical = False
        screen.refresh_for_display_mode()
        await pilot.pause()
        assert "Schema hash" not in view.details

    run_pilot(app, scenario, size=(140, 40))
