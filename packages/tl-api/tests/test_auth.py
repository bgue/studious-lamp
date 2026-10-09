"""Dev identity (ADR-0005): tokens, the allow-all hook that every route calls, the bind rule."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from harness import ALICE, BOB, Harness
from tl_api.app import create_app
from tl_api.auth import Forbidden
from tl_api.settings import check_bind, is_loopback
from tl_api.tokens import TokenStore, add_token, check_actor


def test_a_request_without_a_token_is_401(harness: Harness) -> None:
    response = harness.client_for(None).get("/events")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


def test_an_unknown_token_is_401(harness: Harness) -> None:
    client = harness.client_for(None)
    assert client.get("/events", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/events", headers={"Authorization": "Basic abc"}).status_code == 401


def test_health_needs_no_token(harness: Harness) -> None:
    assert harness.client_for(None).get("/health").json() == {"status": "ok"}


def test_the_hook_sees_the_actor_the_action_and_the_resource(harness: Harness) -> None:
    seen: list[tuple[str, str, str]] = []
    app = create_app(
        harness.backend,
        settings=harness.settings,
        tokens=TokenStore(harness.settings.tokens_path),
        authorize_hook=lambda *args: seen.append(args),
    )
    from fastapi.testclient import TestClient

    client = TestClient(app, headers=harness.headers(BOB))
    assert client.get("/events").status_code == 200
    assert seen == [(BOB, "events.read", "/events")]


def deny(actor: str, action: str, resource: str) -> None:
    raise Forbidden(f"{actor} may not {action}")


def test_every_route_calls_the_hook(harness: Harness) -> None:
    """A deny-all hook turns every route except /health into a 403, even with a body that would
    fail validation: the hook runs before the body is used. Routes come from the OpenAPI paths."""
    from fastapi.testclient import TestClient

    app = create_app(
        harness.backend,
        settings=harness.settings,
        tokens=TokenStore(harness.settings.tokens_path),
        authorize_hook=deny,
    )
    client = TestClient(app, headers=harness.headers(ALICE), raise_server_exceptions=False)
    checked = 0
    for route_path, operations in app.openapi()["paths"].items():
        if route_path == "/health":
            continue
        path = route_path.replace("{", "x").replace("}", "")  # any value will do
        for method in operations:
            response = client.request(method.upper(), path, json={})
            assert response.status_code == 403, f"{method} {route_path} did not call authorize"
            assert response.json()["error"] == "forbidden"
            checked += 1
    assert checked >= 20


def test_a_token_added_while_running_works_without_a_restart(harness: Harness) -> None:
    client = harness.client_for(None)
    token = add_token(harness.settings.tokens_path, "agent:triage")
    assert client.get("/events", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_the_token_file_is_private_and_holds_token_to_actor(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "tokens.json"
    token = add_token(path, "user:carol")
    assert json.loads(path.read_text()) == {token: "user:carol"}
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert TokenStore(path).actor_for(token) == "user:carol"
    assert TokenStore(path).actor_for(token + "x") is None


def test_a_broken_token_file_authenticates_nobody(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("not json")
    assert TokenStore(path).actor_for("anything") is None
    assert TokenStore(tmp_path / "missing.json").actor_for("anything") is None


@pytest.mark.parametrize("actor", ["user:alice", "agent:triage-1", "user:a.b@c"])
def test_actor_names_that_are_accepted(actor: str) -> None:
    assert check_actor(actor) == actor


@pytest.mark.parametrize("actor", ["alice", "svc:scanner", "user:", "user:a b", "admin:root"])
def test_actor_names_that_are_refused(actor: str) -> None:
    with pytest.raises(ValueError):
        check_actor(actor)


def test_only_loopback_binds_are_allowed_by_default() -> None:
    for host in ("127.0.0.1", "::1", "localhost", "127.1.2.3"):
        assert is_loopback(host)
        check_bind(host, insecure_dev=False)
    for host in ("0.0.0.0", "192.168.1.5", "example.com", "::"):
        assert not is_loopback(host)
        with pytest.raises(ValueError, match="--insecure-dev"):
            check_bind(host, insecure_dev=False)
        check_bind(host, insecure_dev=True)


def test_insecure_dev_logs_a_warning_on_every_request(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    from dataclasses import replace

    from fastapi.testclient import TestClient

    app = create_app(
        harness.backend,
        settings=replace(harness.settings, insecure_dev=True),
        tokens=TokenStore(harness.settings.tokens_path),
    )
    client = TestClient(app)
    with caplog.at_level("WARNING", logger="tl_api"):
        client.get("/health")
        client.get("/health")
    assert len([r for r in caplog.records if "INSECURE DEV" in r.getMessage()]) == 2
