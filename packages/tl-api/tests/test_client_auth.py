"""The HTTP client's sign-in and own-account calls (ADR-0009, P1-I0-T03)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from harness import Harness
from tl_api.client import ApiClient
from tl_api.client.auth import sign_in
from tl_api.client.base import ApiUnavailableError
from tl_core.auth import accounts
from tl_core.auth.errors import (
    AccountDisabledError,
    AccountLockedError,
    ForbiddenError,
    InvalidCredentialsError,
    WeakPasswordError,
)
from tl_core.auth.password import prepare_password

PASSWORD = "correct horse battery"
OTHER = "another long passphrase"
BASE = "http://testserver"


@pytest.fixture
def bob(harness: Harness) -> str:
    with harness.backend() as uow:
        view = accounts.create_account(
            uow, username="bob", display_name="Bob", kind="person", roles=["user"],
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip
    return view.account_id


def signed_in(harness: Harness, password: str = PASSWORD) -> ApiClient:
    out = sign_in(BASE, "bob", password, http=harness.client_for(None))
    return ApiClient(BASE, out.token, http=harness.client_for(None))


def test_sign_in_returns_the_token_once_and_the_principal(harness: Harness, bob: str) -> None:
    out = sign_in(BASE, "Bob", PASSWORD, http=harness.client_for(None))
    assert out.token.startswith("tls_") and out.expires_in == 12 * 3600
    assert out.principal.actor == "user:bob" and out.principal.account_id == bob
    assert out.token not in repr(out) and out.token not in str(out)


def test_the_token_works_in_an_api_client_and_whoami_names_it(harness: Harness, bob: str) -> None:
    client = signed_in(harness)
    me = client.whoami()
    assert (me.actor, me.roles, me.via) == ("user:bob", ["user"], "session")


def test_sign_out_ends_the_session(harness: Harness, bob: str) -> None:
    client = signed_in(harness)
    client.sign_out()
    with pytest.raises(Exception) as caught:
        client.whoami()
    assert getattr(caught.value, "status", None) == 401


def test_a_wrong_password_raises_the_embedded_exception(harness: Harness, bob: str) -> None:
    with pytest.raises(InvalidCredentialsError) as caught:
        sign_in(BASE, "bob", "not the password", http=harness.client_for(None))
    assert "not the password" not in str(caught.value)
    with pytest.raises(InvalidCredentialsError):
        sign_in(BASE, "nobody", "not the password", http=harness.client_for(None))


def test_lockout_carries_locked_until(harness: Harness, bob: str) -> None:
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            sign_in(BASE, "bob", "not the password", http=harness.client_for(None))
    with pytest.raises(AccountLockedError) as caught:
        sign_in(BASE, "bob", PASSWORD, http=harness.client_for(None))
    assert caught.value.locked_until is not None and caught.value.locked_until.endswith("Z")


def test_a_disabled_account_raises_account_disabled(harness: Harness, bob: str) -> None:
    with harness.backend() as uow:
        accounts.disable(uow, account_id=bob, by="user:boss", reason=None)
    with pytest.raises(AccountDisabledError):
        sign_in(BASE, "bob", PASSWORD, http=harness.client_for(None))


def test_change_own_password_then_sign_in_with_the_new_one(harness: Harness, bob: str) -> None:
    client = signed_in(harness)
    client.change_own_password(PASSWORD, OTHER)
    with pytest.raises(InvalidCredentialsError):
        sign_in(BASE, "bob", PASSWORD, http=harness.client_for(None))
    assert sign_in(BASE, "bob", OTHER, http=harness.client_for(None)).principal.actor == "user:bob"


def test_a_weak_new_password_carries_its_issues(harness: Harness, bob: str) -> None:
    client = signed_in(harness)
    with pytest.raises(WeakPasswordError) as caught:
        client.change_own_password(PASSWORD, "short")
    assert caught.value.issues and "short" not in str(caught.value)


def test_an_agent_token_cannot_change_a_password(harness: Harness, bob: str) -> None:
    with harness.backend() as uow:
        bot = accounts.create_account(
            uow, username="triage", display_name="T", kind="agent", roles=["user"],
            password=None, by="svc:test",
        )  # fmt: skip
        _, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="t",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    client = ApiClient(BASE, token, http=harness.client_for(None))
    with pytest.raises(ForbiddenError):
        client.change_own_password(PASSWORD, OTHER)
    assert client.whoami().actor == "agent:triage"


def test_an_unreachable_server_is_api_unavailable() -> None:
    with pytest.raises(ApiUnavailableError):
        sign_in("http://127.0.0.1:1", "bob", PASSWORD, timeout=1.0)
