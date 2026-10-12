"""The API server on ``open_backend``: SQLite and Postgres behave the same (P1-I0-S31).

A real server (uvicorn on a loopback port) over a ledger from ``new_db``. The change feed has two
sources, the backend's bus (writes made in this process) and a poller over the ledger (writes made
by another process); both must reach an SSE client, in ``seq`` order, once each, and a client that
reconnects with ``Last-Event-ID`` must get the rest from the ledger.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx2
import pytest
import uvicorn
from sqlalchemy import text
from tl_adapters.backend import open_backend
from tl_adapters.db import DbTarget, create_schema
from tl_api.app import create_app
from tl_api.main import mark_server_started, started_server
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_core.ledger import NewEvent

ACTOR = "user:alice"
SCOPE = "project:P1"
TIMEOUT = httpx2.Timeout(8.0, read=8.0)


def append(backend: object, key: str) -> None:
    with backend() as uow:  # type: ignore[operator]
        uow.append(
            stream_id=f"R-{key}",
            stream_type="core.Record",
            scope=SCOPE,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={
                        "record_type": "core.Record",
                        "key": key,
                        "title": key,
                        "psets": {},
                    },
                )
            ],
            actor=ACTOR,
            source="test",
            correlation_id="c",
        )


@contextmanager
def live_server(target: DbTarget, root: Path) -> Iterator[tuple[str, str, object]]:
    """(base url, token, backend) of a server on ``target`` that stops at the end of the block."""
    tokens_path = root / "tokens.json"
    token = add_token(tokens_path, ACTOR)
    backend = open_backend(target)
    settings = ApiSettings(
        db_path=target,
        tokens_path=tokens_path,
        poll_interval_s=0.05,
        sse_keepalive_s=0.4,
        sse_wait_s=0.1,
    )
    app = create_app(backend, settings=settings, tokens=TokenStore(tokens_path))
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="warning", timeout_graceful_shutdown=1
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the test server did not start")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", token, backend
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        backend.close()


def read_ids(response: httpx2.Response, count: int) -> list[int]:
    """The ``id`` of the next ``count`` messages of an SSE response."""
    found: list[int] = []
    for line in response.iter_lines():
        if line.startswith("id: "):
            found.append(int(line[4:]))
            if len(found) == count:
                break
    return found


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    found = new_db()
    create_schema(found)
    return found


def test_the_stream_carries_own_writes_and_another_process_writes(
    target: DbTarget, tmp_path: Path
) -> None:
    with live_server(target, tmp_path) as (base, token, backend):
        headers = {"Authorization": f"Bearer {token}"}
        with (
            httpx2.Client(base_url=base, timeout=TIMEOUT) as client,
            client.stream("GET", "/stream", headers=headers) as response,
        ):
            assert response.status_code == 200
            append(backend, "OWN")  # reaches the stream through the backend's bus
            with open_backend(target) as other:  # a second engine and bus: only the ledger links it
                append(other, "FOREIGN")
            assert read_ids(response, 2) == [1, 2]


def test_a_client_that_reconnects_gets_what_it_missed_from_the_ledger(
    target: DbTarget, tmp_path: Path
) -> None:
    with live_server(target, tmp_path) as (base, token, backend):
        for key in ("A", "B", "C"):
            append(backend, key)
        headers = {"Authorization": f"Bearer {token}", "Last-Event-ID": "1"}
        with (
            httpx2.Client(base_url=base, timeout=TIMEOUT) as client,
            client.stream("GET", "/stream", headers=headers) as response,
        ):
            assert read_ids(response, 2) == [2, 3]


def test_a_command_over_http_is_a_ledger_event_and_a_current_state_row(
    target: DbTarget, tmp_path: Path
) -> None:
    with live_server(target, tmp_path) as (base, token, backend):
        headers = {"Authorization": f"Bearer {token}"}
        with httpx2.Client(base_url=base, timeout=TIMEOUT, headers=headers) as client:
            made = client.post(
                "/commands/CreateRecord",
                json={
                    "scope": SCOPE,
                    "record_type": "core.Record",
                    "title": "Pour slab",
                    "key": "REC-1",
                },
            )
            assert made.status_code == 200, made.text
            listed = client.get("/records", params={"scope": SCOPE})
            assert listed.status_code == 200, listed.text
            assert [row["key"] for row in listed.json()] == ["REC-1"]
        assert backend.ledger.head_seq() == 1  # type: ignore[attr-defined]


def test_the_restart_mark_is_written_through_the_backend(target: DbTarget) -> None:
    with open_backend(target) as backend:
        mark_server_started(backend)
        with backend(True) as uow:
            who = uow.conn().execute(
                text("SELECT applied_by FROM setting_effect_applied WHERE effect = 'restart'")
            )
            assert [row.applied_by for row in who] == ["server"]


def test_started_server_marks_only_after_the_sockets_are_bound(
    target: DbTarget, tmp_path: Path
) -> None:
    tokens_path = tmp_path / "tokens.json"
    add_token(tokens_path, ACTOR)
    backend = open_backend(target)
    settings = ApiSettings(db_path=target, tokens_path=tokens_path, host="127.0.0.1", port=0)
    app = create_app(backend, settings=settings, tokens=TokenStore(tokens_path))
    marked = threading.Event()
    server = started_server(app, settings, marked.set)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        assert marked.wait(10)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        backend.close()


GOOD_PASSWORD = "correct horse battery"


def seed_accounts(target: DbTarget) -> None:
    """The demo admin and an ordinary user ``amy`` (A's account services, any database)."""
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password
    from tl_core.auth.seed import seed_demo

    with open_backend(target) as backend:
        assert seed_demo(backend, env="dev") is not None
        with backend() as uow:
            accounts.create_account(
                uow,
                username="amy",
                display_name="Amy",
                kind="person",
                roles=["user"],
                password=prepare_password(GOOD_PASSWORD, username="amy"),
                by="user:demo",
            )


def test_sign_in_roles_and_lockout_work_on_either_database(
    target: DbTarget, tmp_path: Path
) -> None:
    seed_accounts(target)
    with live_server(target, tmp_path) as (base, _token, _backend):
        with httpx2.Client(base_url=base, timeout=TIMEOUT) as client:

            def sign_in(name: str, password: str) -> httpx2.Response:
                return client.post("/auth/sign-in", json={"username": name, "password": password})

            admin = sign_in("demo", "demo")
            assert admin.status_code == 200, admin.text
            admin_headers = {"Authorization": f"Bearer {admin.json()['token']}"}
            me = client.get("/auth/me", headers=admin_headers)
            assert me.status_code == 200 and me.json()["actor"] == "user:demo"
            assert client.get("/admin/accounts", headers=admin_headers).status_code == 200

            amy = sign_in("amy", GOOD_PASSWORD)
            assert amy.status_code == 200, amy.text
            amy_headers = {"Authorization": f"Bearer {amy.json()['token']}"}
            refused = client.get("/admin/accounts", headers=amy_headers)
            assert refused.status_code == 403 and refused.json()["error"] == "forbidden"

            statuses = [sign_in("amy", "not the password").status_code for _ in range(12)]
            assert 423 in statuses  # repeated bad passwords lock the account
            assert sign_in("amy", GOOD_PASSWORD).status_code == 423  # even the right one now
            assert client.post("/auth/sign-out", headers=admin_headers).status_code == 204
            assert client.get("/auth/me", headers=admin_headers).status_code == 401
