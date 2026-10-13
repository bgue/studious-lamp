"""The accounts screen over the fake client (P1-I0-T09)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static
from tl_tui.widgets.admin_screen import AdminScreen

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)


def seeded() -> FakeClient:
    client = FakeClient()
    client.seed_account("boss", roles=["admin", "user"])
    client.seed_account("amy", display_name="Amy A")
    client.seed_account("kim", status="disabled")
    bot = client.seed_account("triage", kind="agent")
    client.seed_account("sim-1", kind="sim", locked_until="2026-10-11T12:15:00.000000Z")
    client.issue_agent_token(bot.account_id, "mcp", expires_in_days=90)
    old, _ = client.issue_agent_token(bot.account_id, "old", expires_in_days=90)
    client.issue_agent_token(bot.account_id, "short", expires_in_days=1)
    client.revoke_agent_token(old.token_id)
    client.admin_calls.clear()
    return client


class Host(App[None]):
    def __init__(self, client: FakeClient) -> None:
        super().__init__()
        self.client = client

    def on_mount(self) -> None:
        self.push_screen(AdminScreen(self.client, "user:boss", now=lambda: NOW))


def screen(app: Host) -> AdminScreen:
    assert isinstance(app.screen, AdminScreen)
    return app.screen


def text(widget_id: str, app: Host) -> str:
    return str(screen(app).query_one(widget_id, Static).render())


def calls(client: FakeClient, name: str) -> list[dict[str, Any]]:
    return [args for method, args in client.admin_calls if method == name]


def cursor_to(app: Host, username: str) -> None:
    table = screen(app).query_one("#admin-accounts", DataTable)
    names = [a.username for a in screen(app).accounts]
    table.move_cursor(row=names.index(username))


def test_the_table_lists_every_account_with_symbols_for_status_and_lock() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        shown = screen_text(app)
        assert "Accounts (5)" in shown
        for column in ("Name", "Kind", "Roles", "Status", "Lock"):
            assert column in shown
        assert "boss" in shown and "admin, user" in shown
        assert "✓ active" in shown and "✗ disabled" in shown
        assert "■ until 2026-10-11 12:15" in shown
        assert "d disable/enable  r admin role" in shown
        assert screen(app).query_one("#admin-accounts", DataTable).has_focus

    run_pilot(app, scenario)


def test_the_panel_under_the_table_follows_the_highlighted_account() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "Name      boss" in text("#admin-detail", app)
        await pilot.press("down")
        await pilot.pause()
        detail = text("#admin-detail", app)
        assert "Name      amy" in detail and "Shown as  Amy A" in detail
        cursor_to(app, "triage")
        await pilot.pause()
        assert "Tokens    1 live, 1 revoked" in text("#admin-detail", app)

    run_pilot(app, scenario)


def test_d_disables_an_active_account_after_a_reason_and_reads_the_list_again() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "amy")
        await pilot.press("d")
        await pilot.pause()
        assert "Disable amy" in screen_text(app)
        app.screen.query_one("#prompt-input", Input).value = "left the company"
        await pilot.press("enter")
        await pilot.pause()
        assert "Disabled amy" in text("#admin-status", app)
        assert [a.status for a in screen(app).accounts if a.username == "amy"] == ["disabled"]
        row = screen(app).query_one("#admin-accounts", DataTable).get_row_at(1)
        assert str(row[3]) == "✗ disabled" and screen(app).current_account() is not None
        assert screen(app).current_account().username == "amy"  # type: ignore[union-attr]

    run_pilot(app, scenario)
    assert [c["reason"] for c in calls(client, "disable_account")] == ["left the company"]


def test_d_enables_a_disabled_account_and_a_blank_reason_is_none() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "kim")
        await pilot.press("d")
        await pilot.pause()
        assert "Enable kim" in screen_text(app)
        await pilot.press("enter")  # an empty reason is allowed
        await pilot.pause()
        assert "Enabled kim" in text("#admin-status", app)
        assert next(a for a in screen(app).accounts if a.username == "kim").status == "active"

    run_pilot(app, scenario)
    assert calls(client, "enable_account")[0]["reason"] is None


def test_escape_at_the_reason_prompt_changes_nothing() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "amy")
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)  # only the prompt closed
        assert text("#admin-status", app) == ""

    run_pilot(app, scenario)
    assert calls(client, "disable_account") == []


def test_the_services_refusal_is_shown_and_nothing_changes() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "boss")
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        status = text("#admin-status", app)
        assert status == "! the last active admin cannot be disabled or demoted"
        assert screen(app).accounts[0].status == "active"
        await pilot.press("r")  # demoting the last admin is refused the same way
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert "last active admin" in text("#admin-status", app)

    run_pilot(app, scenario)
    assert len(calls(client, "disable_account")) == 1 and len(calls(client, "set_roles")) == 1


def test_r_gives_and_takes_away_the_admin_role() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "amy")
        await pilot.press("r")
        await pilot.pause()
        assert "Make admin amy" in screen_text(app)
        app.screen.query_one("#prompt-input", Input).value = "team lead"
        await pilot.press("enter")
        await pilot.pause()
        assert "amy is now admin, user" in text("#admin-status", app)
        amy = next(a for a in screen(app).accounts if a.username == "amy")
        assert amy.roles == ["admin", "user"]
        await pilot.press("r")
        await pilot.pause()
        assert "Take the admin role from amy" in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert next(a for a in screen(app).accounts if a.username == "amy").roles == ["user"]

    run_pilot(app, scenario)
    sent = [(c["roles"], c["reason"]) for c in calls(client, "set_roles")]
    assert sent == [(["admin", "user"], "team lead"), (["user"], None)]


def test_r_on_an_agent_or_sim_account_explains_and_calls_nothing() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "triage")
        await pilot.press("r")
        await pilot.pause()
        assert "Only people can be admins; triage is a agent account." in text("#admin-status", app)
        assert isinstance(app.screen, AdminScreen)

    run_pilot(app, scenario)
    assert calls(client, "set_roles") == []


def test_t_switches_to_the_agent_tokens_and_back() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        shown = screen_text(app)
        assert "Agent tokens (3)" in shown
        for column in ("Agent", "Label", "Expires", "State", "Id"):
            assert column in shown
        assert shown.count("triage") == 3
        assert "✓ active" in shown and "✗ revoked" in shown and "! expired" in shown
        assert "Tokens cannot be read back" in text("#admin-detail", app)
        assert screen(app).query_one("#admin-tokens", DataTable).has_focus
        await pilot.press("d")  # account actions do nothing on the tokens view
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        await pilot.press("t")
        await pilot.pause()
        assert "Accounts (5)" in screen_text(app)
        assert screen(app).query_one("#admin-accounts", DataTable).has_focus

    run_pilot(app, scenario)


def test_f5_reads_the_lists_again_and_keeps_the_highlight() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "kim")
        client.seed_account("zed")  # created elsewhere meanwhile
        await pilot.press("f5")
        await pilot.pause()
        assert "Accounts (6)" in screen_text(app) and "Reloaded." in text("#admin-status", app)
        assert screen(app).current_account().username == "kim"  # type: ignore[union-attr]

    run_pilot(app, scenario)


def test_a_non_admin_sees_the_refusal_and_an_empty_screen() -> None:
    client = seeded()
    client.is_admin = False
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert text("#admin-status", app) == "! this action needs the admin role"
        assert "Accounts (0)" in screen_text(app)
        assert "No accounts." in text("#admin-detail", app)
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)

    run_pilot(app, scenario)
    assert calls(client, "disable_account") == []


def test_escape_closes_the_screen() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, AdminScreen)

    run_pilot(app, scenario)


def test_the_accounts_snapshot_120x40(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("down", "down")
        await pilot.pause()

    assert snap_compare(Host(seeded()), terminal_size=(120, 40), run_before=run_before)


def test_the_agent_tokens_snapshot_120x40(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()

    assert snap_compare(Host(seeded()), terminal_size=(120, 40), run_before=run_before)


def test_the_accounts_snapshot_80x24(snap_compare: Any) -> None:
    assert snap_compare(Host(seeded()), terminal_size=(80, 24))


def test_c_gives_and_takes_away_the_controller_role_and_keeps_the_others() -> None:
    client = seeded()
    client.seed_account("dora", roles=["admin", "user"])
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "amy")
        await pilot.press("c")
        await pilot.pause()
        assert "Make document controller amy" in screen_text(app)
        app.screen.query_one("#prompt-input", Input).value = "takes over document control"
        await pilot.press("enter")
        await pilot.pause()
        assert "amy is now document_controller, user" in text("#admin-status", app)
        amy = next(a for a in screen(app).accounts if a.username == "amy")
        assert amy.roles == ["document_controller", "user"]
        assert "document_controller, user" in screen_text(app)  # in the table too
        await pilot.press("c")
        await pilot.pause()
        assert "Take the document controller role from amy" in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert next(a for a in screen(app).accounts if a.username == "amy").roles == ["user"]
        # an admin who is also a controller keeps the admin role when the controller role goes
        cursor_to(app, "dora")
        await pilot.press("c")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert next(a for a in screen(app).accounts if a.username == "dora").roles == [
            "admin",
            "user",
        ]

    run_pilot(app, scenario)
    sent = [(c["roles"], c["reason"]) for c in calls(client, "set_roles")]
    assert sent == [
        (["document_controller", "user"], "takes over document control"),
        (["user"], None),
        (["admin", "document_controller", "user"], None),
        (["admin", "user"], None),
    ]


def test_r_keeps_the_controller_role() -> None:
    client = seeded()
    client.seed_account("dora", roles=["document_controller", "user"])
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "dora")
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        dora = next(a for a in screen(app).accounts if a.username == "dora")
        assert dora.roles == ["admin", "document_controller", "user"]

    run_pilot(app, scenario)


def test_c_on_an_agent_explains_and_calls_nothing_but_a_sim_account_may_be_a_controller() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "triage")
        await pilot.press("c")
        await pilot.pause()
        assert "triage is an agent: agents only propose and cannot control." in text(
            "#admin-status", app
        )
        assert calls(client, "set_roles") == []
        cursor_to(app, "sim-1")
        await pilot.press("c")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        sim = next(a for a in screen(app).accounts if a.username == "sim-1")
        assert sim.roles == ["document_controller", "user"]

    run_pilot(app, scenario)


def test_the_hints_name_the_controller_key() -> None:
    assert "c controller role" in AdminScreen.KEY_HINTS_MORE
    assert len(AdminScreen.KEY_HINTS_MORE) <= 76  # one line of the 80-column screen
