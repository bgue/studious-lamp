"""about:config in plain mode names the layer in words; technical mode keeps the raw id.

P1-UX-T09e. The host is a TlApp on the fake client, so the display mode is the app's own
``display_mode``.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input
from tl_tui.app import TlApp
from tl_tui.display import find_technical
from tl_tui.widgets.setting_form import SettingForm
from tl_tui.widgets.settings_screen import SettingsScreen

KEY = "feed.reactions.enabled"


async def filter_to(pilot: Pilot[Any], app: TlApp, text: str) -> None:
    screen = app.screen
    assert isinstance(screen, SettingsScreen)
    await pilot.press("slash")
    screen.query_one("#settings-filter", Input).value = text
    await pilot.pause()
    await pilot.press("enter")  # back to the table
    await pilot.pause()


def test_the_panel_and_the_form_name_the_layer_in_words() -> None:
    app = TlApp(FakeClient(), scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("f9")
        await pilot.pause()
        await filter_to(pilot, app, KEY)
        panel = screen_text(app)
        assert "change goes to Project P123" in panel
        assert "project:P123" not in panel
        assert find_technical(panel) == []
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, SettingForm)
        form = screen_text(app)
        assert "at Project P123" in form
        assert "project:P123" not in form
        assert find_technical(form) == []

    run_pilot(app, go)


def test_technical_mode_shows_the_raw_layer_in_both_places() -> None:
    app = TlApp(FakeClient(), scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("f9")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        app.display_mode.technical = True
        screen.refresh_for_display_mode()
        await pilot.pause()
        await filter_to(pilot, app, KEY)
        assert "change goes to project:P123" in screen_text(app)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, SettingForm)
        assert "at project:P123" in screen_text(app)

    run_pilot(app, go)


def test_layer_kind_words_are_capitalised_in_plain_and_raw_in_technical() -> None:
    client = FakeClient()
    client.seed_setting(KEY, "project:P123", False)  # origin project, set here
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("f9")
        await pilot.pause()
        await filter_to(pilot, app, KEY)
        assert "origin Project ●" in screen_text(app)
        assert "origin project" not in screen_text(app)
        app.display_mode.technical = True
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        screen.refresh_for_display_mode()
        await pilot.pause()
        assert "origin project ●" in screen_text(app)

    run_pilot(app, go)
