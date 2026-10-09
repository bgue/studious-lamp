"""TlApp layout, panel collapse, narrow mode and message routing (P0-I2-T12)."""

from __future__ import annotations

from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Tree
from tl_tui.app import TlApp
from tl_tui.messages import CloseRecord, StatusMessage, StepRecord
from tl_tui.widgets.context_panel import ContextPanel
from tl_tui.widgets.footer import DEFAULT_HINTS, TlFooter, hints_for
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.main_area import MainArea
from tl_tui.widgets.record_view import RecordView


def _app() -> TlApp:
    return TlApp(FakeClient.with_valve_example())


def test_wide_layout_shows_all_panels_and_focuses_the_grid() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert app.panel_visible("nav") and app.panel_visible("context")
        assert not app.narrow
        assert isinstance(app.focused, RecordGrid)
        assert "Records" in screen_text(app).splitlines()[0]

    run_pilot(app, scenario, size=(120, 40))


def test_f2_and_f3_collapse_and_restore_the_side_panels() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("f2")
        assert not app.panel_visible("nav") and app.panel_visible("context")
        await pilot.press("f3")
        assert not app.panel_visible("context")
        await pilot.press("f2", "f3")
        assert app.panel_visible("nav") and app.panel_visible("context")

    run_pilot(app, scenario, size=(120, 40))


def test_narrow_mode_hides_panels_and_opens_them_as_overlays() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert app.narrow
        assert not app.panel_visible("nav") and not app.panel_visible("context")
        await pilot.press("f2")
        assert app.panel_visible("nav") and not app.panel_visible("context")
        assert isinstance(app.focused, Tree)
        await pilot.press("f3")  # opening the other overlay closes this one
        assert app.panel_visible("context") and not app.panel_visible("nav")
        await pilot.press("escape")
        assert not app.panel_visible("context")
        assert isinstance(app.focused, RecordGrid)

    run_pilot(app, scenario, size=(80, 24))


def test_resizing_across_the_threshold_switches_modes() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert not app.narrow and app.panel_visible("nav")
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert app.narrow and not app.panel_visible("nav")
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert not app.narrow and app.panel_visible("nav") and app.panel_visible("context")

    run_pilot(app, scenario, size=(120, 40))


def test_cursor_moves_update_the_context_panel() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        panel = app.query_one(ContextPanel)
        assert panel.record is not None and panel.record["key"] == "FV-1001"
        await pilot.press("down")
        await pilot.pause()
        assert panel.record is not None and panel.record["key"] == "FV-1002"

    run_pilot(app, scenario, size=(120, 40))


def test_selection_count_and_status_reach_the_footer() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        footer = app.query_one(TlFooter)
        await pilot.press("space", "down", "space")
        await pilot.pause()
        assert footer.selection_count == 2
        app.query_one(RecordGrid).post_message(StatusMessage("it broke", "error"))
        await pilot.pause()
        assert footer.status == "it broke" and footer.severity == "error"

    run_pilot(app, scenario, size=(120, 40))


def test_footer_hints_follow_focus() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        footer = app.query_one(TlFooter)
        assert footer.hints == RecordGrid.KEY_HINTS
        await pilot.press("f6")  # grid -> context panel, which has no hints of its own
        await pilot.pause()
        assert footer.hints == DEFAULT_HINTS
        assert hints_for(None) == DEFAULT_HINTS

    run_pilot(app, scenario, size=(120, 40))


def test_f6_cycles_focus_through_visible_panels() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert isinstance(app.focused, RecordGrid)
        await pilot.press("f6")
        assert isinstance(app.focused, ContextPanel)
        await pilot.press("f6")
        assert isinstance(app.focused, Tree)
        await pilot.press("f6")
        assert isinstance(app.focused, RecordGrid)
        await pilot.press("shift+f6")
        assert isinstance(app.focused, Tree)

    run_pilot(app, scenario, size=(120, 40))


def test_open_close_and_step_records() -> None:
    app = _app()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        main = app.query_one(MainArea)
        await pilot.press("enter")
        await pilot.pause()
        assert main.showing_record
        view = app.query_one(RecordView)
        assert view.key == "FV-1001"
        assert "FV-1001" in screen_text(app).splitlines()[0]
        app.post_message(StepRecord(1))
        await pilot.pause()
        assert app.query_one(RecordView).key == "FV-1002"
        app.post_message(StepRecord(-1))
        app.post_message(StepRecord(-1))
        await pilot.pause()
        assert app.query_one(RecordView).key == "FV-1001"  # no record before the first
        app.post_message(CloseRecord())
        await pilot.pause()
        assert not main.showing_record
        assert "Records" in screen_text(app).splitlines()[0]
        assert isinstance(app.focused, RecordGrid)

    run_pilot(app, scenario, size=(120, 40))
