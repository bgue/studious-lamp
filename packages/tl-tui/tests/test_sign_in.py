"""The TUI sign-in screen and its host app (P1-I0-T08)."""

from __future__ import annotations

from typing import Any

import httpx2
import pytest
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input, Static
from tl_api.client.base import ApiUnavailableError
from tl_api.errors import ApiError
from tl_core.auth.errors import AccountLockedError, InvalidCredentialsError
from tl_tui.sign_in import SignedIn, SignInApp, SignInScreen

TARGET = "ledger ./dev/data/tl.db"
ROOT = SignedIn(actor="user:root", username="root", roles=("admin",))


class FakeAuth:
    """An `Authenticator` that records its calls and answers from a script."""

    def __init__(self, *answers: SignedIn | Exception) -> None:
        self.answers = list(answers) or [ROOT]
        self.calls: list[tuple[str, str]] = []

    def __call__(self, username: str, password: str) -> SignedIn:
        self.calls.append((username, password))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def fill(app: SignInApp, username: str, password: str) -> None:
    app.screen.query_one("#sign-in-username", Input).value = username
    app.screen.query_one("#sign-in-password", Input).value = password


def error_text(app: SignInApp) -> str:
    return str(app.screen.query_one("#sign-in-error", Static).render())


def focused_id(app: SignInApp) -> str | None:
    return app.focused.id if app.focused is not None else None


def test_the_screen_asks_for_a_username_and_a_password_and_says_where() -> None:
    app = SignInApp(FakeAuth(), target=TARGET, hint="dev setup: demo / demo")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        for line in (
            "Sign in to Throughline",
            TARGET,
            "Username",
            "Password",
            "dev setup: demo / demo",
        ):
            assert line in text, line
        assert "Enter sign in" in text and "Esc quit" in text
        assert focused_id(app) == "sign-in-username"
        assert app.screen.query_one("#sign-in-password", Input).password is True
        assert error_text(app) == ""

    run_pilot(app, scenario)


def test_without_a_hint_the_screen_has_no_hint_line() -> None:
    app = SignInApp(FakeAuth(), target=TARGET)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert not app.screen.query("#sign-in-hint")

    run_pilot(app, scenario)


def test_enter_moves_from_the_username_to_the_password_and_then_signs_in() -> None:
    auth = FakeAuth()
    app = SignInApp(auth, target=TARGET)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        fill(app, "  root  ", " pass phrase ")
        await pilot.press("enter")
        assert focused_id(app) == "sign-in-password" and auth.calls == []
        await pilot.press("enter")
        await pilot.pause()

    run_pilot(app, scenario)
    assert auth.calls == [("root", " pass phrase ")]  # the name is trimmed, the password is not
    assert app.return_value == ROOT


def test_a_refused_sign_in_shows_the_message_clears_the_password_and_allows_another_try() -> None:
    auth = FakeAuth(InvalidCredentialsError(), ROOT)
    app = SignInApp(auth, target=TARGET)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        fill(app, "root", "wrong password!")
        await pilot.press("tab", "enter")
        await pilot.pause()
        assert error_text(app) == "invalid username or password"
        assert "invalid username or password" in screen_text(app)
        assert app.screen.query_one("#sign-in-password", Input).value == ""
        assert app.screen.query_one("#sign-in-username", Input).value == "root"
        assert focused_id(app) == "sign-in-password"
        assert "wrong password!" not in screen_text(app)
        fill(app, "root", "right password!")
        await pilot.press("enter")
        await pilot.pause()

    run_pilot(app, scenario)
    assert [c[1] for c in auth.calls] == ["wrong password!", "right password!"]
    assert app.return_value == ROOT


@pytest.mark.parametrize(
    ("failure", "shown"),
    [
        (AccountLockedError("too many failed sign-ins", "2026-10-11T12:15:00Z"), "too many failed"),
        (ApiUnavailableError(httpx2.ConnectError("down")), "server unreachable"),
        (
            ApiError(429, "rate_limited", "too many failed sign-ins from this address"),
            "too many failed sign-ins from this address",
        ),
    ],
)
def test_other_refusals_are_shown_too(failure: Exception, shown: str) -> None:
    app = SignInApp(FakeAuth(failure), target=TARGET)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        fill(app, "root", "some password")
        await pilot.press("tab", "enter")
        await pilot.pause()
        assert shown in error_text(app)
        assert app.return_value is None and app.is_running

    run_pilot(app, scenario)


def test_a_blank_username_or_password_is_asked_for_without_calling_the_authenticator() -> None:
    auth = FakeAuth()
    app = SignInApp(auth, target=TARGET)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        fill(app, "   ", "something")
        await pilot.press("tab", "enter")
        assert error_text(app) == "Enter your username" and focused_id(app) == "sign-in-username"
        fill(app, "root", "")
        await pilot.press("tab", "enter")
        assert error_text(app) == "Enter your password" and focused_id(app) == "sign-in-password"

    run_pilot(app, scenario)
    assert auth.calls == []


def test_the_password_is_masked_on_screen() -> None:
    app = SignInApp(FakeAuth(), target=TARGET)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("tab")
        await pilot.press(*"hunter2hunter2")
        await pilot.pause()
        assert app.screen.query_one("#sign-in-password", Input).value == "hunter2hunter2"
        assert "hunter2" not in screen_text(app)
        assert "•" in screen_text(app)

    run_pilot(app, scenario)


@pytest.mark.parametrize("key", ["escape", "ctrl+q"])
def test_escape_and_ctrl_q_leave_without_signing_in(key: str) -> None:
    auth = FakeAuth()
    app = SignInApp(auth, target=TARGET)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        fill(app, "root", "typed but never sent")
        await pilot.press(key)
        await pilot.pause()

    run_pilot(app, scenario)
    assert app.return_value is None and auth.calls == []


def test_the_signed_in_value_hides_its_token_and_knows_admins() -> None:
    remote = SignedIn(actor="user:amy", username="amy", roles=("user",), token="tls_secret")
    assert "tls_secret" not in repr(remote) and "tls_secret" not in str(remote)
    assert ROOT.is_admin and not remote.is_admin


def test_the_screen_can_be_pushed_by_a_larger_app_and_dismisses_with_its_result() -> None:
    from textual.app import App

    results: list[SignedIn | None] = []

    class Host(App[None]):
        def on_mount(self) -> None:
            self.push_screen(SignInScreen(FakeAuth(), target=TARGET), results.append)

    app = Host()

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.screen.query_one("#sign-in-username", Input).value = "root"
        app.screen.query_one("#sign-in-password", Input).value = "a password"
        await pilot.press("tab", "enter")
        await pilot.pause()

    run_pilot(app, scenario)
    assert results == [ROOT]


def test_the_sign_in_screen_snapshot_80x24(snap_compare: Any) -> None:
    app = SignInApp(FakeAuth(), target=TARGET, hint="dev setup: demo / demo")
    assert snap_compare(app, terminal_size=(80, 24))


def test_the_sign_in_screen_with_an_error_snapshot_120x40(snap_compare: Any) -> None:
    app = SignInApp(FakeAuth(InvalidCredentialsError()), target=TARGET)

    async def run_before(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        app.screen.query_one("#sign-in-username", Input).value = "root"
        app.screen.query_one("#sign-in-password", Input).value = "not the password"
        await pilot.press("tab", "enter")
        await pilot.pause()

    assert snap_compare(app, terminal_size=(120, 40), run_before=run_before)
