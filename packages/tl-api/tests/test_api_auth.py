"""`/auth/*`: sign in, sign out, who am I, change your own password (ADR-0009, P1-I0-T03)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.auth.queries import list_accounts

PASSWORD = "correct horse battery"
OTHER = "another long passphrase"
WRONG = "this is not the password"


class People:
    """Three accounts on the harness ledger: an admin, a user and an agent with a token."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        with harness.backend() as uow:
            for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
                accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="person", roles=roles,
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
            bot = accounts.create_account(
                uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
            _, self.agent_token = accounts.issue_agent_token(
                uow,
                account_id=bot.account_id,
                label="t",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                by="svc:test",
            )

    @property
    def client(self) -> TestClient:
        """A client that sends no Authorization header."""
        return self.harness.client_for(None)

    def sign_in(self, username: str, password: str = PASSWORD) -> Any:
        return self.client.post("/auth/sign-in", json={"username": username, "password": password})

    def bearer(self, username: str) -> dict[str, str]:
        token = self.sign_in(username).json()["token"]
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def people(harness: Harness) -> People:
    return People(harness)


def test_signing_in_answers_a_session_token_and_the_principal(people: People) -> None:
    response = people.sign_in("Bob")
    assert response.status_code == 200
    body = response.json()
    assert body["token"].startswith("tls_") and body["token_type"] == "bearer"
    assert body["expires_in"] == 12 * 3600
    principal = body["principal"]
    assert principal["actor"] == "user:bob" and principal["kind"] == "person"
    assert principal["roles"] == ["user"] and principal["via"] == "session"
    assert PASSWORD not in response.text and "scrypt" not in response.text


def test_the_token_is_a_bearer_token_for_the_rest_of_the_api(people: People) -> None:
    headers = people.bearer("bob")
    assert people.client.get("/events", headers=headers).status_code == 200
    me = people.client.get("/auth/me", headers=headers).json()
    assert me["actor"] == "user:bob" and me["via"] == "session"


def test_sign_in_needs_no_token_and_nothing_else_does(people: People) -> None:
    assert people.sign_in("bob").status_code == 200
    assert people.client.post("/auth/sign-out").status_code == 401
    assert people.client.get("/auth/me").status_code == 401
    assert people.client.post("/auth/password", json={}).status_code == 401


def test_an_unknown_user_and_a_wrong_password_look_the_same(people: People) -> None:
    wrong = people.sign_in("bob", WRONG)
    unknown = people.sign_in("nobody", WRONG)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"] == "invalid_credentials"
    assert WRONG not in wrong.text


def test_an_agent_account_cannot_sign_in(people: People) -> None:
    assert people.sign_in("triage", PASSWORD).json()["error"] == "invalid_credentials"


def test_repeated_failures_lock_the_name_even_for_the_right_password(people: People) -> None:
    for _ in range(5):
        assert people.sign_in("bob", WRONG).status_code == 401
    locked = people.sign_in("bob", PASSWORD)
    assert locked.status_code == 423
    body = locked.json()
    assert body["error"] == "account_locked" and body["locked_until"].endswith("Z")
    assert people.sign_in("ghost", WRONG).status_code == 401  # a different name is unaffected
    for _ in range(4):
        people.sign_in("ghost", WRONG)
    assert people.sign_in("ghost", WRONG).status_code == 423  # and an unknown name locks too


def test_a_disabled_account_is_reported_only_for_the_right_password(people: People) -> None:
    with people.harness.backend() as uow:
        bob = next(a for a in list_accounts(uow.conn()) if a.username == "bob")
        accounts.disable(uow, account_id=bob.account_id, by="user:boss", reason="left")
    assert people.sign_in("bob", WRONG).json()["error"] == "invalid_credentials"
    refused = people.sign_in("bob", PASSWORD)
    assert refused.status_code == 403 and refused.json()["error"] == "account_disabled"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"username": "bob"},
        {"password": PASSWORD},
        {"username": "", "password": PASSWORD},
        {"username": "bob", "password": ""},
        {"username": "bob", "password": PASSWORD, "extra": 1},
        {"username": "bob", "password": "x" * 2000},
        {"username": 7, "password": PASSWORD},
    ],
)
def test_a_malformed_sign_in_body_is_a_422_that_does_not_echo_the_password(
    people: People, payload: dict[str, Any]
) -> None:
    response = people.client.post("/auth/sign-in", json=payload)
    assert response.status_code == 422 and response.json()["error"] == "validation_error"
    assert PASSWORD not in response.text


