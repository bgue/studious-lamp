"""Add an account, reset a password, issue and revoke a token on the accounts screen (T09b)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes import FakeClient
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Checkbox, DataTable, Input, RadioButton, RadioSet, Static
from tl_tui.widgets.account_forms import AccountForm, PasswordForm, TokenForm, TokenShown
from tl_tui.widgets.admin_screen import AdminScreen

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
GOOD = "correct horse battery"
OTHER = "another long passphrase"


def seeded() -> FakeClient:
    client = FakeClient()
    client.seed_account("boss", roles=["admin", "user"])
    client.seed_account("amy", display_name="Amy A")
    client.seed_account("kim", status="disabled")
    bot = client.seed_account("triage", kind="agent")
    client.seed_account("sim-1", kind="sim", locked_until="2026-10-11T12:15:00.000000Z")
    gone = client.seed_account("old-bot", kind="agent", status="disabled")
    client.issue_agent_token(bot.account_id, "mcp", expires_in_days=90)
    client.issue_agent_token(bot.account_id, "old", expires_in_days=90)
    client.revoke_agent_token(client.list_agent_tokens()[1].token_id)
    assert gone.status == "disabled"
    client.admin_calls.clear()
    return client


class Host(App[None]):
    def __init__(self, client: FakeClient) -> None:
        super().__init__()
        self.client = client

    def on_mount(self) -> None:
        self.push_screen(AdminScreen(self.client, "user:boss", now=lambda: NOW))


def admin(app: Host) -> AdminScreen:
    screens = [s for s in app.screen_stack if isinstance(s, AdminScreen)]
    return screens[0]


def status(app: Host) -> str:
    return str(admin(app).query_one("#admin-status", Static).render())


def calls(client: FakeClient, name: str) -> list[dict[str, Any]]:
    return [args for method, args in client.admin_calls if method == name]


def cursor_to(app: Host, username: str) -> None:
    names = [a.username for a in admin(app).accounts]
    admin(app).query_one("#admin-accounts", DataTable).move_cursor(row=names.index(username))


def fill(app: Host, **values: str) -> None:
    for name, value in values.items():
        app.screen.query_one(f"#form-{name}", Input).value = value


def error(app: Host) -> str:
    return str(app.screen.query_one(".form-error", Static).render())


def password_fields(app: Host) -> list[str]:
    return [i.value for i in app.screen.query(".form-password") if isinstance(i, Input)]


async def open_form(pilot: Pilot[Any], app: Host, key: str, kind: type) -> None:
    await pilot.pause()
    await pilot.press(key)
    await pilot.pause()
    assert isinstance(app.screen, kind), (key, app.screen)


# --- add an account ------------------------------------------------------------------------------


def test_a_opens_the_add_form_with_its_fields_and_the_extra_hints_show() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "a add  p password  i issue token  x revoke token" in screen_text(app)
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, AccountForm)
        shown = screen_text(app)
        for text in ("Add an account", "Username", "Kind", "Password", "Repeat the password"):
            assert text in shown, text
        assert app.focused is not None and app.focused.id == "form-username"
        assert all(i.password for i in app.screen.query(".form-password") if isinstance(i, Input))

    run_pilot(app, scenario)


def test_a_person_is_added_with_a_password_and_the_list_shows_them() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_form(pilot, app, "a", AccountForm)
        fill(app, username="zed", display="Zed Z", password=GOOD, repeat=GOOD)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        assert "Added zed" in status(app) and "Accounts (7)" in screen_text(app)
        assert "zed" in [a.username for a in admin(app).accounts]

    run_pilot(app, scenario)
    assert calls(client, "create_account") == [
        {"username": "zed", "kind": "person", "roles": ["user"]}
    ]
    assert all(GOOD not in str(call) for call in client.admin_calls)


def test_the_admin_box_and_the_kind_choose_the_roles_and_the_kind() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_form(pilot, app, "a", AccountForm)
        fill(app, username="lead", password=GOOD, repeat=GOOD)
        app.screen.query_one("#form-admin", Checkbox).value = True
        await pilot.press("ctrl+s")
        await pilot.pause()
        await open_form(pilot, app, "a", AccountForm)
        fill(app, username="sim-2", password=GOOD, repeat=GOOD)
        app.screen.query_one("#form-kind", RadioSet).query(RadioButton)[1].value = True
        await pilot.press("ctrl+s")
        await pilot.pause()

    run_pilot(app, scenario)
    made = calls(client, "create_account")
    assert [(c["username"], c["kind"], c["roles"]) for c in made] == [
        ("lead", "person", ["admin", "user"]),
        ("sim-2", "sim", ["user"]),
    ]


def test_an_agent_is_added_without_a_password() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_form(pilot, app, "a", AccountForm)
        fill(app, username="robot")
        app.screen.query_one("#form-kind", RadioSet).query(RadioButton)[2].value = True
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen) and "Added robot" in status(app)
        assert next(a for a in admin(app).accounts if a.username == "robot").kind == "agent"

    run_pilot(app, scenario)
    assert calls(client, "create_account")[0]["kind"] == "agent"


def test_passwords_that_differ_or_an_empty_username_stop_before_any_call() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_form(pilot, app, "a", AccountForm)
        await pilot.press("ctrl+s")
        assert error(app) == "Enter a username"
        fill(app, username="zed", password=GOOD, repeat=OTHER)
        await pilot.press("ctrl+s")
        assert error(app) == "The two passwords differ"
        assert password_fields(app) == ["", ""]  # cleared, the name stays
        assert app.screen.query_one("#form-username", Input).value == "zed"
        assert isinstance(app.screen, AccountForm)

    run_pilot(app, scenario)
    assert calls(client, "create_account") == []


def test_the_services_refusals_are_shown_and_the_form_stays_open_with_empty_passwords() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_form(pilot, app, "a", AccountForm)
        fill(app, username="zed", password="short", repeat="short")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, AccountForm)
        assert "password does not meet the policy" in error(app)
        assert "at least 12 characters" in error(app) and "short" not in error(app).replace(
            "shorter", ""
        ).replace("at least", "")
        assert password_fields(app) == ["", ""]
        fill(app, username="AMY", password=GOOD, repeat=GOOD)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "taken" in error(app) and isinstance(app.screen, AccountForm)

    run_pilot(app, scenario)


def test_escape_cancels_the_add_form_and_a_non_admin_is_told_so() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_form(pilot, app, "a", AccountForm)
        fill(app, username="zed", password=GOOD, repeat=GOOD)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        client.is_admin = False
        await pilot.press("a")
        await pilot.pause()
        fill(app, username="zed", password=GOOD, repeat=GOOD)
        await pilot.press("ctrl+s")
        assert error(app) == "this action needs the admin role"

    run_pilot(app, scenario)
    assert calls(client, "create_account")[-1]["username"] == "zed"
    assert (
        len(calls(client, "create_account")) == 1
    )  # only the non-admin attempt reached the client


# --- reset a password ----------------------------------------------------------------------------


def test_p_resets_a_password_ends_the_lock_and_closes() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "sim-1")
        assert "■ until" in screen_text(app)
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, PasswordForm)
        assert "New password for sim-1" in screen_text(app)
        fill(app, password=OTHER, repeat=OTHER)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        assert "Password reset for sim-1; their sessions ended" in status(app)
        assert "■ until" not in screen_text(app)

    run_pilot(app, scenario)
    assert len(calls(client, "reset_password")) == 1
    assert all(OTHER not in str(call) for call in client.admin_calls)


def test_the_password_form_checks_the_two_fields_and_shows_the_rules() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "amy")
        await pilot.press("p")
        await pilot.pause()
        await pilot.press("ctrl+s")
        assert error(app) == "Enter the new password"
        fill(app, password=GOOD, repeat=OTHER)
        await pilot.press("ctrl+s")
        assert error(app) == "The two passwords differ" and password_fields(app) == ["", ""]
        fill(app, password="short", repeat="short")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "does not meet the policy" in error(app) and password_fields(app) == ["", ""]
        assert isinstance(app.screen, PasswordForm)

    run_pilot(app, scenario)
    assert calls(client, "reset_password") == [{"account_id": client.list_accounts()[1].account_id}]


def test_p_on_an_agent_explains_and_opens_nothing() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "triage")
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        assert "triage is an agent: it has tokens, not a password." in status(app)
        await pilot.press("t")
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)

    run_pilot(app, scenario)


# --- issue a token -------------------------------------------------------------------------------


def test_i_issues_a_token_for_an_agent_and_shows_it_once() -> None:
    client = seeded()
    app = Host(client)
    shown: list[str] = []

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "triage")
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, TokenForm)
        assert "Issue a token for triage" in screen_text(app)
        assert app.screen.query_one("#form-days", Input).value == "90"
        fill(app, label="ci helper")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, TokenShown)
        assert client.last_issued_token is not None
        shown.append(str(app.screen.query_one("#token-value", Static).render()))
        assert "Copy it now" in screen_text(app) and shown[0] == client.last_issued_token
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        assert "Issued token ci helper for triage" in status(app)
        assert client.last_issued_token not in screen_text(app)  # gone for good
        assert "Tokens    2 live" in str(app.screen.query_one("#admin-detail", Static).render())

    run_pilot(app, scenario)
    assert calls(client, "issue_agent_token")[0]["label"] == "ci helper"
    assert all(shown[0] not in str(call) for call in client.admin_calls)


def test_never_expires_and_the_number_of_days_choose_the_lifetime() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "triage")
        await open_form(pilot, app, "i", TokenForm)
        fill(app, label="short", days="7")
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.press("escape")
        await open_form(pilot, app, "i", TokenForm)
        fill(app, label="forever")
        app.screen.query_one("#form-never", Checkbox).value = True
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    run_pilot(app, scenario)
    tokens = {t.label: t.expires_at for t in client.list_agent_tokens()}
    assert tokens["forever"] is None and tokens["short"] is not None
    assert tokens["short"] < client.list_agent_tokens()[0].expires_at  # type: ignore[operator]


def test_a_blank_label_or_days_that_are_not_a_number_stop_before_any_call() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "triage")
        await open_form(pilot, app, "i", TokenForm)
        await pilot.press("ctrl+s")
        assert error(app) == "Enter a label"
        fill(app, label="x", days="soon")
        await pilot.press("ctrl+s")
        assert error(app) == "Days must be a whole number" and isinstance(app.screen, TokenForm)

    run_pilot(app, scenario)
    assert calls(client, "issue_agent_token") == []


def test_a_disabled_agent_is_refused_by_the_service_and_the_form_says_so() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "old-bot")
        await open_form(pilot, app, "i", TokenForm)
        fill(app, label="x")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert error(app) == "the agent account is disabled" and isinstance(app.screen, TokenForm)

    run_pilot(app, scenario)


def test_i_on_a_person_or_on_the_tokens_view_explains_and_opens_nothing() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "amy")
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        assert "Only agents have tokens; amy is a person account." in status(app)
        await pilot.press("t")
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        assert "Press t for the accounts, pick the agent, then i." in status(app)

    run_pilot(app, scenario)


# --- revoke a token ------------------------------------------------------------------------------


def test_x_revokes_the_highlighted_token_after_a_reason() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert admin(app).current_token() is not None
        await pilot.press("x")
        await pilot.pause()
        assert "Revoke token mcp" in screen_text(app)
        app.screen.query_one("#prompt-input", Input).value = "leaked"
        await pilot.press("enter")
        await pilot.pause()
        assert "Revoked token mcp" in status(app)
        assert [t.revoked for t in admin(app).tokens] == [True, True]
        assert "✗ revoked" in screen_text(app)

    run_pilot(app, scenario)
    assert calls(client, "revoke_agent_token")[0]["reason"] == "leaked"


def test_x_escape_and_the_services_refusal_change_nothing() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert "Press t for the tokens, pick one, then x." in status(app)
        await pilot.press("t")
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, AdminScreen)
        await pilot.press("down", "x")  # the second token is revoked already
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert status(app) == "! the token is already revoked"

    run_pilot(app, scenario)
    assert len(calls(client, "revoke_agent_token")) == 1


# --- snapshots -----------------------------------------------------------------------------------


def test_the_add_form_snapshot_120x40(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await open_form(pilot, app, "a", AccountForm)

    app = Host(seeded())
    assert snap_compare(app, terminal_size=(120, 40), run_before=run_before)


def test_the_password_form_with_an_error_snapshot_80x24(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "amy")
        await open_form(pilot, app, "p", PasswordForm)
        fill(app, password=GOOD, repeat=OTHER)
        await pilot.press("ctrl+s")
        await pilot.pause()

    app = Host(seeded())
    assert snap_compare(app, terminal_size=(80, 24), run_before=run_before)


def test_the_token_shown_once_snapshot_120x40(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        cursor_to(app, "triage")
        await open_form(pilot, app, "i", TokenForm)
        fill(app, label="ci helper")
        await pilot.press("ctrl+s")
        await pilot.pause()

    app = Host(seeded())
    assert snap_compare(app, terminal_size=(120, 40), run_before=run_before)
