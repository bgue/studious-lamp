"""Ctrl+R and Ctrl+E open the review queue and the integration registry (P1-I7). Supervisor-built:
the app wiring of the two screens; the screens have their own tests."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.commands import command_by_id
from tl_tui.widgets.integration_screen import IntegrationScreen
from tl_tui.widgets.review_queue import ReviewQueueScreen
from tl_tui.widgets.settings_screen import SettingsScreen


def test_anyone_opens_the_review_queue_and_nothing_opens_over_another_modal() -> None:
    app = TlApp(FakeClient(), scope=SCOPE, actor="user:kim", is_admin=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        await pilot.press("ctrl+e")  # not over the queue
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        await pilot.press("escape", "f9", "ctrl+r")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

    run_pilot(app, scenario)


def test_the_registry_opens_for_an_admin_only() -> None:
    app = TlApp(FakeClient(), scope=SCOPE, actor="user:boss", is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert isinstance(app.screen, IntegrationScreen)

    run_pilot(app, scenario)


def test_the_palette_names_both_commands_and_the_app_binds_their_keys() -> None:
    review = command_by_id("review")
    registry = command_by_id("integration")
    assert review is not None and review.keys == "Ctrl+R" and review.action == "review"
    assert registry is not None and registry.keys == "Ctrl+E" and registry.action == "integration"
    bound = {(b.key, b.action) for b in TlApp.BINDINGS if hasattr(b, "key")}  # type: ignore[union-attr]
    assert ("ctrl+r", "review") in bound and ("ctrl+e", "integration") in bound
