"""Remote policy (P2-REL-S2): plain http to a non-loopback host is refused before any prompt."""

from __future__ import annotations

import pytest
from harness import Harness
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_tui import main as tui_main
from tl_tui.remote import RemoteAuthenticator

GOOD = "correct horse battery"
PLAIN = ["http://tl.example", "http://10.0.0.5:8765", "http://[2001:db8::1]:80"]
PASSES = [
    "https://tl.example",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
    "http://[::1]:8765",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TL_REMOTE", "TL_TOKEN", "TL_TYPE", "TL_DB", "TL_PROJECT", "TL_ALLOW_PLAIN_HTTP"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("url", PLAIN)
def test_plain_http_to_another_host_is_refused(url: str) -> None:
    with pytest.raises(ValueError, match="plain http"):
        tui_main.check_remote_policy(url)


@pytest.mark.parametrize("url", PASSES)
def test_https_and_loopback_pass(url: str) -> None:
    tui_main.check_remote_policy(url)


def test_the_override_lets_plain_http_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TL_ALLOW_PLAIN_HTTP", "1")
    tui_main.check_remote_policy("http://tl.example")
    assert tui_main.plain_http_warning("http://tl.example") is not None  # the warning line stays


@pytest.mark.parametrize("value", ["0", "", "yes", "true"])
def test_only_one_overrides(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TL_ALLOW_PLAIN_HTTP", value)
    with pytest.raises(ValueError):
        tui_main.check_remote_policy("http://tl.example")


def test_the_refusal_names_the_host_and_never_a_secret() -> None:
    with pytest.raises(ValueError) as refused:
        tui_main.check_remote_policy("http://amy:hunter2@tl.example:8765/x?token=tls_abc")
    text = str(refused.value)
    assert "tl.example" in text
    for secret in ("hunter2", "amy", "tls_abc", "token="):
        assert secret not in text


def test_main_exits_2_with_error_before_any_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_prompt(**kwargs: object) -> None:
        raise AssertionError("the sign-in screen opened")

    monkeypatch.setattr(tui_main, "SignInApp", no_prompt)
    assert tui_main.main(["--remote", "http://tl.example"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "tl.example" in err


def test_main_refuses_even_with_a_token_given(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TL_REMOTE", "http://tl.example")
    monkeypatch.setenv("TL_TOKEN", "tls_secrettoken")
    assert tui_main.main([]) == 2
    captured = capsys.readouterr()
    assert "tls_secrettoken" not in captured.out + captured.err


def test_sign_in_first_and_make_app_refuse_plain_http() -> None:
    with pytest.raises(ValueError, match="plain http"):
        tui_main.sign_in_first(remote="http://tl.example")
    with pytest.raises(ValueError, match="plain http"):
        tui_main.make_app(remote="http://tl.example", token="t")


def test_the_override_opens_the_sign_in_with_the_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TL_ALLOW_PLAIN_HTTP", "1")
    seen: dict[str, object] = {}

    class Fake:
        def __init__(self, auth: object, *, target: str, hint: str | None) -> None:
            seen.update(target=target, hint=hint)

        def run(self) -> None:
            return None

    monkeypatch.setattr(tui_main, "SignInApp", Fake)
    assert tui_main.sign_in_first(remote="http://tl.example") is None
    assert "plain http" in str(seen["hint"])


def test_a_remote_sign_in_prints_neither_the_password_nor_the_session_token(
    harness: Harness, capfd: pytest.CaptureFixture[str]
) -> None:
    with harness.backend() as uow:
        accounts.create_account(
            uow, username="root", display_name="Root", kind="person", roles=["admin"],
            password=prepare_password(GOOD), by="svc:test",
        )  # fmt: skip
    auth = RemoteAuthenticator("http://testserver", http=harness.client_for(None))
    signed = auth("root", GOOD)
    assert signed.token is not None
    out = capfd.readouterr()
    for stream in (out.out, out.err):
        assert signed.token not in stream and GOOD not in stream
