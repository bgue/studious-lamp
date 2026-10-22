"""The Files tab of the record view: there only when the record has files (P1-UX2-S4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from doc_support import pdf_bytes, settle
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import TabbedContent
from tl_tui.display import DisplayMode
from tl_tui.file_text import file_line
from tl_tui.widgets.file_panel import FilePanel
from tl_tui.widgets.record_screen import RecordScreen
from tl_tui.widgets.record_view import RecordView

PROJECT = "P123"
RFI = "RFI-0001-ID"


class Host(App[None]):
    def __init__(self, client: FakeClient, record_id: str) -> None:
        super().__init__()
        self.client = client
        self.record_id = record_id
        self.actor = "user:t"
        self.display_mode = DisplayMode()

    def on_mount(self) -> None:
        self.push_screen(RecordScreen(self.client, SCOPE, PROJECT, self.record_id, self.actor))


@pytest.fixture(autouse=True)
def text_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TL_IMAGES", "off")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def rfi_world() -> FakeClient:
    client = FakeClient()
    client.add_stored_record(RFI, "P123-RFI-0001", "core.Record", "Pile cap clash at AZ203")
    return client


def tabs(app: Host) -> TabbedContent:
    return app.screen.query_one("#rv-tabs", TabbedContent)


def test_no_files_tab_while_the_record_has_no_files() -> None:
    client = rfi_world()
    app = Host(client, RFI)

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        assert "Files" not in screen_text(app)
        await pilot.press("6")
        await settle(pilot)
        assert tabs(app).active == "tab-details"  # the key does nothing while the tab is hidden

    run_pilot(app, go, size=(140, 40))


def test_the_files_tab_lists_both_files_of_an_rfi_with_file_line() -> None:
    client = rfi_world()
    first = client.add_record_file(RFI, "clash-sketch.pdf", pdf_bytes(pages=2))
    second = client.add_record_file(RFI, "survey.csv", b"a,b\n1,2\n", content_type="text/csv")
    app = Host(client, RFI)

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        assert "Files" in screen_text(app)
        await pilot.press("6")
        await settle(pilot)
        assert tabs(app).active == "tab-files"
        panel = app.screen.query_one(FilePanel)
        pages = panel.pages.get(first.sha256)
        assert pages == 2  # learnt from the first page's render
        lines = panel.lines()
        assert lines == [
            "> " + file_line(first.filename, first.content_type, first.size, 2),
            "  " + file_line(second.filename, second.content_type, second.size),
        ]
        text = screen_text(app)
        assert "clash-sketch.pdf  PDF document" in text and "survey.csv  CSV file" in text

    run_pilot(app, go, size=(140, 40))


def test_v_on_the_files_tab_opens_the_chosen_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tl_tui.widgets import file_panel

    opened: list[Path] = []
    monkeypatch.setattr(
        file_panel, "open_in_viewer", lambda path, launcher=None: opened.append(path)
    )
    client = rfi_world()
    client.add_record_file(RFI, "one.csv", b"1", content_type="text/csv")
    client.add_record_file(RFI, "two.csv", b"2", content_type="text/csv")
    app = Host(client, RFI)

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await pilot.press("6")
        await settle(pilot)
        await pilot.press("down", "v")
        await settle(pilot)
        assert [p.name for p in opened] == ["two.csv"]
        assert "Opened two.csv." in app.screen.query_one(RecordView).query_one(FilePanel).note

    run_pilot(app, go, size=(140, 40))


def test_a_hidden_record_has_no_files_tab() -> None:
    client = rfi_world()
    client.add_record_file(RFI, "secret.pdf", pdf_bytes())
    client.hide_record(RFI)
    app = Host(client, RFI)

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        assert "secret.pdf" not in screen_text(app) and "Files" not in screen_text(app)

    run_pilot(app, go, size=(140, 40))


def test_the_other_tabs_keep_their_keys() -> None:
    client = rfi_world()
    client.add_record_file(RFI, "a.csv", b"1", content_type="text/csv")
    app = Host(client, RFI)

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        for key, tab in (("2", "tab-psets"), ("3", "tab-links"), ("4", "tab-history"),
                         ("5", "tab-trace"), ("6", "tab-files"), ("1", "tab-details")):  # fmt: skip
            await pilot.press(key)
            await pilot.pause()
            assert tabs(app).active == tab

    run_pilot(app, go, size=(140, 40))
