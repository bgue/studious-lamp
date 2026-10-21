"""Plain mode on the accounts and about:config screens: no ids, no change numbers (P1-UX-T09b).

The host app carries a ``display_mode`` the way the app will (P1-UX-T10); a test host without one
reads as plain. Each test turns the technical mode on and off to show what plain mode hides.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.admin_text import TECHNICAL_TOKEN_COLUMNS, TOKEN_COLUMNS
from tl_tui.display import DisplayMode, find_technical
from tl_tui.settings_text import HISTORY_COLUMNS, TECHNICAL_HISTORY_COLUMNS
from tl_tui.widgets.admin_screen import AdminScreen
from tl_tui.widgets.setting_form import SettingForm
from tl_tui.widgets.setting_history import SettingHistory

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
KEY = "feed.signal_tags"


def seeded() -> FakeClient:
    client = FakeClient()
    client.seed_account("boss", roles=["admin", "user"])
    bot = client.seed_account("triage", kind="agent")
    client.issue_agent_token(bot.account_id, "mcp", expires_in_days=90)
    client.issue_agent_token(bot.account_id, "short", expires_in_days=1)
    client.admin_calls.clear()
    return client


class Host(App[None]):
    def __init__(self, client: FakeClient) -> None:
        super().__init__()
        self.client = client
        self.display_mode = DisplayMode()

    def on_mount(self) -> None:
        self.push_screen(AdminScreen(self.client, "user:boss", now=lambda: NOW))


class HistoryHost(App[None]):
    def __init__(self, client: FakeClient, *, technical: bool = False) -> None:
        super().__init__()
        self.client = client
        self.display_mode = DisplayMode()
        self.display_mode.technical = technical

    def on_mount(self) -> None:
        self.push_screen(SettingHistory(self.client, KEY))


def admin(app: Host) -> AdminScreen:
    assert isinstance(app.screen, AdminScreen)
    return app.screen


def labels_of(table: DataTable[str]) -> list[str]:
    return [str(column.label) for column in table.columns.values()]


def test_plain_token_table_has_no_id_column_and_no_token_id_in_the_text() -> None:
    client = seeded()
    app = Host(client)
    token_ids = [token.token_id for token in client.list_agent_tokens()]

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        table = admin(app).query_one("#admin-tokens", DataTable)
        assert labels_of(table) == list(TOKEN_COLUMNS)
        shown = screen_text(app)
        assert "Agent tokens (2)" in shown and "mcp" in shown
        assert not any(token_id in shown for token_id in token_ids)
        assert find_technical(shown) == []

    run_pilot(app, scenario)


def test_technical_mode_shows_the_id_column() -> None:
    client = seeded()
    app = Host(client)
    token_ids = [token.token_id for token in client.list_agent_tokens()]

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        app.display_mode.technical = True
        admin(app).refresh_for_display_mode()
        await pilot.pause()
        table = admin(app).query_one("#admin-tokens", DataTable)
        assert labels_of(table) == list(TECHNICAL_TOKEN_COLUMNS)
        assert all(token_id in screen_text(app) for token_id in token_ids)
        app.display_mode.technical = False
        admin(app).refresh_for_display_mode()
        await pilot.pause()
        assert labels_of(table) == list(TOKEN_COLUMNS)
        assert not any(token_id in screen_text(app) for token_id in token_ids)

    run_pilot(app, scenario)


def test_history_plain_drops_seq_and_names_a_service_actor_as_a_service() -> None:
    client = FakeClient()
    client.setting_actor = "svc:enricher"
    client.set_setting(KEY, layer="company", value=["a"])
    app = HistoryHost(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert isinstance(app.screen, SettingHistory)
        table = app.screen.query_one("#history-table", DataTable)
        assert labels_of(table) == list(HISTORY_COLUMNS)
        shown = screen_text(app)
        assert "a service" in shown and "svc:" not in shown
        assert find_technical(shown) == []
        app.display_mode.technical = True
        app.screen.refresh_for_display_mode()
        await pilot.pause()
        assert labels_of(table) == list(TECHNICAL_HISTORY_COLUMNS)
        assert "svc:enricher" in screen_text(app)

    run_pilot(app, scenario)


def test_the_undo_message_has_no_sequence_number_in_plain_mode() -> None:
    client = FakeClient()
    client.set_setting(KEY, layer="project:P123", value=["a"])
    client.set_setting(KEY, layer="project:P123", value=["b"])
    app = HistoryHost(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("up", "u")  # the cursor starts on the latest; move to the first
        await pilot.pause()
        assert "Only the latest change at Project P123 can be undone." in screen_text(app)
        assert "(#" not in screen_text(app)
        app.display_mode.technical = True
        await pilot.press("u")
        await pilot.pause()
        assert "Only the latest change at project:P123 can be undone (#2)." in screen_text(app)

    run_pilot(app, scenario)


def test_the_undo_reports_the_change_plainly_and_with_its_number_in_technical_mode() -> None:
    client = FakeClient()
    client.set_setting(KEY, layer="project:P123", value=["a"])
    client.set_setting(KEY, layer="project:P123", value=["b"])
    app = HistoryHost(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert isinstance(app.screen, SettingHistory)
        await pilot.press("u")  # the cursor starts on the latest change, which is undoable
        await pilot.pause()
        assert isinstance(app.screen, SettingForm)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, SettingHistory)
        shown = screen_text(app)
        assert "Undid the change." in shown
        assert "Undid #" not in shown and "(#" not in shown

    run_pilot(app, scenario)

    technical_client = FakeClient()
    technical_client.set_setting(KEY, layer="project:P123", value=["a"])
    technical_client.set_setting(KEY, layer="project:P123", value=["b"])
    seq = technical_client.setting_history(KEY)[-1].seq
    technical_app = HistoryHost(technical_client, technical=True)

    async def technical_scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(technical_app.screen, SettingHistory)
        shown = screen_text(technical_app)
        assert f"Undid #{seq}." in shown
        assert "Undid the change." not in shown

    run_pilot(technical_app, technical_scenario)


def test_the_layer_cell_reads_in_plain_words_and_by_its_key_in_technical_mode() -> None:
    client = FakeClient()
    client.set_setting(KEY, layer="project:P123", value=["a"])
    app = HistoryHost(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert isinstance(app.screen, SettingHistory)
        table = app.screen.query_one("#history-table", DataTable)
        assert str(table.get_row_at(0)[0]) == "Project P123"
        assert "project:" not in screen_text(app)
        app.display_mode.technical = True
        app.screen.refresh_for_display_mode()
        await pilot.pause()
        assert str(table.get_row_at(0)[1]) == "project:P123"

    run_pilot(app, scenario)
