"""Helpers for the remote-mode tests: a writer that is another process, and a restartable server."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import uvicorn
from harness import Harness
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.app import create_app
from tl_api.tokens import TokenStore
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.records import handle_create_record, handle_update_record

SCOPE = "project:P123"


class OtherWriter:
    """Writes to the harness ledger through its own engine and bus, like the CLI does.

    The server's change feed only sees these writes by polling the ledger, which is the path an
    embedded TUI or `tl record create` takes in the demo.
    """

    def __init__(self, harness: Harness, actor: str = "user:bob") -> None:
        self.factory = SqliteUowFactory(harness.db)
        self.actor = actor

    def create(self, key: str, title: str = "Written elsewhere") -> CommandResult:
        with self.factory(False) as uow:
            return handle_create_record(
                uow,
                CreateRecord(
                    actor=self.actor,
                    source="test",
                    scope=SCOPE,
                    record_type="core.Record",
                    key=key,
                    title=title,
                ),
            )

    def update(self, stream_id: str, version: int, **changes: Any) -> CommandResult:
        with self.factory(False) as uow:
            return handle_update_record(
                uow,
                UpdateRecord(
                    actor=self.actor,
                    source="test",
                    scope=SCOPE,
                    stream_id=stream_id,
                    expected_version=version,
                    changes=changes,
                ),
            )

    def close(self) -> None:
        self.factory.close()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class RestartableServer:
    """The harness's API under uvicorn on a fixed loopback port that can be stopped and started."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.port = free_port()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def token(self) -> str:
        return self.harness.tokens["user:alice"]

    def start(self) -> None:
        h = self.harness
        app = create_app(
            h.backend,
            settings=h.settings,
            tokens=TokenStore(h.settings.tokens_path),
            files_service=h.service,
        )
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            lifespan="on",
            timeout_graceful_shutdown=1,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("the test server did not start")
            time.sleep(0.01)
        self._server, self._thread = server, thread

    def stop(self) -> None:
        if self._server is not None and self._thread is not None:
            self._server.should_exit = True
            self._thread.join(timeout=10)
        self._server = self._thread = None


@contextmanager
def restartable(harness: Harness) -> Iterator[RestartableServer]:
    server = RestartableServer(harness)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def wait_for(predicate: Any, timeout: float = 5.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.01)
