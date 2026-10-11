"""`/admin/*`: accounts, roles, passwords and agent tokens, admin only (ADR-0009, P1-I0-T04)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password

PASSWORD = "correct horse battery"
OTHER = "another long passphrase"
WRONG = "this is not the password"


class Cast:
    """An admin (boss), a user (bob) and an agent (triage) with a token, on the harness ledger."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        with harness.backend() as uow:
            self.boss = self._person(uow, "boss", ["admin"])
            self.bob = self._person(uow, "bob", ["user"])
            bot = accounts.create_account(
                uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
            self.bot = bot.account_id
            _, self.agent_token = accounts.issue_agent_token(
                uow,
                account_id=bot.account_id,
                label="t",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                by="svc:test",
            )

    @staticmethod
    def _person(uow: Any, name: str, roles: list[str]) -> str:
        view = accounts.create_account(
            uow, username=name, display_name=name.title(), kind="person", roles=roles,
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip
        return view.account_id

    @property
    def client(self) -> TestClient:
        return self.harness.client_for(None)

    def bearer(self, username: str) -> dict[str, str]:
        _, token = sessions.sign_in(self.harness.backend, username=username, password=PASSWORD)
        return {"Authorization": f"Bearer {token}"}

    @property
    def admin(self) -> dict[str, str]:
        return self.bearer("boss")

    def events(self) -> list[tuple[str, str, str]]:
        with self.harness.backend(True) as uow:
            rows = uow.conn().exec_driver_sql("SELECT event_type, actor, payload FROM events").all()
        return [(str(a), str(b), str(c)) for a, b, c in rows]


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    """These tests run on every adapter (`just test-parity`): the ledger is the parity `db`."""
    return parity_harness


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def admin_routes(cast: Cast) -> list[tuple[str, str]]:
    paths = cast.client.get("/openapi.json", headers=cast.admin).json()["paths"]
    return [
        (method.upper(), path.replace("{account_id}", cast.bob).replace("{token_id}", "x"))
        for path, operations in paths.items()
        if path.startswith("/admin/")
        for method in operations
    ]


def test_every_admin_route_refuses_everyone_who_is_not_an_admin(cast: Cast) -> None:
    routes = admin_routes(cast)
    assert len(routes) >= 10
    credentials = {
        "user": cast.bearer("bob"),
        "agent": {"Authorization": f"Bearer {cast.agent_token}"},
        "dev token": cast.harness.headers("user:alice"),
    }
    for label, headers in credentials.items():
        for method, path in routes:
            response = cast.client.request(method, path, json={}, headers=headers)
            assert response.status_code == 403, (label, method, path)
            assert response.json()["error"] == "forbidden", (label, method, path)
    for method, path in routes:
        assert cast.client.request(method, path, json={}).status_code == 401, (method, path)


def test_listing_shows_every_account_and_no_secret(cast: Cast) -> None:
    response = cast.client.get("/admin/accounts", headers=cast.admin)
    assert response.status_code == 200
    rows = response.json()
    assert [r["username"] for r in rows] == ["boss", "bob", "triage"]
    assert rows[0]["roles"] == ["admin"] and rows[2]["kind"] == "agent"
    assert all(r["locked_until"] is None for r in rows)
    assert "scrypt" not in response.text and PASSWORD not in response.text


def test_a_lock_shows_in_the_listing_and_a_reset_clears_it(cast: Cast) -> None:
    for _ in range(5):
        cast.client.post("/auth/sign-in", json={"username": "bob", "password": WRONG})
    listed = cast.client.get(f"/admin/accounts/{cast.bob}", headers=cast.admin).json()
    assert listed["locked_until"] is not None
    reset = cast.client.post(
        f"/admin/accounts/{cast.bob}/password", json={"new_password": OTHER}, headers=cast.admin
    )
    assert reset.status_code == 200 and reset.json()["locked_until"] is None
    signed = cast.client.post("/auth/sign-in", json={"username": "bob", "password": OTHER})
    assert signed.status_code == 200


def test_get_one_account_and_the_404(cast: Cast) -> None:
    assert (
        cast.client.get(f"/admin/accounts/{cast.bob}", headers=cast.admin).json()["username"]
        == "bob"
    )
    missing = cast.client.get("/admin/accounts/nope", headers=cast.admin)
    assert missing.status_code == 404 and missing.json()["error"] == "account_not_found"


def test_creating_an_account_gives_201_and_the_person_can_sign_in(cast: Cast) -> None:
    body = {
        "username": "Carol",
        "display_name": "Carol C",
        "kind": "person",
        "roles": ["user"],
        "password": OTHER,
    }
    created = cast.client.post("/admin/accounts", json=body, headers=cast.admin)
    assert created.status_code == 201
    view = created.json()
    assert view["username"] == "carol" and view["roles"] == ["user"] and view["status"] == "active"
    assert OTHER not in created.text
    signed = cast.client.post("/auth/sign-in", json={"username": "carol", "password": OTHER})
    assert signed.status_code == 200


def test_create_defaults_to_a_person_with_the_user_role_and_no_password(cast: Cast) -> None:
    body = {"username": "dave", "display_name": "Dave"}
    view = cast.client.post("/admin/accounts", json=body, headers=cast.admin).json()
    assert (view["kind"], view["roles"]) == ("person", ["user"])
    refused = cast.client.post(
        "/auth/sign-in", json={"username": "dave", "password": OTHER}
    )  # no password was set
    assert refused.status_code == 401


@pytest.mark.parametrize(
    ("payload", "status", "error"),
    [
        ({"username": "BOB", "display_name": "x", "password": OTHER}, 409, "username_taken"),
        ({"username": "triage", "display_name": "x"}, 409, "username_taken"),
        ({"username": "eve", "display_name": "x", "password": "short"}, 422, "weak_password"),
        ({"username": "a b", "display_name": "x"}, 422, "invalid_account"),
        (
            {"username": "bot", "display_name": "x", "kind": "agent", "password": OTHER},
            422,
            "invalid_account",
        ),
        (
            {"username": "bot", "display_name": "x", "kind": "agent", "roles": ["admin"]},
            422,
            "invalid_account",
        ),
        ({"username": "eve", "display_name": "x", "roles": []}, 422, "validation_error"),
        ({"username": "eve", "display_name": "x", "roles": ["root"]}, 422, "validation_error"),
        ({"username": "eve", "display_name": "x", "extra": 1}, 422, "validation_error"),
        ({"display_name": "x"}, 422, "validation_error"),
    ],
)
def test_refused_creates_leave_no_trace(
    cast: Cast, payload: dict[str, Any], status: int, error: str
) -> None:
    before = len(cast.events())
    response = cast.client.post("/admin/accounts", json=payload, headers=cast.admin)
    assert response.status_code == status and response.json()["error"] == error
    assert OTHER not in response.text
    assert len(cast.events()) == before


def test_roles_change_and_a_live_session_sees_it_at_once(cast: Cast) -> None:
    bob = cast.bearer("bob")
    assert cast.client.get("/auth/me", headers=bob).json()["roles"] == ["user"]
    changed = cast.client.put(
        f"/admin/accounts/{cast.bob}/roles",
        json={"roles": ["admin", "user"], "reason": "cover"},
        headers=cast.admin,
    )
    assert changed.status_code == 200 and changed.json()["roles"] == ["admin", "user"]
    assert cast.client.get("/auth/me", headers=bob).json()["roles"] == ["admin", "user"]
    assert cast.client.get("/admin/accounts", headers=bob).status_code == 200


def test_the_last_admin_cannot_be_demoted_or_disabled(cast: Cast) -> None:
    demote = cast.client.put(
        f"/admin/accounts/{cast.boss}/roles", json={"roles": ["user"]}, headers=cast.admin
    )
    assert demote.status_code == 409 and demote.json()["error"] == "last_admin"
    disable = cast.client.post(f"/admin/accounts/{cast.boss}/disable", json={}, headers=cast.admin)
    assert disable.status_code == 409 and disable.json()["error"] == "last_admin"


def test_setting_the_same_roles_is_a_409_account_state(cast: Cast) -> None:
    again = cast.client.put(
        f"/admin/accounts/{cast.bob}/roles", json={"roles": ["user"]}, headers=cast.admin
    )
    assert again.status_code == 409 and again.json()["error"] == "account_state"


def test_disable_ends_sessions_and_enable_brings_the_account_back(cast: Cast) -> None:
    bob = cast.bearer("bob")
    off = cast.client.post(
        f"/admin/accounts/{cast.bob}/disable", json={"reason": "left"}, headers=cast.admin
    )
    assert off.status_code == 200 and off.json()["status"] == "disabled"
    assert cast.client.get("/auth/me", headers=bob).status_code == 401
    sign_in = {"username": "bob", "password": PASSWORD}
    assert cast.client.post("/auth/sign-in", json=sign_in).json()["error"] == "account_disabled"
    twice = cast.client.post(f"/admin/accounts/{cast.bob}/disable", json={}, headers=cast.admin)
    assert twice.status_code == 409 and twice.json()["error"] == "account_state"
    on = cast.client.post(f"/admin/accounts/{cast.bob}/enable", json={}, headers=cast.admin)
    assert on.status_code == 200 and on.json()["status"] == "active"
    assert cast.client.post("/auth/sign-in", json=sign_in).status_code == 200
    again = cast.client.post(f"/admin/accounts/{cast.bob}/enable", json={}, headers=cast.admin)
    assert again.status_code == 409


def test_unknown_accounts_are_404_on_every_account_route(cast: Cast) -> None:
    calls = [
        ("PUT", "roles", {"roles": ["user"]}),
        ("POST", "disable", {}),
        ("POST", "enable", {}),
        ("POST", "password", {"new_password": OTHER}),
    ]
    for method, tail, body in calls:
        response = cast.client.request(
            method, f"/admin/accounts/nope/{tail}", json=body, headers=cast.admin
        )
        assert response.status_code == 404, tail
        assert response.json()["error"] == "account_not_found"


def test_a_reset_ends_sessions_takes_effect_and_must_meet_the_policy(cast: Cast) -> None:
    bob = cast.bearer("bob")
    weak = cast.client.post(
        f"/admin/accounts/{cast.bob}/password", json={"new_password": "short"}, headers=cast.admin
    )
    assert weak.status_code == 422 and weak.json()["error"] == "weak_password"
    assert cast.client.get("/auth/me", headers=bob).status_code == 200  # nothing changed
    done = cast.client.post(
        f"/admin/accounts/{cast.bob}/password", json={"new_password": OTHER}, headers=cast.admin
    )
    assert done.status_code == 200 and OTHER not in done.text
    assert cast.client.get("/auth/me", headers=bob).status_code == 401
    old = {"username": "bob", "password": PASSWORD}
    assert cast.client.post("/auth/sign-in", json=old).status_code == 401


def test_an_agent_account_cannot_be_given_a_password(cast: Cast) -> None:
    response = cast.client.post(
        f"/admin/accounts/{cast.bot}/password", json={"new_password": OTHER}, headers=cast.admin
    )
    assert response.status_code == 422 and response.json()["error"] == "invalid_account"


def test_issuing_a_token_shows_it_once_and_the_agent_can_use_it(cast: Cast) -> None:
    issued = cast.client.post(
        "/admin/tokens",
        json={"account_id": cast.bot, "label": "triage assistant"},
        headers=cast.admin,
    )
    assert issued.status_code == 201
    body = issued.json()
    token = body["token"]
    assert token.startswith("tla_") and body["view"]["label"] == "triage assistant"
    assert body["view"]["revoked"] is False and body["view"]["issued_by"] == "user:boss"
    expires = datetime.fromisoformat(body["view"]["expires_at"])
    assert timedelta(days=89) < expires - datetime.now(UTC) < timedelta(days=91)  # the default
    me = cast.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert (me["actor"], me["via"]) == ("agent:triage", "agent_token")
    listed = cast.client.get("/admin/tokens", headers=cast.admin)
    assert token not in listed.text and body["view"]["token_id"] in listed.text
    assert token not in json.dumps(cast.events())


def test_a_token_can_be_issued_without_an_expiry_or_with_a_short_one(cast: Cast) -> None:
    never = cast.client.post(
        "/admin/tokens",
        json={"account_id": cast.bot, "label": "n", "expires_in_days": None},
        headers=cast.admin,
    )
    assert never.json()["view"]["expires_at"] is None
    short = cast.client.post(
        "/admin/tokens",
        json={"account_id": cast.bot, "label": "s", "expires_in_days": 1},
        headers=cast.admin,
    )
    expires = datetime.fromisoformat(short.json()["view"]["expires_at"])
    assert timedelta(hours=23) < expires - datetime.now(UTC) < timedelta(hours=25)


@pytest.mark.parametrize(
    ("payload", "status", "error"),
    [
        ({"label": "x"}, 422, "validation_error"),
        ({"account_id": "bob", "label": ""}, 422, "validation_error"),
        ({"account_id": "bot", "label": "x", "expires_in_days": 0}, 422, "validation_error"),
        ({"account_id": "bot", "label": "x", "expires_in_days": 99999}, 422, "validation_error"),
        ({"account_id": "BOB", "label": "x"}, 422, "invalid_account"),  # a person: no tokens
        ({"account_id": "nope", "label": "x"}, 404, "account_not_found"),
    ],
)
def test_refused_token_requests(
    cast: Cast, payload: dict[str, Any], status: int, error: str
) -> None:
    payload = {
        k: (cast.bob if v == "BOB" else cast.bot if v == "bot" else v) for k, v in payload.items()
    }
    response = cast.client.post("/admin/tokens", json=payload, headers=cast.admin)
    assert response.status_code == status and response.json()["error"] == error


def test_listing_tokens_filters_by_account_and_revocation(cast: Cast) -> None:
    other = cast.client.post(
        "/admin/accounts", json={"username": "second", "display_name": "S", "kind": "agent"},
        headers=cast.admin,
    ).json()["account_id"]  # fmt: skip
    cast.client.post("/admin/tokens", json={"account_id": other, "label": "o"}, headers=cast.admin)
    everything = cast.client.get("/admin/tokens", headers=cast.admin).json()
    assert len(everything) == 2
    mine = cast.client.get("/admin/tokens", params={"account_id": cast.bot}, headers=cast.admin)
    assert [t["account_id"] for t in mine.json()] == [cast.bot]
    first = mine.json()[0]["token_id"]
    cast.client.post(f"/admin/tokens/{first}/revoke", json={}, headers=cast.admin)
    live = cast.client.get("/admin/tokens", params={"include_revoked": False}, headers=cast.admin)
    assert [t["account_id"] for t in live.json()] == [other]
    assert len(cast.client.get("/admin/tokens", headers=cast.admin).json()) == 2


def test_revoking_a_token_stops_it_at_once_and_only_once(cast: Cast) -> None:
    token_id = cast.client.get("/admin/tokens", headers=cast.admin).json()[0]["token_id"]
    agent = {"Authorization": f"Bearer {cast.agent_token}"}
    assert cast.client.get("/auth/me", headers=agent).status_code == 200
    revoked = cast.client.post(
        f"/admin/tokens/{token_id}/revoke", json={"reason": "rotated"}, headers=cast.admin
    )
    assert revoked.status_code == 200 and revoked.json()["revoked"] is True
    assert cast.client.get("/auth/me", headers=agent).status_code == 401
    twice = cast.client.post(f"/admin/tokens/{token_id}/revoke", json={}, headers=cast.admin)
    assert twice.status_code == 409 and twice.json()["error"] == "account_state"
    gone = cast.client.post("/admin/tokens/nope/revoke", json={}, headers=cast.admin)
    assert gone.status_code == 404 and gone.json()["error"] == "agent_token_not_found"


def test_the_ledger_records_who_did_what_and_holds_no_secret(cast: Cast) -> None:
    cast.client.post(
        "/admin/accounts",
        json={"username": "carol", "display_name": "C", "password": OTHER},
        headers=cast.admin,
    )
    cast.client.post(
        f"/admin/accounts/{cast.bob}/password", json={"new_password": OTHER}, headers=cast.admin
    )
    issued = cast.client.post(
        "/admin/tokens", json={"account_id": cast.bot, "label": "x"}, headers=cast.admin
    ).json()
    events = [e for e in cast.events() if e[1] == "user:boss"]
    assert {e[0] for e in events} >= {
        "Account.Created",
        "Account.PasswordChanged",
        "AgentToken.Issued",
    }
    everything = json.dumps(cast.events())
    for secret in (OTHER, PASSWORD, issued["token"], "scrypt$"):
        assert secret not in everything


def test_a_weak_password_is_not_echoed_in_the_error(cast: Cast) -> None:
    refused = cast.client.post(
        "/admin/accounts",
        json={"username": "eve", "display_name": "E", "password": "short"},
        headers=cast.admin,
    )
    assert "short" not in refused.json()["message"]


def test_a_password_with_a_nul_is_a_422_weak_password(cast: Cast) -> None:
    bad = "a\x00b" * 6
    # json.dumps escapes the NUL; the service refuses it before any query
    wire = {**cast.admin, "content-type": "application/json"}
    created = cast.client.post(
        "/admin/accounts",
        content=json.dumps({"username": "eve", "display_name": "E", "password": bad}),
        headers=wire,
    )
    assert created.status_code == 422 and created.json()["error"] == "weak_password"
    reset = cast.client.post(
        f"/admin/accounts/{cast.bob}/password",
        content=json.dumps({"new_password": bad}),
        headers=wire,
    )
    assert reset.status_code == 422 and reset.json()["error"] == "weak_password"
    sign_in = {"username": "bob", "password": PASSWORD}
    assert cast.client.post("/auth/sign-in", json=sign_in).status_code == 200  # nothing changed


def test_a_lone_surrogate_in_a_password_is_refused_by_the_body_parser(cast: Cast) -> None:
    wire = {**cast.admin, "content-type": "application/json"}
    body = json.dumps({"username": "eve", "display_name": "E", "password": "\ud800" * 12})
    refused = cast.client.post("/admin/accounts", content=body, headers=wire)
    assert refused.status_code == 422 and "ud800" not in refused.text
    assert cast.client.get("/admin/accounts", headers=cast.admin).status_code == 200


def test_the_username_is_part_of_the_policy_on_create_and_on_reset(cast: Cast) -> None:
    name = "carolina.smith"  # long enough that the password rules alone would accept it
    created = cast.client.post(
        "/admin/accounts",
        json={"username": name, "display_name": "C", "password": name},
        headers=cast.admin,
    )
    assert created.status_code == 422 and created.json()["error"] == "weak_password"
    assert any("username" in issue for issue in created.json()["issues"])
    made = cast.client.post(
        "/admin/accounts", json={"username": name, "display_name": "C"}, headers=cast.admin
    )
    reset = cast.client.post(
        f"/admin/accounts/{made.json()['account_id']}/password",
        json={"new_password": name.upper()},
        headers=cast.admin,
    )
    assert reset.status_code == 422 and reset.json()["error"] == "weak_password"


class WriteWatch:
    """A backend that counts the write transactions open right now and delegates the rest."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.open_writes = 0
        self.hashes = 0

    @property
    def ledger(self) -> Any:
        return self.inner.ledger

    @property
    def bus(self) -> Any:
        return self.inner.bus

    def close(self) -> None:
        return None

    def __call__(self, readonly: bool = False) -> Any:
        watch = self

        class Tracked:
            def __enter__(self) -> Any:
                self.cm = watch.inner(readonly)
                if not readonly:
                    watch.open_writes += 1
                return self.cm.__enter__()

            def __exit__(self, *exc: Any) -> Any:
                try:
                    return self.cm.__exit__(*exc)
                finally:
                    if not readonly:
                        watch.open_writes -= 1

        return Tracked()


def test_no_password_is_hashed_while_a_write_transaction_is_open(
    cast: Cast, harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hash is slow and the writer lock is global: hash first (`prepare_password`), then write."""
    from tl_api.app import create_app
    from tl_core.auth import password as pw

    watch = WriteWatch(harness.backend)
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]

    def checking(password: str, salt: bytes, params: Any) -> bytes:
        assert watch.open_writes == 0, "a password was hashed inside a write transaction"
        watch.hashes += 1
        return real(password, salt, params)

    monkeypatch.setattr(pw, "_scrypt", checking)
    app = create_app(watch, settings=harness.settings)  # type: ignore[arg-type]
    client = TestClient(app, raise_server_exceptions=False)
    created = client.post(
        "/admin/accounts",
        json={"username": "dave", "display_name": "D", "password": OTHER},
        headers=cast.admin,
    )
    assert created.status_code == 201
    reset = client.post(
        f"/admin/accounts/{cast.bob}/password", json={"new_password": OTHER}, headers=cast.admin
    )
    assert reset.status_code == 200
    assert watch.hashes >= 2
