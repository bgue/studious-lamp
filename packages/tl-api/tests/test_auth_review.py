"""Fixes from the D6 security review at the HTTP edge: streams, hidden events, limits, startup."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx2
import pytest
import uvicorn
from fastapi import Depends
from fastapi.testclient import TestClient
from harness import Harness
from starlette.types import ASGIApp, Receive, Scope, Send
from tl_api.app import create_app
from tl_api.auth import PRINCIPAL_KEY, current_principal, guard
from tl_api.startup import StartupRefused, check_demo_account
from tl_api.tokens import TokenStore
from tl_core.auth import accounts, seed, sessions
from tl_core.auth import password as pw
from tl_core.auth.password import prepare_password
from tl_core.auth.provider import RoleAuthorizer
from tl_core.auth.types import Principal

PASSWORD = "correct horse battery"


class Cast:
    def __init__(self, harness: Harness) -> None:
        self.h = harness
        with harness.backend() as uow:
            for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
                accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="person", roles=roles,
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
            bot = accounts.create_account(
                uow, username="triage", display_name="T", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
            self.bot = bot.account_id
            self.view, self.agent_token = accounts.issue_agent_token(
                uow,
                account_id=bot.account_id,
                label="t",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                by="svc:test",
            )

    def session(self, name: str) -> str:
        return sessions.sign_in(self.h.backend, username=name, password=PASSWORD)[1]


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def app_with(harness: Harness, **settings: Any) -> Any:
    app = create_app(
        harness.backend,
        settings=replace(harness.settings, **settings),
        tokens=TokenStore(harness.settings.tokens_path),
    )

    @app.get("/_t/me")
    def me(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        return principal

    @app.post("/auth/echo")  # stands in for a route that reads its body, under the /auth/ limit
    def echo(body: dict[str, Any]) -> dict[str, int]:
        return {"keys": len(body)}

    @app.get("/_t/hash")
    def hashing(actor: Annotated[str, Depends(guard("record.read"))]) -> dict[str, str]:
        return {"hash": pw.prepare_password("another long passphrase").hash[:6]}

    return app


@contextmanager
def serve(app: Any) -> Iterator[str]:
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="warning", timeout_graceful_shutdown=1
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the test server did not start"
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def stream_lines(
    base: str, token: str, seconds: float, params: dict[str, Any] | None = None
) -> str:
    """Everything an open stream sends until it ends, or until ``seconds`` have passed."""
    text = ""
    deadline = time.monotonic() + seconds
    with httpx2.Client(base_url=base, timeout=httpx2.Timeout(seconds + 2)) as client:
        with client.stream("GET", "/stream", headers=bearer(token), params=params) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                text += line + "\n"
                if "event: closed" in text and line == "" or time.monotonic() > deadline:
                    break
    return text


# --- item 4: an open stream stops when its token stops ---------------------------------------


def test_a_stream_ends_when_the_session_is_signed_out(harness: Harness, cast: Cast) -> None:
    token = cast.session("bob")
    app = app_with(harness, sse_recheck_s=0.2, sse_wait_s=0.1)
    with serve(app) as base:
        threading.Timer(
            0.5, sessions.sign_out, args=(harness.backend,), kwargs={"token": token}
        ).start()
        seen = stream_lines(base, token, 6.0)
    assert 'event: closed\ndata: {"reason": "unauthorized"}' in seen


def test_a_stream_ends_when_the_agent_token_is_revoked(harness: Harness, cast: Cast) -> None:
    app = app_with(harness, sse_recheck_s=0.2, sse_wait_s=0.1)

    def revoke() -> None:
        with harness.backend() as uow:
            accounts.revoke_agent_token(
                uow, token_id=cast.view.token_id, by="user:boss", reason="x"
            )

    with serve(app) as base:
        threading.Timer(0.5, revoke).start()
        seen = stream_lines(base, cast.agent_token, 6.0)
    assert '"reason": "unauthorized"' in seen


def test_a_stream_ends_when_the_account_is_disabled(harness: Harness, cast: Cast) -> None:
    token = cast.session("bob")
    app = app_with(harness, sse_recheck_s=0.2, sse_wait_s=0.1)

    def disable() -> None:
        with harness.backend() as uow:
            bob = [
                a
                for a in __import__("tl_core.auth.queries", fromlist=["x"]).list_accounts(
                    uow.conn()
                )
                if a.username == "bob"
            ][0]
            accounts.disable(uow, account_id=bob.account_id, by="user:boss", reason="x")

    with serve(app) as base:
        threading.Timer(0.5, disable).start()
        assert '"reason": "unauthorized"' in stream_lines(base, token, 6.0)


def test_no_stream_outlives_the_maximum_age(harness: Harness, cast: Cast) -> None:
    token = cast.session("bob")
    app = app_with(harness, sse_max_age_s=0.5, sse_wait_s=0.1, sse_recheck_s=60.0)
    with serve(app) as base:
        assert '"reason": "expired"' in stream_lines(base, token, 6.0)


def test_a_valid_stream_stays_open_past_the_recheck(harness: Harness, cast: Cast) -> None:
    token = cast.session("bob")
    app = app_with(harness, sse_recheck_s=0.2, sse_wait_s=0.1)
    with serve(app) as base:
        seen = stream_lines(base, token, 1.5)
    assert "closed" not in seen and ": connected" in seen


# --- item 5: account events are for admins ---------------------------------------------------


def event_types(client: TestClient, headers: dict[str, str]) -> set[str]:
    body = client.get("/events", headers=headers, params={"limit": 1000}).json()
    return {e["event_type"] for e in body["events"]}


def test_only_an_admin_sees_account_events_in_the_events_api(harness: Harness, cast: Cast) -> None:
    harness.create_record("R-1")
    client = harness.client_for(None)
    admin = event_types(client, bearer(cast.session("boss")))
    assert {"Account.Created", "AgentToken.Issued", "Record.Created"} <= admin
    for headers in (
        bearer(cast.session("bob")),
        bearer(cast.agent_token),
        harness.headers("user:alice"),
    ):
        seen = event_types(client, headers)
        assert "Record.Created" in seen
        assert not {t for t in seen if t.startswith(("Account.", "AgentToken."))}


def test_only_an_admin_sees_account_events_in_the_stream(harness: Harness, cast: Cast) -> None:
    harness.create_record("R-1")
    app = app_with(harness, sse_wait_s=0.1)
    with serve(app) as base:
        admin = stream_lines(base, cast.session("boss"), 1.5, {"after": 0})
        user = stream_lines(base, cast.session("bob"), 1.5, {"after": 0})
        agent = stream_lines(base, cast.agent_token, 1.5, {"after": 0})
    assert "event: Account.Created" in admin
    for seen in (user, agent):
        assert "event: Record.Created" in seen
        assert "Account." not in seen and "AgentToken." not in seen


def test_the_account_filter_hides_a_stream_type_before_anything_else() -> None:
    from tl_core.changefeed import SubscriptionFilter

    flt = SubscriptionFilter.of(hide_stream_types=["core.Account"], event_types=["*"])
    assert flt.hide_stream_types == frozenset({"core.Account"})


# --- item 6: limits ---------------------------------------------------------------------------


def test_oversized_bodies_on_auth_and_admin_routes_are_413(harness: Harness) -> None:
    client = harness.client_for(None)
    big = {"username": "bob", "password": "x" * 20_000}
    refused = client.post("/auth/sign-in", json=big)
    assert refused.status_code == 413 and refused.json()["error"] == "payload_too_large"
    assert "x" * 100 not in refused.text
    huge = client.post("/admin/accounts", content=b"{" + b" " * 70_000 + b"}")
    assert huge.status_code == 413  # before any token check: the limit is outermost


def test_a_chunked_body_over_the_limit_is_413_too(harness: Harness) -> None:
    app = app_with(harness)
    with serve(app) as base:

        def chunks() -> Iterator[bytes]:
            for _ in range(40):
                yield b" " * 1024

        response = httpx2.post(
            f"{base}/auth/echo",
            content=chunks(),
            headers={"content-type": "application/json", **harness.headers("user:alice")},
            timeout=5.0,
        )
    assert response.status_code == 413 and response.json()["error"] == "payload_too_large"
    ok = TestClient(app).post("/auth/echo", json={"a": 1}, headers=harness.headers("user:alice"))
    assert ok.status_code == 200 and ok.json() == {"keys": 1}


# --- item 3: a busy hash gate is a 503 with Retry-After ----------------------------------------


def test_a_busy_hash_gate_is_503_auth_busy_with_retry_after(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(app_with(harness), raise_server_exceptions=False)
    monkeypatch.setattr(pw, "GATE_TIMEOUT_S", 0.05)
    taken = [pw._gate.acquire() for _ in range(pw.MAX_CONCURRENT_HASHES)]  # pyright: ignore[reportPrivateUsage]
    try:
        busy = client.get("/_t/hash", headers=harness.headers("user:alice"))
    finally:
        for _ in taken:
            pw._gate.release()  # pyright: ignore[reportPrivateUsage]
    assert busy.status_code == 503 and busy.json()["error"] == "auth_busy"
    assert busy.headers["retry-after"] == "2"
    assert client.get("/_t/hash", headers=harness.headers("user:alice")).status_code == 200


# --- item 8: the principal key and the agent allow-list ----------------------------------------


def test_nothing_in_scope_state_can_stand_in_for_the_principal(
    harness: Harness, cast: Cast
) -> None:
    app = app_with(harness)

    class Inject:
        def __init__(self, inner: ASGIApp) -> None:
            self.inner = inner

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                admin = Principal(
                    actor="user:boss", account_id="x", kind="person", roles=["admin"], via="session"
                )
                scope["state"] = {"principal": admin}
                scope["principal"] = admin
            await self.inner(scope, receive, send)

    client = TestClient(Inject(app), raise_server_exceptions=False)
    token = cast.session("bob")
    me = client.get("/_t/me", headers=bearer(token)).json()
    assert me["actor"] == "user:bob" and me["roles"] == ["user"]
    assert PRINCIPAL_KEY not in {"state", "principal"}


def route_actions(app: Any) -> set[str]:
    found: set[str] = set()

    def walk(dependant: Any) -> None:
        action = getattr(dependant.call, "action", None)
        if action is not None:
            found.add(action)
        for sub in dependant.dependencies:
            walk(sub)

    def routes(container: Any) -> Iterator[Any]:
        for route in container:
            inner = getattr(route, "original_router", None)  # an included router
            if inner is not None:
                yield from routes(inner.routes)
            else:
                yield route

    for route in routes(app.routes):
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            walk(dependant)
    return found


#: Every non-command action a route may use, decided once. A route with an action in neither set
#: fails the test below: whoever adds it has to say whether an agent may call it.
AGENT_MAY = {
    "auth.me",
    "auth.sign_out",
    "events.read",
    "events.stream",
    "feed.read",
    "file.read",
    "link.read",
    "openapi.read",
    "proposal.read",
    "proposal.accept",  # the service answers proposal_decider
    "proposal.reject",
    "record.read",
    "reference.read",
    "setting.read",
    "standards.read",
    "tag.read",
    "type.read",
}
AGENT_MAY_NOT = {
    "auth.password",
    "file.upload",
    "record.write",
    "setting.write",
    "admin.accounts.list",
    "admin.accounts.create",
    "admin.accounts.roles",
    "admin.accounts.state",
    "admin.accounts.password",
    "admin.tokens.list",
    "admin.tokens.issue",
    "admin.tokens.revoke",
    # the engineering registry commands (P1-I1): one action per admin-only command
    "admin.command.RegisterCodeList",
    "admin.command.RegisterMnemonic",
    "admin.command.RegisterNumberingPattern",
    "admin.command.CloseStandard",
    "admin.command.DefineTagClass",
    "admin.command.ReviseTagClass",
    "admin.command.CloseTagClass",
}
FEED_COMMANDS = {"PostToFeed", "EditPost", "RetractPost", "ReactToPost"}


def test_every_route_action_is_decided_for_agents(harness: Harness) -> None:
    actions = route_actions(app_with(harness))
    commands = {a for a in actions if a.startswith("command.")}
    others = actions - commands
    undecided = others - AGENT_MAY - AGENT_MAY_NOT
    assert not undecided, f"decide for agents (these sets and AGENT_ACTIONS): {sorted(undecided)}"
    assert len(commands) >= 15 and len(others) >= 15  # the walk really found the routes
    for action in others:
        assert _agent_may(action) == (action in AGENT_MAY), action
    for action in commands:
        assert _agent_may(action) == (action.removeprefix("command.") in FEED_COMMANDS), action
    assert {f"command.{n}" for n in FEED_COMMANDS} <= commands


def test_the_walk_notices_a_new_undecided_action(harness: Harness) -> None:
    app = app_with(harness)

    @app.get("/_t/new")
    def new_route(actor: Annotated[str, Depends(guard("brand.new"))]) -> dict[str, str]:
        return {"actor": actor}

    undecided = (
        {a for a in route_actions(app) if not a.startswith("command.")} - AGENT_MAY - AGENT_MAY_NOT
    )
    assert undecided == {"brand.new"}
    assert not _agent_may("brand.new")


def _agent_may(action: str) -> bool:
    agent = Principal(
        actor="agent:x", account_id="a", kind="agent", roles=["user"], via="agent_token"
    )
    try:
        RoleAuthorizer().authorize(agent, action, "/x")
    except Exception:
        return False
    return True


def test_an_unknown_action_is_closed_to_agents_and_open_to_people() -> None:
    assert not _agent_may("brand.new.route")
    person = Principal(actor="user:x", account_id="a", kind="person", roles=["user"], via="session")
    RoleAuthorizer().authorize(person, "brand.new.route", "/x")


def test_an_agent_gets_agent_must_propose_before_the_authorizer_speaks(
    harness: Harness, cast: Cast
) -> None:
    client = TestClient(app_with(harness), raise_server_exceptions=False)
    refused = client.post(
        "/commands/CreateRecord",
        headers=bearer(cast.agent_token),
        json={"scope": "project:P123", "record_type": "core.Record", "title": "x", "key": "K-9"},
    )
    assert refused.json()["error"] == "agent_must_propose"
    denied = client.get("/settings", headers=bearer(cast.agent_token), params={"project": "P123"})
    assert denied.status_code in (200, 403, 422)


# --- item 2: the server will not start with an unsafe demo account -----------------------------


def make_demo(harness: Harness) -> None:
    assert seed.seed_demo(harness.backend, env="dev") is not None


def test_startup_is_quiet_without_a_demo_account(harness: Harness) -> None:
    assert check_demo_account(harness.backend, host="0.0.0.0", env={"TL_ENV": "prod"}) is False


def test_startup_warns_about_demo_on_loopback_in_dev(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    make_demo(harness)
    with caplog.at_level("WARNING", logger="tl_api"):
        assert check_demo_account(harness.backend, host="127.0.0.1", env={"TL_ENV": "dev"}) is True
    assert any("demo account" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("env", ["prod", "production", "", "ci", "staging"])
def test_startup_refuses_demo_when_the_environment_is_not_dev_demo_or_test(
    harness: Harness, env: str
) -> None:
    make_demo(harness)
    with pytest.raises(StartupRefused, match="disable"):
        check_demo_account(harness.backend, host="127.0.0.1", env={"TL_ENV": env})


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com", "::"])
def test_startup_refuses_demo_on_a_non_loopback_bind_even_in_dev(
    harness: Harness, host: str
) -> None:
    make_demo(harness)
    with pytest.raises(StartupRefused, match="demo"):
        check_demo_account(harness.backend, host=host, env={"TL_ENV": "dev"})


def test_startup_allows_a_disabled_demo_account_anywhere(harness: Harness) -> None:
    make_demo(harness)
    with harness.backend() as uow:
        demo = next(
            a
            for a in __import__("tl_core.auth.queries", fromlist=["x"]).list_accounts(uow.conn())
            if a.username == "demo"
        )
        accounts.create_account(
            uow, username="boss", display_name="B", kind="person", roles=["admin"],
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip
        accounts.disable(uow, account_id=demo.account_id, by="svc:test", reason="real use")
    assert check_demo_account(harness.backend, host="0.0.0.0", env={"TL_ENV": "prod"}) is False


def test_a_ledger_without_account_tables_says_to_run_init(tmp_path: Any) -> None:
    import sqlite3

    from tl_adapters.sqlite.factory import SqliteUowFactory

    path = tmp_path / "old.db"
    sqlite3.connect(path).close()
    backend = SqliteUowFactory(path)
    try:
        with pytest.raises(StartupRefused, match="tl init"):
            check_demo_account(backend, host="127.0.0.1", env={"TL_ENV": "dev"})
    finally:
        backend.close()


# --- the default filter fails closed (re-review item 5) ----------------------------------------


def test_a_filter_built_without_thinking_hides_account_events() -> None:
    from tl_core.changefeed import ANY, SubscriptionFilter
    from tl_core.changefeed.filters import INTERNAL_STREAM_TYPES
    from tl_core.ledger import Event

    def event(stream_type: str) -> Event:
        now = datetime.now(UTC)
        return Event(
            event_type="Account.Created", payload={}, seq=1, event_id="e", stream_id="s",
            stream_type=stream_type, stream_version=1, scope="company", actor="u",
            recorded_at=now, effective_at=now, correlation_id="c", causation_id=None,
            source="t", prev_hash=None, hash="h",
        )  # fmt: skip

    account, record = event("core.Account"), event("core.Record")
    for flt in (
        ANY,
        SubscriptionFilter(),
        SubscriptionFilter(scope="company"),
        SubscriptionFilter.of(),
    ):
        assert not flt.matches(account) and flt.matches(record)
    assert "core.Account" in INTERNAL_STREAM_TYPES
    admin = SubscriptionFilter.of(hide_stream_types=())
    assert admin.matches(account) and admin.matches(record)


def test_the_embedded_follower_and_tl_events_do_not_show_account_streams(
    harness: Harness, cast: Cast
) -> None:
    from tl_core.changefeed import fetch_changes

    page = fetch_changes(harness.backend.ledger, after_seq=0, limit=1000)
    assert page.events == [] or all(e.stream_type != "core.Account" for e in page.events)
    everything = harness.backend.ledger.read_after(0, limit=1000)
    assert any(e.stream_type == "core.Account" for e in everything)  # they exist, only hidden