def test_sign_in_is_post_only(people: People) -> None:
    assert people.client.get("/auth/sign-in").status_code == 405


def test_no_password_or_token_reaches_the_log(
    people: People, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    token = people.sign_in("bob").json()["token"]
    people.sign_in("bob", WRONG)
    people.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    people.client.post("/auth/sign-out", headers={"Authorization": f"Bearer {token}"})
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert PASSWORD not in text and WRONG not in text and token not in text


def test_sign_out_ends_that_session_only(people: People) -> None:
    first, second = people.bearer("bob"), people.bearer("bob")
    out = people.client.post("/auth/sign-out", headers=first)
    assert out.status_code == 204 and out.content == b""
    assert people.client.get("/auth/me", headers=first).status_code == 401
    assert people.client.get("/auth/me", headers=second).status_code == 200
    assert people.client.post("/auth/sign-out", headers=first).status_code == 401


def test_sign_out_with_an_agent_or_dev_token_changes_nothing(people: People) -> None:
    agent = {"Authorization": f"Bearer {people.agent_token}"}
    assert people.client.post("/auth/sign-out", headers=agent).status_code == 204
    assert people.client.get("/auth/me", headers=agent).status_code == 200
    dev = people.harness.headers("user:alice")
    assert people.client.post("/auth/sign-out", headers=dev).status_code == 204
    assert people.client.get("/auth/me", headers=dev).status_code == 200


def test_me_says_who_you_are_for_every_kind_of_token(people: People) -> None:
    session = people.client.get("/auth/me", headers=people.bearer("boss")).json()
    assert (session["actor"], session["roles"], session["via"]) == (
        "user:boss",
        ["admin"],
        "session",
    )
    agent = people.client.get(
        "/auth/me", headers={"Authorization": f"Bearer {people.agent_token}"}
    ).json()
    assert (agent["actor"], agent["kind"], agent["via"]) == ("agent:triage", "agent", "agent_token")
    dev = people.client.get("/auth/me", headers=people.harness.headers("user:alice")).json()
    assert (dev["actor"], dev["roles"], dev["via"]) == ("user:alice", ["user"], "dev_token")


def test_changing_your_password_ends_every_session_and_sets_the_new_one(people: People) -> None:
    mine, other = people.bearer("bob"), people.bearer("bob")
    body = {"current_password": PASSWORD, "new_password": OTHER}
    changed = people.client.post("/auth/password", json=body, headers=mine)
    assert changed.status_code == 204
    for headers in (mine, other):
        assert people.client.get("/auth/me", headers=headers).status_code == 401
    assert people.sign_in("bob", PASSWORD).status_code == 401
    assert people.sign_in("bob", OTHER).status_code == 200


def test_a_wrong_current_password_is_refused_and_counts_towards_lockout(people: People) -> None:
    headers = people.bearer("bob")
    body = {"current_password": WRONG, "new_password": OTHER}
    for _ in range(5):
        refused = people.client.post("/auth/password", json=body, headers=headers)
        assert refused.status_code == 401 and refused.json()["error"] == "invalid_credentials"
        assert WRONG not in refused.text
    assert people.sign_in("bob", PASSWORD).status_code == 423


def test_a_weak_new_password_is_a_422_that_names_the_rule(people: People) -> None:
    headers = people.bearer("bob")
    body = {"current_password": PASSWORD, "new_password": "short"}
    refused = people.client.post("/auth/password", json=body, headers=headers)
    assert refused.status_code == 422 and refused.json()["error"] == "weak_password"
    assert any("12" in issue for issue in refused.json()["issues"])
    assert "short" not in refused.json()["message"]
    assert people.sign_in("bob", PASSWORD).status_code == 200  # nothing changed


def test_agents_and_dev_tokens_have_no_password_to_change(people: People) -> None:
    body = {"current_password": PASSWORD, "new_password": OTHER}
    agent = {"Authorization": f"Bearer {people.agent_token}"}
    for headers in (agent, people.harness.headers("user:alice")):
        refused = people.client.post("/auth/password", json=body, headers=headers)
        assert refused.status_code == 403 and refused.json()["error"] == "forbidden"


def test_the_routes_are_in_the_openapi_document(people: People) -> None:
    paths = people.client.get("/openapi.json", headers=people.bearer("bob")).json()["paths"]
    assert {"/auth/sign-in", "/auth/sign-out", "/auth/me", "/auth/password"} <= set(paths)
    assert paths["/auth/sign-out"]["post"]["responses"]["204"]


def wire(body: dict[str, Any]) -> dict[str, Any]:
    """Send ``body`` through ``json.dumps``, which escapes a lone surrogate as \\ud800.

    The test client's own JSON encoder refuses a lone surrogate before it reaches the server.
    """
    return {"content": json.dumps(body), "headers": {"content-type": "application/json"}}


def test_a_nul_in_the_credentials_is_a_plain_401_and_the_server_stays_healthy(
    people: People,
) -> None:
    """A NUL breaks a Postgres parameter; it must never reach a query."""
    for body in (
        {"username": "a\x00b", "password": PASSWORD},
        {"username": "bob", "password": "a\x00b"},
        {"username": "a\x00b", "password": "a\x00b"},
    ):
        refused = people.client.post("/auth/sign-in", **wire(body))
        assert refused.status_code == 401 and refused.json()["error"] == "invalid_credentials"
    assert people.sign_in("bob").status_code == 200  # the connection is intact


@pytest.mark.parametrize("bad", ["\ud800", "ali\udfffce"])
def test_a_lone_surrogate_is_refused_without_echo_and_the_server_stays_healthy(
    people: People, bad: str
) -> None:
    """JSON allows the escape; the body parser refuses it (422) or the service does (401)."""
    for body in (
        {"username": bad, "password": PASSWORD},
        {"username": "bob", "password": bad},
    ):
        refused = people.client.post("/auth/sign-in", **wire(body))
        assert refused.status_code in (401, 422)
        assert refused.json()["error"] in ("invalid_credentials", "validation_error")
        assert PASSWORD not in refused.text
    assert people.sign_in("bob").status_code == 200  # the connection is intact


def test_usernames_are_not_stripped_or_trimmed(people: People) -> None:
    for variant in (" bob", "bob ", "\tbob", "bob\n"):
        refused = people.sign_in(variant)
        assert refused.status_code == 401 and refused.json()["error"] == "invalid_credentials"


def test_a_body_over_16_kib_is_413_before_anything_reads_it(people: People) -> None:
    body = {"username": "bob", "password": "x" * 20_000}
    refused = people.client.post("/auth/sign-in", json=body)
    assert refused.status_code == 413 and refused.json()["error"] == "payload_too_large"
    assert "x" * 50 not in refused.text


def test_a_busy_hash_gate_answers_503_with_retry_after(
    people: People, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_core.auth import password as pw

    headers = people.bearer("bob")
    monkeypatch.setattr(pw, "GATE_TIMEOUT_S", 0.05)
    taken = [pw._gate.acquire() for _ in range(pw.MAX_CONCURRENT_HASHES)]  # pyright: ignore[reportPrivateUsage]
    try:
        body = {"current_password": PASSWORD, "new_password": OTHER}
        busy = people.client.post("/auth/password", json=body, headers=headers)
        signing_in = people.sign_in("bob")
    finally:
        for _ in taken:
            pw._gate.release()  # pyright: ignore[reportPrivateUsage]
    for response in (busy, signing_in):
        assert response.status_code == 503 and response.json()["error"] == "auth_busy"
        assert response.headers["retry-after"] == "2"
    assert people.sign_in("bob").status_code == 200  # and it recovers
