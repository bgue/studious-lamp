"""The HTTP client's admin calls (ADR-0009, P1-I0-T04)."""

from __future__ import annotations

import pytest
from harness import Harness
from tl_api.client import ApiClient
from tl_api.client.auth import sign_in
from tl_api.errors import ApiError
from tl_core.auth import accounts
from tl_core.auth.errors import (
    AccountNotFoundError,
    AccountStateError,
    AgentTokenNotFoundError,
    ForbiddenError,
    InvalidAccountError,
    LastAdminError,
    UsernameTakenError,
    WeakPasswordError,
)
from tl_core.auth.password import prepare_password

PASSWORD = "correct horse battery"
OTHER = "another long passphrase"
BASE = "http://testserver"


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    """These tests run on every adapter (`just test-parity`): the ledger is the parity `db`."""
    return parity_harness


@pytest.fixture
def admin(harness: Harness) -> ApiClient:
    with harness.backend() as uow:
        for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
            accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=roles,
                password=prepare_password(PASSWORD), by="svc:test",
            )  # fmt: skip
    return client_for(harness, "boss")


def client_for(harness: Harness, username: str) -> ApiClient:
    out = sign_in(BASE, username, PASSWORD, http=harness.client_for(None))
    return ApiClient(BASE, out.token, http=harness.client_for(None))


def test_a_user_gets_forbidden_from_every_admin_call(harness: Harness, admin: ApiClient) -> None:
    user = client_for(harness, "bob")
    calls = [
        lambda: user.list_accounts(),
        lambda: user.get_account("x"),
        lambda: user.create_account("eve", "Eve"),
        lambda: user.set_roles("x", ["user"]),
        lambda: user.disable_account("x"),
        lambda: user.enable_account("x"),
        lambda: user.reset_password("x", OTHER),
        lambda: user.list_agent_tokens(),
        lambda: user.issue_agent_token("x", "t"),
        lambda: user.revoke_agent_token("x"),
    ]
    for call in calls:
        with pytest.raises(ForbiddenError):
            call()


def test_list_get_and_create(admin: ApiClient) -> None:
    assert [a.username for a in admin.list_accounts()] == ["boss", "bob"]
    created = admin.create_account("Carol", "Carol C", roles=["user"], password=OTHER)
    assert created.username == "carol" and created.roles == ["user"] and created.kind == "person"
    assert admin.get_account(created.account_id).account_id == created.account_id
    with pytest.raises(AccountNotFoundError):
        admin.get_account("nope")
    with pytest.raises(UsernameTakenError):
        admin.create_account("CAROL", "again")
    with pytest.raises(WeakPasswordError) as weak:
        admin.create_account("dave", "Dave", password="short")
    assert weak.value.issues and "short" not in str(weak.value)
    with pytest.raises(InvalidAccountError):
        admin.create_account("bot", "Bot", kind="agent", roles=["admin"])


def test_roles_disable_enable_and_reset(harness: Harness, admin: ApiClient) -> None:
    bob = next(a for a in admin.list_accounts() if a.username == "bob")
    assert admin.set_roles(bob.account_id, ["admin", "user"], reason="cover").roles == [
        "admin",
        "user",
    ]
    with pytest.raises(AccountStateError):
        admin.set_roles(bob.account_id, ["user", "admin"])
    assert admin.disable_account(bob.account_id, reason="left").status == "disabled"
    with pytest.raises(AccountStateError):
        admin.disable_account(bob.account_id)
    assert admin.enable_account(bob.account_id).status == "active"
    assert admin.reset_password(bob.account_id, OTHER).locked_until is None
    out = sign_in(BASE, "bob", OTHER, http=harness.client_for(None))
    assert out.principal.actor == "user:bob"


def test_the_last_admin_is_protected(admin: ApiClient) -> None:
    boss = next(a for a in admin.list_accounts() if a.username == "boss")
    with pytest.raises(LastAdminError):
        admin.set_roles(boss.account_id, ["user"])
    with pytest.raises(LastAdminError):
        admin.disable_account(boss.account_id)


def test_agent_tokens_are_issued_once_listed_and_revoked(
    harness: Harness, admin: ApiClient
) -> None:
    bot = admin.create_account("triage", "Triage", kind="agent")
    view, token = admin.issue_agent_token(bot.account_id, "triage assistant")
    assert token.startswith("tla_") and view.label == "triage assistant" and view.expires_at
    forever, _ = admin.issue_agent_token(bot.account_id, "forever", expires_in_days=None)
    assert forever.expires_at is None
    listed = admin.list_agent_tokens(bot.account_id)
    assert [t.token_id for t in listed] == [view.token_id, forever.token_id]
    agent = ApiClient(BASE, token, http=harness.client_for(None))
    assert agent.whoami().actor == "agent:triage"
    assert admin.revoke_agent_token(view.token_id, reason="rotated").revoked is True
    with pytest.raises(Exception) as caught:
        agent.whoami()
    assert getattr(caught.value, "status", None) == 401
    assert [t.token_id for t in admin.list_agent_tokens(include_revoked=False)] == [
        forever.token_id
    ]
    with pytest.raises(AccountStateError):
        admin.revoke_agent_token(view.token_id)
    with pytest.raises(AgentTokenNotFoundError):
        admin.revoke_agent_token("nope")
    bob = next(a for a in admin.list_accounts() if a.username == "bob")
    with pytest.raises(InvalidAccountError):  # a person holds no agent tokens
        admin.issue_agent_token(bob.account_id, "x")


def test_ids_cannot_change_the_path(admin: ApiClient) -> None:
    for bad in ("..", "."):
        with pytest.raises(ValueError):
            admin.get_account(bad)
    with pytest.raises(ApiError) as caught:  # escaped, so it stays one segment: no such route
        admin.get_account("a/b?x=1")
    assert caught.value.status == 404
