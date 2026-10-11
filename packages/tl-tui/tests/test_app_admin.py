"""F10 is for admins only (P1-I0-S4). The test that it opens the screen is added with T09."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.commands import command_by_id
from tl_tui.widgets.admin_screen import AdminScreen
from tl_tui.widgets.settings_screen import SettingsScreen


def app_for(*, is_admin: bool) -> TlApp:
    client = FakeClient()
    client.seed_account("boss", roles=["admin", "user"])
    return TlApp(client, scope=SCOPE, actor="user:boss", is_admin=is_admin)


def test_f10_tells_anyone_else_why_nothing_opened() -> None:
    app = app_for(is_admin=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.press("f10")
        await pilot.pause()
        assert not isinstance(app.screen, AdminScreen)
        assert "Accounts need the admin role" in screen_text(app)

    run_pilot(app, scenario)


def test_f10_does_nothing_over_another_modal() -> None:
    app = app_for(is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.press("f9")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        await pilot.press("f10")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

    run_pilot(app, scenario)


def test_the_palette_has_the_command_and_the_app_a_binding_for_it() -> None:
    command = command_by_id("admin")
    assert command is not None and command.keys == "F10" and command.action == "admin"
    assert any(b.key == "f10" and b.action == "admin" for b in TlApp.BINDINGS)  # type: ignore[union-attr]
