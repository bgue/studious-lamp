"""Column chooser modal and the grid's `c` and `y` actions (P0-I2-T13b). Provided; do not edit."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_tui.messages import StatusMessage
from tl_tui.widgets.column_chooser import ColumnChooser
from tl_tui.widgets.grid import CORE_COLUMNS, DEFAULT_COLUMNS, RecordGrid

VISIBLE = ["key", "title"]


class ChooserHost(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[list[str] | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        self.push_screen(ColumnChooser(list(CORE_COLUMNS), VISIBLE), self.results.append)


def test_chooser_returns_the_checked_columns_in_available_order() -> None:
    app = ChooserHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "Choose columns" in text and "Conformance" in text and "Created" in text
        await pilot.press("down", "down", "space", "ctrl+s")  # also check "Status"
        await pilot.pause()
        assert app.results == [["key", "title", "status"]]

    run_pilot(app, scenario, size=(80, 30))


def test_chooser_unchecking_removes_a_column() -> None:
    app = ChooserHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("space", "ctrl+s")  # uncheck "Key"
        await pilot.pause()
        assert app.results == [["title"]]

    run_pilot(app, scenario, size=(80, 30))


def test_chooser_refuses_an_empty_selection_and_cancel_returns_none() -> None:
    app = ChooserHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("space", "down", "space", "ctrl+s")  # uncheck both
        await pilot.pause()
        assert app.results == []
        assert isinstance(app.screen, ColumnChooser)
        assert "Choose at least one column" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [None]

    run_pilot(app, scenario, size=(80, 30))


class GridHost(App[None]):
    def __init__(self, client: FakeClient | None = None) -> None:
        super().__init__()
        self.client = client or FakeClient.with_valve_example()
        self.statuses: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        yield RecordGrid(self.client, SCOPE, id="grid")

    def on_status_message(self, message: StatusMessage) -> None:
        self.statuses.append((message.text, message.severity))


def test_grid_c_opens_the_chooser_with_pset_columns_and_applies_the_result() -> None:
    app = GridHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one(RecordGrid)
        assert [c.key for c in grid.columns] == [c.key for c in DEFAULT_COLUMNS]
        assert "c columns" in RecordGrid.KEY_HINTS and "y copy" in RecordGrid.KEY_HINTS
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ColumnChooser)
        assert "valve_data.size_in" in screen_text(app)
        # CORE_COLUMNS has 8 entries; the first pset property (size_in) is the 9th item.
        await pilot.press(*["down"] * len(CORE_COLUMNS), "space", "ctrl+s")
        await pilot.pause()
        assert not isinstance(app.screen, ColumnChooser)
        keys = [c.key for c in grid.columns]
        assert keys == [*[c.key for c in DEFAULT_COLUMNS], "psets.valve_data.size_in"]
        assert "valve_data.si" in screen_text(app)  # the header is cut to the column width

    run_pilot(app, scenario, size=(120, 40))


def test_grid_c_cancel_keeps_the_columns() -> None:
    app = GridHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one(RecordGrid)
        await pilot.press("c", "escape")
        await pilot.pause()
        assert [c.key for c in grid.columns] == [c.key for c in DEFAULT_COLUMNS]

    run_pilot(app, scenario, size=(120, 40))


def test_grid_y_copies_the_selection_as_tsv_to_the_clipboard() -> None:
    app = GridHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one(RecordGrid)
        await pilot.press("space", "down", "space", "y")
        await pilot.pause()
        assert app.clipboard == grid.copy_text()
        assert app.clipboard.splitlines()[1].startswith("FV-1001\t")
        assert app.statuses[-1] == ("Copied 2 rows as TSV", "info")

    run_pilot(app, scenario, size=(120, 40))


def test_grid_y_without_a_selection_copies_the_cursor_row() -> None:
    app = GridHost()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("down", "y")
        await pilot.pause()
        lines = app.clipboard.splitlines()
        assert len(lines) == 2 and lines[1].startswith("FV-1002\t")
        assert app.statuses[-1] == ("Copied 1 row as TSV", "info")

    run_pilot(app, scenario, size=(120, 40))


def test_grid_y_on_an_empty_grid_warns_and_copies_nothing() -> None:
    app = GridHost(FakeClient())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert app.clipboard == ""
        assert app.statuses[-1] == ("Nothing to copy", "warning")

    run_pilot(app, scenario, size=(120, 40))
