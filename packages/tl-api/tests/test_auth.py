"""Dev identity (ADR-0005): tokens, the allow-all hook that every route calls, the bind rule."""

from __future__ import annotations

import json
import os
import stat
import threading
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
    # /openapi.json is served by the app but not listed in its own document: name it here.
    routes = [("/openapi.json", ["get"])] + [
        (path, list(operations)) for path, operations in app.openapi()["paths"].items()
    ]
    for route_path, methods in routes:
        if route_path == "/health":
            continue
        path = route_path.replace("{", "x").replace("}", "")  # any value will do
        for method in methods:
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


def body_routes(h: Harness) -> list[tuple[str, str]]:
    """Every (method, path) of the committed document that takes a request body."""
    found = []
    for path, operations in h.app.openapi()["paths"].items():
        for method in operations:
            if method in ("post", "put") and path != "/health":
                found.append((method.upper(), path.replace("{", "x").replace("}", "")))
    return found


def test_authentication_comes_before_the_body_is_read(harness: Harness) -> None:
    """No token and a body that is not even JSON must be 401, not 422, on every body route."""
    routes = body_routes(harness)
    assert len(routes) >= 15
    anon = harness.client_for(None)
    known = harness.client_for(ALICE)
    for method, path in routes:
        broken = {"content": b"{not json", "headers": {"content-type": "application/json"}}
        assert anon.request(method, path, **broken).status_code == 401, f"{method} {path}"
        wrong = {**broken, "headers": {**broken["headers"], "Authorization": "Bearer nope"}}
        assert anon.request(method, path, **wrong).status_code == 401, f"{method} {path}"
        # with a real token the same body is a validation error, so the 401 above was the token
        assert known.request(method, path, **broken).status_code == 422, f"{method} {path}"


def test_an_unknown_path_without_a_token_is_401_not_404(harness: Harness) -> None:
    anon = harness.client_for(None)
    assert anon.get("/no/such/path").status_code == 401
    assert harness.client_for(ALICE).get("/no/such/path").status_code == 404


def test_the_openapi_document_needs_a_token(harness: Harness) -> None:
    anon = harness.client_for(None)
    assert anon.get("/openapi.json").status_code == 401
    assert anon.get("/docs").status_code == 401 and anon.get("/redoc").status_code == 401
    served = harness.client_for(ALICE).get("/openapi.json")
    assert served.status_code == 200
    assert served.json() == harness.app.openapi()
    assert "/openapi.json" not in served.json()["paths"]  # the committed document is unchanged


def test_a_group_or_world_readable_token_file_is_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "tokens.json"
    token = add_token(path, "user:alice")
    assert TokenStore(path).actor_for(token) == "user:alice"
    for mode in (0o640, 0o604, 0o660, 0o644):
        os.chmod(path, mode)
        with pytest.raises(ValueError, match="chmod 600"):
            TokenStore(path).check()
        with pytest.raises(ValueError, match="chmod 600"):
            add_token(path, "user:bob")
        with caplog.at_level("ERROR", logger="tl_api"):
            assert TokenStore(path).actor_for(token) is None  # fails closed
        assert "token file refused" in caplog.text
        caplog.clear()
    os.chmod(path, 0o600)
    TokenStore(path).check()
    assert TokenStore(path).actor_for(token) == "user:alice"
    TokenStore(tmp_path / "missing.json").check()  # no file is not an error


def test_the_server_will_not_start_on_an_open_token_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tl_adapters.sqlite.uow import create_schema
    from tl_api import main as server

    db = tmp_path / "tl.db"
    create_schema(db)
    tokens = tmp_path / "tokens.json"
    add_token(tokens, "user:alice")
    os.chmod(tokens, 0o644)
    assert server.main(["--db", str(db), "--tokens", str(tokens)]) == 2
    assert "chmod 600" in capsys.readouterr().err


def test_concurrent_add_token_calls_all_keep_their_token(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    issued: list[str] = []
    guard = threading.Lock()

    def worker(n: int) -> None:
        token = add_token(path, f"user:u{n}")
        with guard:
            issued.append(token)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(24)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(issued) == 24
    stored = json.loads(path.read_text())
    assert set(stored) == set(issued)  # none was overwritten by a racing writer
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))  # no scratch file left behind
