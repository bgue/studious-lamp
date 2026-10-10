"""The about:config screens on the fake client, driven with a pilot (P0-I8-S19)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Checkbox, DataTable, Input
from tl_tui.app import TlApp
from tl_tui.widgets.setting_form import SettingForm
from tl_tui.widgets.setting_history import SettingHistory
from tl_tui.widgets.settings_screen import SettingsScreen

KEY = "feed.reactions.enabled"


def scenario(client: FakeClient, steps: Callable[[Pilot[None], TlApp], Awaitable[None]]) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f9")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        await steps(pilot, app)

    run_pilot(app, go)


async def filter_to(pilot: Pilot[None], app: TlApp, text: str) -> None:
    screen = app.screen
    assert isinstance(screen, SettingsScreen)
    await pilot.press("slash")
    screen.query_one("#settings-filter", Input).value = text
    await pilot.pause()
    await pilot.press("enter")  # back to the table
    await pilot.pause()


def form(app: TlApp) -> SettingForm:
    assert isinstance(app.screen, SettingForm)
    return app.screen


def test_f9_lists_the_settings_with_their_origin_and_closes_with_escape() -> None:
    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        text = screen_text(app)
        assert "about:config for P123: changes go to the project" in text
        assert "ai.agents.daily_proposals" in text and "default" in text
        table = app.screen.query_one("#settings-table", DataTable)
        assert table.row_count == 10
        assert "key ai.agents.daily_proposals" in text  # the detail of the first row
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SettingsScreen)

    scenario(FakeClient(), steps)


def test_the_filter_narrows_by_name_or_description() -> None:
    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, "feed.")
        table = app.screen.query_one("#settings-table", DataTable)
        assert table.row_count == 2
        assert "lake.sync.interval" not in screen_text(app)
        await filter_to(pilot, app, "nothing like this")
        assert table.row_count == 0 and "No setting matches." in screen_text(app)

    scenario(FakeClient(), steps)


def test_editing_a_value_sets_it_at_the_project_and_marks_it() -> None:
    client = FakeClient()

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, KEY)
        await pilot.press("e")
        await pilot.pause()
        assert "at project:P123" in screen_text(app)
        form(app).query_one("#form-value", Input).value = "false"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert "project ●" in screen_text(app)
        assert "Set: feed.reactions.enabled" in screen_text(app)

    scenario(client, steps)
    assert client.setting_calls[-3:][1:] == [
        ("set_setting", {"key": KEY, "layer": "project:P123", "value": False}),
        ("list_settings", {"project": "P123", "prefix": None}),
    ]


def test_a_refused_value_stays_in_the_form_with_the_message() -> None:
    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, KEY)
        await pilot.press("e")
        await pilot.pause()
        form(app).query_one("#form-value", Input).value = "maybe"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, SettingForm)
        assert "'maybe' is not true or false" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

    scenario(FakeClient(), steps)


def test_a_dangerous_key_asks_for_a_reason_and_the_risk() -> None:
    client = FakeClient()

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, "webhooks.egress")
        await pilot.press("e")
        await pilot.pause()
        assert "at company" in screen_text(app)  # the key has no project layer
        f = form(app)
        f.query_one("#form-value", Input).value = "a.example.com"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "needs a reason" in screen_text(app)
        f.query_one("#form-reason", Input).value = "partner hub"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "accept the risk" in screen_text(app) and isinstance(app.screen, SettingForm)
        f.query_one("#form-risk", Checkbox).value = True
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

    scenario(client, steps)
    assert client.get_setting("webhooks.egress.allowlist").effective.value == ["a.example.com"]
    (change,) = client.setting_history("webhooks.egress.allowlist")
    assert (change.reason, change.layer) == ("partner hub", "company")


def test_reset_takes_the_value_away_and_only_where_it_is_set() -> None:
    client = FakeClient()
    client.seed_setting(KEY, "project:P123", False)

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, KEY)
        assert "project ●" in screen_text(app)
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        text = screen_text(app)
        assert "project ●" not in text and "Reset: feed.reactions.enabled" in text
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert "nothing to reset" in screen_text(app)

    scenario(client, steps)


def test_a_key_the_company_locked_cannot_be_changed_by_the_project() -> None:
    client = FakeClient()
    client.lock_setting(KEY, locked=True, reason="policy")

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, KEY)
        assert "locked" in screen_text(app)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert "locked by the company" in screen_text(app)

    scenario(client, steps)


def test_the_layer_key_sends_changes_to_the_company_and_back() -> None:
    client = FakeClient()

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, KEY)
        await pilot.press("L")
        await pilot.pause()
        assert "changes go to the company" in screen_text(app)
        await pilot.press("e")
        await pilot.pause()
        assert "at company" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("L")
        await pilot.pause()
        assert "changes go to the project" in screen_text(app)

    scenario(client, steps)


def test_lock_asks_for_a_reason_and_unlock_undoes_it() -> None:
    client = FakeClient()

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, KEY)
        await pilot.press("k")
        await pilot.pause()
        assert "Lock for projects" in screen_text(app)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "A reason is required" in screen_text(app)
        form(app).query_one("#form-reason", Input).value = "policy"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert "Locked: feed.reactions.enabled" in screen_text(app)
        await pilot.press("k")
        await pilot.pause()
        assert "Unlock for projects" in screen_text(app)

    scenario(client, steps)
    assert client.get_setting(KEY).effective.locked


def test_a_key_that_cannot_be_locked_says_so() -> None:
    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, "lake.sync")
        await pilot.press("k")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert "cannot be locked" in screen_text(app)

    scenario(FakeClient(), steps)


def test_modified_only_lists_what_is_set_at_the_layer() -> None:
    client = FakeClient()
    client.seed_setting(KEY, "project:P123", False)

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await pilot.press("m")
        await pilot.pause()
        table = app.screen.query_one("#settings-table", DataTable)
        assert table.row_count == 1 and "(modified only)" in screen_text(app)
        await pilot.press("m")
        await pilot.pause()
        assert table.row_count == 10

    scenario(client, steps)


def test_history_lists_the_changes_and_undoes_only_the_latest() -> None:
    client = FakeClient()
    client.set_setting("feed.signal_tags", layer="project:P123", value=["a"])
    client.set_setting("feed.signal_tags", layer="project:P123", value=["b"])

    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        await filter_to(pilot, app, "feed.signal")
        await pilot.press("h")
        await pilot.pause()
        assert isinstance(app.screen, SettingHistory)
        text = screen_text(app)
        assert "History of feed.signal_tags" in text and "null -> [a]" in text
        assert "[a] -> [b]" in text
        await pilot.press("up", "u")  # the cursor starts on the latest; move to the first
        await pilot.pause()
        assert "Only the latest change at project:P123 can be undone (#2)" in screen_text(app)
        await pilot.press("down", "u")
        await pilot.pause()
        assert isinstance(app.screen, SettingForm)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, SettingHistory)
        assert "Undid #2." in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

    scenario(client, steps)
    assert client.get_setting("feed.signal_tags", project="P123").effective.value == ["a"]


def test_the_palette_offers_about_config() -> None:
    from tl_tui.commands import command_by_id

    command = command_by_id("settings")
    assert command is not None and command.keys == "F9" and command.action == "settings"
