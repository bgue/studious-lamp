"""Ctrl+D switches technical details on and off for an admin; a plain user is refused (P1-UX-T10).

Pilot tests on the fake client. The toggle is an app-level binding: it works under a modal, opens
none, and calls ``refresh_for_display_mode`` on every open screen and widget that has one.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import ComposeResult
from textual.pilot import Pilot
from textual.screen import ModalScreen
from textual.widget import Widget
from tl_tui.app import TlApp
from tl_tui.display import REFUSAL
from tl_tui.widgets.footer import TlFooter
from tl_tui.widgets.help_screen import HelpScreen


def app_for(*, is_admin: bool) -> TlApp:
    return TlApp(FakeClient(), scope=SCOPE, actor="user:boss", is_admin=is_admin)


class Probe(Widget):
    """A child widget that counts its refresh calls; it can be set to raise instead."""

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail
        self.calls = 0

    def refresh_for_display_mode(self) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("a broken hook")


class ProbeScreen(ModalScreen[None]):
    """A modal with a hook of its own and two child widgets; the first child's hook raises."""

    def __init__(self) -> None:
        super().__init__()
        self.own_calls = 0
        self.failing = Probe(fail=True)
        self.after = Probe()

    def compose(self) -> ComposeResult:
        yield self.failing
        yield self.after

    def refresh_for_display_mode(self) -> None:
        self.own_calls += 1


def test_admin_ctrl_d_switches_technical_mode_on_and_off() -> None:
    app = app_for(is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert app.display_mode.technical is False
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.display_mode.technical is True
        assert "Technical details on" in screen_text(app)
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.display_mode.technical is False
        assert "Technical details off" in screen_text(app)

    run_pilot(app, scenario)


def test_plain_user_gets_the_refusal_and_mode_stays_off() -> None:
    app = app_for(is_admin=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.display_mode.technical is False
        assert REFUSAL in screen_text(app)
        assert "Technical details on" not in screen_text(app)

    run_pilot(app, scenario)


def test_the_key_works_with_a_modal_open_and_opens_none() -> None:
    app = app_for(is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        assert len(app.screen_stack) == 2
        assert app.display_mode.technical is True
        assert app.query_one("#footer", TlFooter).status == "Technical details on"

    run_pilot(app, scenario)


def test_toggle_calls_refresh_hooks_on_open_screens() -> None:
    app = app_for(is_admin=True)
    probe = ProbeScreen()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.push_screen(probe)
        await pilot.pause()
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert probe.own_calls == 1
        assert probe.failing.calls == 1  # its hook raised ...
        assert probe.after.calls == 1  # ... and the next widget was still told
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert (probe.own_calls, probe.failing.calls, probe.after.calls) == (2, 2, 2)

    run_pilot(app, scenario)


def test_a_refused_toggle_calls_no_refresh_hook() -> None:
    app = app_for(is_admin=False)
    probe = ProbeScreen()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.push_screen(probe)
        await pilot.pause()
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert (probe.own_calls, probe.failing.calls, probe.after.calls) == (0, 0, 0)

    run_pilot(app, scenario)


def test_palette_entry_runs_the_toggle() -> None:
    app = app_for(is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause()
        await pilot.press(*"technical")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert app.display_mode.technical is True

    run_pilot(app, scenario)


def test_mode_is_off_at_start_and_not_remembered() -> None:
    first = app_for(is_admin=True)

    async def switch_on(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert first.display_mode.technical is True

    run_pilot(first, switch_on)
    second = app_for(is_admin=True)
    assert second.display_mode.technical is False
    assert first.display_mode is not second.display_mode
