"""The sign-in version line (P2-REL-T02): the pure rule, the one read of /health, the screen."""

from __future__ import annotations

from typing import Any

import httpx2
import pytest
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input
from tl_api.client.base import ApiUnavailableError
from tl_tui import main as tui_main
from tl_tui import remote
from tl_tui.sign_in import SignedIn, SignInApp
from tl_tui.version_note import app_version, version_pair_note

ROOT = SignedIn(actor="user:root", username="root", roles=("admin",))
TARGET = "server http://tl.example"


class FakeAuth:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, username: str, password: str) -> SignedIn:
        self.calls.append((username, password))
        return ROOT


@pytest.mark.parametrize(
    ("server", "app", "expected"),
    [
        ("0.1.0", "0.1.0", None),  # equal
        ("0.1.9", "0.1.0", None),  # patch differs only
        ("0.2.0", "0.1.0", "server is 0.2.x, this app is 0.1.x: not a supported pair"),
        ("0.0.5", "0.1.0", "server is 0.0.x, this app is 0.1.x: not a supported pair"),
        ("1.1.0", "0.1.0", "server is 1.1.x, this app is 0.1.x: not a supported pair"),
        ("2.0.0", "1.9.3", "server is 2.0.x, this app is 1.9.x: not a supported pair"),
        ("0.1.0rc1", "0.1.0", None),  # a pre-release of the same minor is the same pair
        ("0.2", "0.1.4", "server is 0.2.x, this app is 0.1.x: not a supported pair"),
        (None, "0.1.0", None),  # the server is unknown
        ("dev", "0.1.0", None),  # non-numeric: cannot be compared, so no claim
        ("0.x", "0.1.0", None),
        ("0.1.0", "unknown", None),  # this app's version is not numeric
        ("", "0.1.0", None),
    ],
)
def test_the_note_names_a_different_major_or_minor_only(
    server: str | None, app: str, expected: str | None
) -> None:
    assert version_pair_note(server, app) == expected


def test_this_app_has_a_version_string() -> None:
    assert isinstance(app_version(), str) and app_version()


def test_server_version_reads_health_once_and_returns_its_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_health(base_url: str, **_: Any) -> dict[str, Any]:
        calls.append(base_url)
        return {"status": "ok", "version": "0.2.3"}

    monkeypatch.setattr(remote, "health", fake_health)
    assert remote.server_version("http://tl.example") == "0.2.3"
    assert calls == ["http://tl.example"]


@pytest.mark.parametrize(
    "failure",
    [
        ApiUnavailableError(httpx2.ConnectError("down")),
        ValueError("not json"),
    ],
)
def test_an_unreadable_health_gives_no_version_and_no_error(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def broken(base_url: str, **_: Any) -> dict[str, Any]:
        raise failure

    monkeypatch.setattr(remote, "health", broken)
    assert remote.server_version("http://tl.example") is None


def test_an_answer_without_a_string_version_gives_no_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(remote, "health", lambda base_url, **_: {"status": "ok"})
    assert remote.server_version("http://tl.example") is None


@pytest.mark.parametrize(("server_says", "shown"), [("0.2.3", True), ("0.1.7", False)])
def test_sign_in_first_shows_the_line_only_for_a_different_pair(
    monkeypatch: pytest.MonkeyPatch, server_says: str, shown: bool
) -> None:
    seen: dict[str, Any] = {}

    class FakeSignInApp:
        def __init__(self, authenticate: Any, **kwargs: Any) -> None:
            seen.update(kwargs)

        def run(self) -> None:
            return None

    monkeypatch.delenv("TL_REMOTE", raising=False)
    monkeypatch.delenv("TL_ALLOW_PLAIN_HTTP", raising=False)
    monkeypatch.setattr(tui_main, "SignInApp", FakeSignInApp)
    monkeypatch.setattr(tui_main, "server_version", lambda url, **_: server_says)
    monkeypatch.setattr(tui_main, "app_version", lambda: "0.1.4")
    tui_main.sign_in_first(remote="https://tl.example")
    if shown:
        assert seen["notice"] == "server is 0.2.x, this app is 0.1.x: not a supported pair"
    else:
        assert seen["notice"] is None


def flat_text(app: SignInApp) -> str:
    """The screen's words in reading order: the box border and the wrap at 60 columns removed."""
    rows = [row.strip(" │") for row in screen_text(app).splitlines()]
    return " ".join(" ".join(rows).split())


def test_the_screen_shows_the_line_for_a_mismatched_server_and_still_lets_you_sign_in() -> None:
    line = version_pair_note("0.2.3", "0.1.4")
    auth = FakeAuth()
    app = SignInApp(auth, target=TARGET, notice=line)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "server is 0.2.x, this app is 0.1.x: not a supported pair" in flat_text(app)
        app.screen.query_one("#sign-in-username", Input).value = "root"
        app.screen.query_one("#sign-in-password", Input).value = "a passphrase"
        await pilot.press("tab", "enter")
        await pilot.pause()

    run_pilot(app, scenario)
    assert auth.calls == [("root", "a passphrase")]
    assert app.return_value == ROOT


def test_the_screen_shows_nothing_for_a_matching_server() -> None:
    app = SignInApp(FakeAuth(), target=TARGET, notice=version_pair_note("0.1.9", "0.1.4"))

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert not app.screen.query("#sign-in-notice")
        assert "not a supported pair" not in flat_text(app)

    run_pilot(app, scenario)
