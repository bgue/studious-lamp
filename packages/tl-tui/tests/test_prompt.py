"""PromptScreen (P0-I3)."""

from __future__ import annotations

from typing import Any

from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Input
from tl_tui.widgets.prompt import PromptScreen


class Host(App[None]):
    def __init__(self, **kw: Any) -> None:
        super().__init__()
        self.kw = kw
        self.results: list[str | None] = []

    def compose(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        self.push_screen(PromptScreen("Retract link", "Reason", **self.kw), self.results.append)


def test_enter_returns_the_stripped_text() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "Retract link" in screen_text(app) and "Reason" in screen_text(app)
        app.screen.query_one("#prompt-input", Input).value = "  entered in error "
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == ["entered in error"]

    run_pilot(app, scenario, size=(100, 30))


def test_an_empty_answer_stays_open_when_required() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == []
        assert "Required" in screen_text(app)

    run_pilot(app, scenario, size=(100, 30))


def test_an_empty_answer_is_fine_when_not_required_and_initial_text_is_shown() -> None:
    app = Host(required=False, initial="draft")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert app.screen.query_one("#prompt-input", Input).value == "draft"
        app.screen.query_one("#prompt-input", Input).value = ""
        await pilot.press("enter")
        await pilot.pause()
        assert app.results == [""]

    run_pilot(app, scenario, size=(100, 30))


def test_escape_cancels() -> None:
    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.results == [None]

    run_pilot(app, scenario, size=(100, 30))
