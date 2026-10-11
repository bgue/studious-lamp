"""Signing in before the TUI opens: the authenticators and the flow in `main` (P1-I0-S4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from tl_adapters.db import make_uow_factory
from tl_adapters.sqlite.uow import create_schema
from tl_api.client import ApiClient
from tl_api.client.base import ApiUnavailableError
from tl_api.errors import ApiError
from tl_core.auth import accounts, seed
from tl_core.auth.errors import AccountLockedError, InvalidCredentialsError
from tl_core.auth.password import prepare_password
from tl_tui import main as tui_main
from tl_tui.embedded import EmbeddedAuthenticator, sqlite_uow_factory
from tl_tui.remote import RemoteAuthenticator, sign_out
from tl_tui.sign_in import SignedIn

GOOD = "correct horse battery"
ROOT = SignedIn(actor="user:root", username="root", roles=("admin",))


def make_ledger(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    factory = sqlite_uow_factory(path)
    for name, roles in (("root", ["admin"]), ("amy", ["user"])):
        prepared = prepare_password(GOOD, username=name)
        with factory(False) as uow:
            accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=roles,
                password=prepared, by="svc:test",
            )  # fmt: skip
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TL_REMOTE", "TL_TOKEN", "TL_TYPE", "TL_DB", "TL_PROJECT"):
        monkeypatch.delenv(name, raising=False)


# --- the embedded authenticator ------------------------------------------------------------------


def test_the_embedded_authenticator_names_the_account_and_its_roles(tmp_path: Path) -> None:
    auth = EmbeddedAuthenticator.for_sqlite(make_ledger(tmp_path))
    assert auth("root", GOOD) == ROOT
    assert auth("AMY", GOOD) == SignedIn(actor="user:amy", username="amy", roles=("user",))


def test_it_refuses_alike_a_wrong_password_and_an_unknown_name_and_locks_after_five(
    tmp_path: Path,
) -> None:
    auth = EmbeddedAuthenticator.for_sqlite(make_ledger(tmp_path))
    for name in ("root", "nobody"):
        with pytest.raises(InvalidCredentialsError, match="invalid username or password"):
            auth(name, "this is not the password")
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            auth("amy", "this is not the password")
    with pytest.raises(AccountLockedError):
        auth("amy", GOOD)


def test_the_demo_hint_shows_only_where_the_demo_account_can_be_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = make_ledger(tmp_path)
    auth = EmbeddedAuthenticator.for_sqlite(path)
    monkeypatch.setenv("TL_ENV", "dev")
    assert auth.demo_hint() is None  # no demo account yet
    seed.seed_demo(make_uow_factory(path), env="dev")
    assert auth.demo_hint() == "dev setup: sign in as demo / demo"
    assert auth("demo", "demo").is_admin
    monkeypatch.setenv("TL_ENV", "prod")
    assert auth.demo_hint() is None


# --- the remote authenticator --------------------------------------------------------------------


def test_the_remote_authenticator_signs_in_over_http_and_keeps_the_token(harness: Harness) -> None:
    with harness.backend() as uow:
        accounts.create_account(
            uow, username="root", display_name="Root", kind="person", roles=["admin"],
            password=prepare_password(GOOD), by="svc:test",
        )  # fmt: skip
    auth = RemoteAuthenticator("http://testserver", http=harness.client_for(None))
    signed = auth("root", GOOD)
    assert signed.actor == "user:root" and signed.roles == ("admin",) and signed.is_admin
    assert signed.token is not None and signed.token.startswith("tls_")
    assert signed.token not in repr(signed)
    me = ApiClient("http://testserver", signed.token, http=harness.client_for(None)).whoami()
    assert me.actor == "user:root"
    with pytest.raises(InvalidCredentialsError):
        auth("root", "this is not the password")


def test_the_remote_authenticator_reports_an_unreachable_server() -> None:
    with pytest.raises(ApiUnavailableError):
        RemoteAuthenticator("http://127.0.0.1:9")("root", GOOD)


# --- make_app, needs_sign_in, sign_in_first, run -------------------------------------------------


def test_make_app_takes_the_actor_and_the_admin_flag_from_the_person_who_signed_in(
    tmp_path: Path,
) -> None:
    path = make_ledger(tmp_path)
    app = tui_main.make_app(db=path, signed_in=ROOT)
    assert app.actor == "user:root" and app.is_admin is True
    plain = tui_main.make_app(db=path, signed_in=SignedIn("user:amy", "amy", ("user",)))
    assert plain.actor == "user:amy" and plain.is_admin is False
    assert tui_main.make_app(db=path).actor == "user:dev"  # callers that do not sign in


def test_a_remote_app_uses_the_session_token_of_the_sign_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_remote(url: str, token: str, project: str, **kwargs: Any) -> str:
        seen.update(url=url, token=token, **kwargs)
        return "app"

    monkeypatch.setattr(tui_main, "build_remote_app", fake_remote)
    signed = SignedIn("user:root", "root", ("admin",), token="tls_x")
    assert tui_main.make_app(remote="http://h", signed_in=signed) == "app"  # type: ignore[comparison-overlap]
    assert seen["token"] == "tls_x" and seen["actor"] == "user:root" and seen["is_admin"] is True
    with pytest.raises(ValueError, match="sign in, pass --token or set TL_TOKEN"):
        tui_main.make_app(remote="http://h")
    assert tui_main.make_app(remote="http://h", token="dev-token") == "app"  # type: ignore[comparison-overlap]
    assert seen["token"] == "dev-token"


def test_needs_sign_in_unless_remote_with_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    assert tui_main.needs_sign_in() is True  # embedded
    assert tui_main.needs_sign_in(remote="http://h") is True
    assert tui_main.needs_sign_in(remote="http://h", token="t") is False
    monkeypatch.setenv("TL_REMOTE", "http://h")
    assert tui_main.needs_sign_in() is True
    monkeypatch.setenv("TL_TOKEN", "t")
    assert tui_main.needs_sign_in() is False


def test_sign_in_first_refuses_a_missing_ledger_and_a_bad_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no ledger at .*tl init"):
        tui_main.sign_in_first(db=tmp_path / "none.db")
    assert not (tmp_path / "none.db").exists()
    with pytest.raises(ValueError, match="http"):
        tui_main.sign_in_first(remote="ftp://x")


def test_run_does_not_open_the_app_when_the_person_quits_the_sign_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tui_main, "sign_in_first", lambda **_: None)
    monkeypatch.setattr(tui_main, "make_app", lambda **_: pytest.fail("the app was built"))
    tui_main.run(db=tmp_path / "tl.db")


def test_run_signs_in_then_builds_and_runs_the_app_and_closes_the_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class FakeApp:
        class client:  # noqa: N801
            @staticmethod
            def close() -> None:
                events.append("closed")

        def run(self) -> None:
            events.append("ran")

    def build(**kwargs: Any) -> FakeApp:
        events.append(f"built as {kwargs['signed_in'].actor}")
        return FakeApp()

    monkeypatch.setattr(tui_main, "sign_in_first", lambda **_: ROOT)
    monkeypatch.setattr(tui_main, "make_app", build)
    tui_main.run(db=tmp_path / "tl.db")
    assert events == ["built as user:root", "ran", "closed"]


def test_run_skips_the_sign_in_when_the_caller_already_knows_the_person(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tui_main, "sign_in_first", lambda **_: pytest.fail("asked again"))
    built: list[SignedIn | None] = []

    class FakeApp:
        client = None

        def run(self) -> None:
            pass

    monkeypatch.setattr(
        tui_main, "make_app", lambda **kw: built.append(kw["signed_in"]) or FakeApp()
    )
    tui_main.run(db=tmp_path / "tl.db", signed_in=ROOT)
    assert built == [ROOT]


# --- ending the server session, and the plain-http warning ---------------------------------------

REMOTE = SignedIn("user:root", "root", ("admin",), token="tls_remote")


class _App:
    client = None

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def run(self) -> None:
        if self.fail:
            raise RuntimeError("the app crashed")


def _remote_run(
    monkeypatch: pytest.MonkeyPatch, app: Any, *, signed: SignedIn | None = REMOTE, **options: Any
) -> list[tuple[str, str]]:
    ended: list[tuple[str, str]] = []
    monkeypatch.setattr(tui_main, "sign_in_first", lambda **_: signed)
    monkeypatch.setattr(tui_main, "make_app", lambda **_: app)
    monkeypatch.setattr(tui_main, "sign_out", lambda url, token: ended.append((url, token)))
    tui_main.run(remote="https://tl.example", **options)
    return ended


def test_the_server_session_is_ended_when_the_tui_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _remote_run(monkeypatch, _App()) == [("https://tl.example", "tls_remote")]


def test_the_server_session_is_ended_when_the_app_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    ended: list[tuple[str, str]] = []
    monkeypatch.setattr(tui_main, "sign_in_first", lambda **_: REMOTE)
    monkeypatch.setattr(tui_main, "make_app", lambda **_: _App(fail=True))
    monkeypatch.setattr(tui_main, "sign_out", lambda url, token: ended.append((url, token)))
    with pytest.raises(RuntimeError, match="crashed"):
        tui_main.run(remote="https://tl.example")
    assert ended == [("https://tl.example", "tls_remote")]


def test_the_server_session_is_ended_when_the_app_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ended: list[tuple[str, str]] = []
    monkeypatch.setattr(tui_main, "sign_in_first", lambda **_: REMOTE)
    monkeypatch.setattr(tui_main, "sign_out", lambda url, token: ended.append((url, token)))

    def broken(**_: Any) -> Any:
        raise ValueError("bad option")

    monkeypatch.setattr(tui_main, "make_app", broken)
    with pytest.raises(ValueError):
        tui_main.run(remote="https://tl.example")
    assert ended == [("https://tl.example", "tls_remote")]


def test_a_session_or_token_the_caller_brought_is_not_ours_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _remote_run(monkeypatch, _App(), signed=None, token="dev-token") == []
    assert _remote_run(monkeypatch, _App(), signed=None, signed_in=REMOTE) == []


def test_an_embedded_run_ends_no_server_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ended: list[tuple[str, str]] = []
    monkeypatch.setattr(tui_main, "sign_in_first", lambda **_: ROOT)
    monkeypatch.setattr(tui_main, "make_app", lambda **_: _App())
    monkeypatch.setattr(tui_main, "sign_out", lambda url, token: ended.append((url, token)))
    tui_main.run(db=tmp_path / "tl.db")
    assert ended == []


def test_sign_out_ends_the_session_on_the_server_and_never_raises(harness: Harness) -> None:
    with harness.backend() as uow:
        accounts.create_account(
            uow, username="root", display_name="Root", kind="person", roles=["admin"],
            password=prepare_password(GOOD), by="svc:test",
        )  # fmt: skip
    http = harness.client_for(None)
    signed = RemoteAuthenticator("http://testserver", http=http)("root", GOOD)
    assert signed.token is not None
    assert ApiClient("http://testserver", signed.token, http=http).whoami().actor == "user:root"
    sign_out("http://testserver", signed.token, http=http)
    with pytest.raises(ApiError) as refused:
        ApiClient("http://testserver", signed.token, http=http).whoami()
    assert refused.value.status == 401
    sign_out("http://testserver", signed.token, http=http)  # already ended: ignored
    sign_out("http://127.0.0.1:9", "tls_whatever")  # unreachable: ignored


@pytest.mark.parametrize(
    ("url", "warned"),
    [
        ("http://tl.example", True),
        ("http://10.0.0.5:8765", True),
        ("http://[2001:db8::1]:80", True),
        ("https://tl.example", False),
        ("http://localhost:8765", False),
        ("http://127.0.0.1:8765", False),
        ("http://127.1.2.3", False),
        ("http://[::1]:8765", False),
    ],
)
def test_plain_http_to_another_host_is_warned_about_on_the_sign_in_screen(
    url: str, warned: bool
) -> None:
    message = tui_main.plain_http_warning(url)
    assert (message is not None) is warned
    if message is not None:
        assert "plain http" in message and "unencrypted" in message
