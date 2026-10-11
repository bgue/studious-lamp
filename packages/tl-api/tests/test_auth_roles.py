"""Real sign-in at the HTTP edge: session and agent tokens, roles, dev tokens gated by TL_ENV."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.app import create_app
from tl_api.auth import current_principal, guard
from tl_api.errors import ERROR_TABLE, HTTP_ERRORS, body_for, exception_for
from tl_api.tokens import TokenStore
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import AccountLockedError, ForbiddenError, WeakPasswordError
from tl_core.auth.password import prepare_password
from tl_core.auth.queries import list_accounts
from tl_core.auth.types import Principal

PASSWORD = "correct horse battery"


class Accounts:
    """Accounts on the harness ledger and the bearer headers of their tokens."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        with harness.backend() as uow:
            accounts.create_account(
                uow, username="boss", display_name="Boss", kind="person", roles=["admin"],
                password=prepare_password(PASSWORD), by="svc:test",
            )  # fmt: skip
            accounts.create_account(
                uow, username="bob", display_name="Bob", kind="person", roles=["user"],
                password=prepare_password(PASSWORD), by="svc:test",
            )  # fmt: skip
            bot = accounts.create_account(
                uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
            self.agent_id = bot.account_id
            _, self.agent_token = accounts.issue_agent_token(
                uow,
                account_id=bot.account_id,
                label="t",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                by="svc:test",
            )

    def session(self, username: str) -> dict[str, str]:
        _, token = sessions.sign_in(self.harness.backend, username=username, password=PASSWORD)
        return {"Authorization": f"Bearer {token}"}

    def agent(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.agent_token}"}


@pytest.fixture
def people(harness: Harness) -> Accounts:
    return Accounts(harness)


def secured_app(harness: Harness, **kwargs: object) -> TestClient:
    """The harness app plus two test-only routes behind ``guard``."""
    app = create_app(
        harness.backend,
        settings=harness.settings,
        tokens=TokenStore(harness.settings.tokens_path),
        **kwargs,  # type: ignore[arg-type]
    )

    @app.get("/_t/admin")
    def admin_only(actor: Annotated[str, Depends(guard("admin.test"))]) -> dict[str, str]:
        return {"actor": actor}

    @app.get("/_t/me")
    def me(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        return principal

    client = TestClient(app, raise_server_exceptions=False)
    harness._clients.append(client)  # pyright: ignore[reportPrivateUsage]
    return client


def test_a_session_token_is_accepted_and_names_the_account(
    harness: Harness, people: Accounts
) -> None:
    client = secured_app(harness)
    got = client.get("/_t/me", headers=people.session("bob"))
    assert got.status_code == 200
    body = got.json()
    assert (body["actor"], body["kind"], body["roles"], body["via"]) == (
        "user:bob",
        "person",
        ["user"],
        "session",
    )
    assert client.get("/events", headers=people.session("bob")).status_code == 200


def test_admin_actions_need_the_admin_role(harness: Harness, people: Accounts) -> None:
    client = secured_app(harness)
    assert client.get("/_t/admin", headers=people.session("boss")).json() == {"actor": "user:boss"}
    refused = client.get("/_t/admin", headers=people.session("bob"))
    assert refused.status_code == 403 and refused.json()["error"] == "forbidden"
    assert "admin.test" in refused.json()["message"]


def test_an_agent_token_authenticates_but_is_never_admin_and_never_writes(
    harness: Harness, people: Accounts
) -> None:
    client = secured_app(harness)
    assert client.get("/_t/me", headers=people.agent()).json()["actor"] == "agent:triage"
    assert client.get("/events", headers=people.agent()).status_code == 200
    assert client.get("/_t/admin", headers=people.agent()).status_code == 403
    write = client.post(
        "/commands/CreateRecord",
        headers=people.agent(),
        json={"scope": "project:P123", "record_type": "core.Record", "title": "x", "key": "K-1"},
    )
    assert write.status_code == 403 and write.json()["error"] == "agent_must_propose"


def test_a_signed_out_or_revoked_token_is_a_401(harness: Harness, people: Accounts) -> None:
    client = secured_app(harness)
    headers = people.session("bob")
    assert client.get("/events", headers=headers).status_code == 200
    sessions.sign_out(harness.backend, token=headers["Authorization"].removeprefix("Bearer "))
    gone = client.get("/events", headers=headers)
    assert gone.status_code == 401 and gone.json()["error"] == "unauthorized"
    assert gone.headers["www-authenticate"] == "Bearer"


def test_disabling_an_account_stops_its_token_at_once(harness: Harness, people: Accounts) -> None:
    client = secured_app(harness)
    headers = people.session("bob")
    with harness.backend() as uow:
        target = next(a for a in list_accounts(uow.conn()) if a.username == "bob")
        accounts.disable(uow, account_id=target.account_id, by="user:boss", reason="left")
    assert client.get("/events", headers=headers).status_code == 401


def test_garbage_and_look_alike_tokens_are_401_not_500(harness: Harness, people: Accounts) -> None:
    client = secured_app(harness)
    for value in ("tls_", "tla_" + "A" * 43, "tls_" + "A" * 43, "x" * 5000, "tls_é", "Bearer"):
        # the wire carries bytes, not ascii: send latin-1 bytes as a header value
        header: Any = f"Bearer {value}".encode("latin-1")
        got = client.get("/events", headers={"Authorization": header})
        assert got.status_code == 401, value


def test_unknown_paths_are_401_without_a_token(harness: Harness) -> None:
    client = secured_app(harness)
    assert client.get("/no/such/path").status_code == 401
    assert client.get("/auth/sign-in").status_code in (404, 405)  # open: reaches the router


# --- the dev token file --------------------------------------------------------------------


def test_the_dev_token_works_in_dev_and_test_and_is_a_plain_user(harness: Harness) -> None:
    client = secured_app(harness)  # TL_ENV=dev from the root conftest
    me = client.get("/_t/me", headers=harness.headers("user:alice")).json()
    assert (me["actor"], me["via"], me["roles"]) == ("user:alice", "dev_token", ["user"])
    assert client.get("/_t/admin", headers=harness.headers("user:alice")).status_code == 403


@pytest.mark.parametrize("env", ["prod", "production", "", "staging"])
def test_the_dev_token_is_refused_outside_dev_and_test(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("TL_ENV", env)
    client = secured_app(harness)
    refused = client.get("/events", headers=harness.headers("user:alice"))
    assert refused.status_code == 401 and refused.json()["error"] == "unauthorized"


def test_the_dev_token_can_be_switched_off_explicitly(harness: Harness) -> None:
    client = secured_app(harness, dev_tokens=False)
    assert client.get("/events", headers=harness.headers("user:alice")).status_code == 401


def test_a_real_token_still_works_when_dev_tokens_are_off(
    harness: Harness, people: Accounts
) -> None:
    client = secured_app(harness, dev_tokens=False)
    assert client.get("/events", headers=people.session("boss")).status_code == 200


# --- the error table -----------------------------------------------------------------------


def test_the_new_error_rows_have_the_contract_statuses() -> None:
    by_code = {spec.error: spec.status for spec in ERROR_TABLE}
    assert by_code["invalid_credentials"] == 401 and by_code["account_locked"] == 423
    assert by_code["account_disabled"] == 403 and by_code["forbidden"] == 403
    assert by_code["last_admin"] == 409 and by_code["weak_password"] == 422
    assert by_code["username_taken"] == 409
    assert "forbidden" not in HTTP_ERRORS


def test_locked_until_and_password_issues_survive_the_wire() -> None:
    mapped = body_for(AccountLockedError("locked", "2026-10-11T10:00:00.000000Z"))
    assert mapped is not None
    status, body = mapped
    assert status == 423 and body.locked_until == "2026-10-11T10:00:00.000000Z"
    rebuilt = exception_for(status, body.model_dump(exclude_none=True))
    assert isinstance(rebuilt, AccountLockedError)
    assert rebuilt.locked_until == "2026-10-11T10:00:00.000000Z"

    weak = body_for(WeakPasswordError("weak", ["must be at least 12 characters"]))
    assert weak is not None
    again = exception_for(weak[0], weak[1].model_dump(exclude_none=True))
    assert isinstance(again, WeakPasswordError) and again.issues == [
        "must be at least 12 characters"
    ]
    assert isinstance(exception_for(403, {"error": "forbidden", "message": "no"}), ForbiddenError)
