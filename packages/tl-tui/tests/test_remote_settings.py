"""The settings group and the about:config screen over a real API server on loopback (P0-I8-S27).

Nothing is mocked: `RemoteClient` passes the seven settings methods to `ApiClient`, the server
answers from its ledger, and the screen is driven with a pilot. The answers and the refusals have
the classes and messages of the embedded client.
"""

from __future__ import annotations

import pytest
from harness import Harness
from helpers import run_pilot, screen_text
from remote_support import LIVE_TIMEOUT_S, SCOPE, restartable
from textual.pilot import Pilot
from textual.widgets import DataTable, Input
from tl_core.services.errors import (
    InvalidSettingValueError,
    RiskNotAcceptedError,
    SettingLockedError,
    SettingRevertNotLatestError,
    UnknownSettingError,
)
from tl_tui.app import TlApp
from tl_tui.display import DisplayMode
from tl_tui.remote import RemoteClient
from tl_tui.widgets.setting_form import SettingForm
from tl_tui.widgets.setting_history import SettingHistory
from tl_tui.widgets.settings_screen import SettingsScreen

KEY = "feed.reactions.enabled"
TAGS = "feed.signal_tags"


def test_the_seven_calls_round_trip_with_the_embedded_error_classes(harness: Harness) -> None:
    with restartable(harness) as server:
        client = RemoteClient.connect(server.base_url, server.token, timeout=LIVE_TIMEOUT_S)
        assert len(client.list_settings()) == 17
        done = client.set_setting(KEY, layer="project:P123", value=False)
        assert done.effective.value is False and done.effective.modified_here
        assert client.get_setting(KEY).effective.value is True
        assert client.get_setting(KEY, project="P123").effective.value is False
        assert [r.actor for r in client.setting_history(KEY)] == ["user:alice"]
        with pytest.raises(InvalidSettingValueError):
            client.set_setting(KEY, layer="project:P123", value="yes")
        with pytest.raises(UnknownSettingError):
            client.get_setting("no.such")
        with pytest.raises(RiskNotAcceptedError):
            client.set_setting(
                "webhooks.egress.allowlist", layer="company", value=["a.example.com"], reason="r"
            )
        client.lock_setting(KEY, locked=True, reason="policy")
        with pytest.raises(SettingLockedError):
            client.set_setting(KEY, layer="project:P9", value=False)
        client.set_setting(TAGS, layer="company", value=["a"])
        client.set_setting(TAGS, layer="company", value=["b"])
        first = client.setting_history(TAGS)[0].seq
        with pytest.raises(SettingRevertNotLatestError):
            client.revert_setting(TAGS, layer="company", seq=first)
        last = client.setting_history(TAGS)[-1].seq
        assert client.revert_setting(TAGS, layer="company", seq=last).effective.value == ["a"]
        back = client.reset_setting(KEY, layer="project:P123")
        assert not back.effective.modified_here
        client.close()


def test_the_screen_edits_and_undoes_through_the_server(harness: Harness) -> None:
    with restartable(harness) as server:
        remote = RemoteClient.connect(server.base_url, server.token, timeout=LIVE_TIMEOUT_S)
        client = remote.as_client()
        app = TlApp(client, scope=SCOPE, actor="user:alice", mode="remote")

        async def go(pilot: Pilot[None]) -> None:
            await pilot.press("f9")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SettingsScreen)
            assert screen.query_one("#settings-table", DataTable).row_count == 17
            await pilot.press("slash")
            screen.query_one("#settings-filter", Input).value = KEY
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()
            assert isinstance(app.screen, SettingForm)
            app.screen.query_one("#form-value", Input).value = "maybe"
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert "is not true or false" in screen_text(app)
            app.screen.query_one("#form-value", Input).value = "false"
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen) and "project ●" in screen_text(app)
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, SettingHistory)
            assert "alice" in screen_text(app)
            await pilot.press("u")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert isinstance(app.screen, SettingHistory)
            await pilot.press("escape")
            await pilot.pause()
            assert "project ●" not in screen_text(app)

        run_pilot(app, go)
        assert remote.get_setting(KEY, project="P123").effective.value is True
        assert [(c.new_value, c.reset) for c in remote.setting_history(KEY)] == [
            (False, False),
            (None, True),
        ]
        remote.close()


def test_the_history_by_column_reads_the_user_id_only_in_technical_mode(harness: Harness) -> None:
    with restartable(harness) as server:
        remote = RemoteClient.connect(server.base_url, server.token, timeout=LIVE_TIMEOUT_S)
        remote.set_setting(KEY, layer="project:P123", value=False)
        client = remote.as_client()
        app = TlApp(client, scope=SCOPE, actor="user:alice", mode="remote")
        mode = DisplayMode()
        assert mode.toggle(is_admin=True) == ""
        app.display_mode = mode  # pyright: ignore[reportAttributeAccessIssue]  # App does not declare it yet

        async def go(pilot: Pilot[None]) -> None:
            app.push_screen(SettingHistory(client, KEY))
            await pilot.pause()
            assert isinstance(app.screen, SettingHistory)
            assert "user:alice" in screen_text(app)

        run_pilot(app, go)
        remote.close()
