"""Snapshots of the about:config list and a change form at 120x40 (P0-I8-S19)."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.widgets.settings_screen import SettingsScreen


def seeded() -> FakeClient:
    client = FakeClient()
    client.seed_setting("feed.reactions.enabled", "project:P123", False)
    client.seed_setting("feed.signal_tags", "company", ["safety", "hold", "ncr"])
    client.set_setting("lake.sync.interval", layer="company", value="30m")
    client.lock_setting("feed.signal_tags", locked=True, reason="policy")
    return client


def test_the_settings_list_snapshot(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[None]) -> None:
        await pilot.press("f9")
        await pilot.pause()

    app = TlApp(seeded(), scope=SCOPE, actor="user:kim")
    assert snap_compare(app, terminal_size=(120, 40), run_before=run_before)


def test_the_change_form_of_a_dangerous_key_snapshot(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[None]) -> None:
        await pilot.press("f9")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, SettingsScreen)
        await pilot.press("slash")
        screen.query_one("#settings-filter").value = "webhooks.egress"  # type: ignore[attr-defined]
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

    app = TlApp(seeded(), scope=SCOPE, actor="user:kim")
    assert snap_compare(app, terminal_size=(120, 40), run_before=run_before)
