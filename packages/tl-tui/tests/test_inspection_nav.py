"""The inspections palette entry (P2-INSP-T10): the palette lists `inspections`; choosing it shows
the log."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from fakes_insp import seed_inspections
from helpers import run_pilot, settle
from textual.pilot import Pilot
from textual.widgets import Input, OptionList
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.widgets.inspection_log import InspectionLogScreen


def make_app() -> TlApp:
    client = FakeClient()
    seed_inspections(client)
    return TlApp(client, scope=SCOPE, actor="user:kim")


def label_of(cid: str) -> str:
    return next(c.label for c in APP_COMMANDS if c.id == cid)


def top_row(app: TlApp) -> Any:
    palette: Any = app.screen
    index = palette.query_one("#palette-list", OptionList).highlighted
    rows = palette.rows
    return rows[index].choice if index is not None and 0 <= index < len(rows) else None


def test_the_palette_lists_inspections_and_its_action_exists() -> None:
    rows = {c.id: c for c in APP_COMMANDS}
    assert "inspections" in rows
    assert rows["inspections"].keys == ""
    assert rows["inspections"].action == "inspections"
    assert callable(getattr(TlApp, "action_inspections", None))


def test_choosing_inspections_in_the_palette_shows_the_log() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        base = len(app.screen_stack)
        app.action_palette()
        await settle(pilot)
        app.screen.query_one("#palette-input", Input).value = label_of("inspections")
        await settle(pilot)
        seen["choice"] = top_row(app)
        await pilot.press("enter")
        await settle(pilot)
        seen["screen"] = app.screen
        await pilot.press("escape")
        await settle(pilot)
        seen["back"] = len(app.screen_stack) == base

    app = make_app()

    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=(170, 44))
    choice = seen["choice"]
    assert choice is not None and choice.command_id == "inspections"
    assert isinstance(seen["screen"], InspectionLogScreen)
    assert seen["back"]
