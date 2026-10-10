"""The filter bar wired into the app: `/`, Enter, the count, the caret, Esc (P0-I4).

Over the FakeClient (real parser). The bar itself is tested in `test_filter_bar.py`, the grid side
in `test_grid_filter.py`; this proves they are connected and that nothing else moves.
"""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input
from tl_tui.app import TlApp
from tl_tui.widgets.filter_bar import INPUT_OFFSET, FilterBar
from tl_tui.widgets.grid import RecordGrid


def build() -> TlApp:
    return TlApp(FakeClient.with_valve_example())


def keys_of(app: TlApp) -> list[str]:
    return [r["key"] for r in app.query_one("#grid", RecordGrid).rows]


def test_the_bar_is_hidden_until_slash_and_slash_focuses_its_input() -> None:
    app = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        bar = app.query_one("#filter", FilterBar)
        assert not bar.display
        await pilot.press("slash")
        await pilot.pause()
        assert bar.display
        assert isinstance(app.focused, Input) and app.focused.id == "filter-input"

    run_pilot(app, scenario)


def test_enter_filters_the_grid_shows_the_count_and_returns_to_the_grid() -> None:
    app = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("slash", *"status:Design", "enter")
        await pilot.pause()
        assert keys_of(app) == ["FV-1001", "FV-1002"]
        assert "2 matches" in screen_text(app)
        assert isinstance(app.focused, RecordGrid)
        assert app.query_one("#filter", FilterBar).display  # stays while a filter is in force

    run_pilot(app, scenario)


def test_a_syntax_error_shows_its_position_with_a_caret_and_keeps_the_rows() -> None:
    app = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("slash", *"status:Design )", "enter")
        await pilot.pause()
        assert keys_of(app) == ["FV-1001", "FV-1002", "FV-1003"]
        lines = screen_text(app).splitlines()
        assert any("✗" in line and "(position 14)" in line for line in lines)
        caret = next(line for line in lines if line.strip() == "^")
        assert caret.index("^") == INPUT_OFFSET + 14
        assert isinstance(app.focused, Input)  # the user fixes the text in place

    run_pilot(app, scenario)


def test_a_blank_filter_clears_and_hides_the_bar_and_escape_leaves_it() -> None:
    app = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        bar = app.query_one("#filter", FilterBar)
        await pilot.press("slash", *"status:Installed", "enter")
        await pilot.pause()
        assert keys_of(app) == ["FV-1003"]
        await pilot.press("slash")
        bar.set_text("")
        await pilot.press("enter")
        await pilot.pause()
        assert keys_of(app) == ["FV-1001", "FV-1002", "FV-1003"] and not bar.display
        await pilot.press("slash", "escape")  # nothing in force: Esc hides the bar again
        await pilot.pause()
        assert not bar.display and isinstance(app.focused, RecordGrid)

    run_pilot(app, scenario)


def test_slash_from_an_open_record_returns_to_the_grid_first() -> None:
    app = build()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app._record_view() is not None  # pyright: ignore[reportPrivateUsage]
        await pilot.press("slash")
        await pilot.pause()
        assert app._record_view() is None  # pyright: ignore[reportPrivateUsage]
        assert app.query_one("#filter", FilterBar).display

    run_pilot(app, scenario)
