"""Shared test harness: a real app over a real SQLite file, with helpers to seed and to call it.

Nothing here mocks tl_core. ``Harness.client`` is a Starlette ``TestClient`` (an in-process httpx
client) acting as ``user:alice``; ``Harness.live()`` starts the same app under uvicorn on a
loopback port, which the SSE tests need because the in-process transport buffers whole responses.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_api.app import create_app
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_core.files.scan import Scanner
from tl_core.files.service import FileService
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.records import handle_create_record

SCOPE = "project:P123"
ALICE = "user:alice"
BOB = "user:bob"


@dataclass
class LiveServer:
    base_url: str
    token: str


@dataclass
class Harness:
    root: Path
    db: Path
    backend: SqliteUowFactory
    app: FastAPI
    service: FileService
    store: FsObjectStore
    tokens: dict[str, str]  # actor -> token
    settings: ApiSettings
    _clients: list[TestClient] = field(default_factory=list[TestClient])

    @staticmethod
    def build(
        root: Path, *, scan_inline: bool = True, files: bool = True, scanner: Scanner | None = None
    ) -> Harness:
        db = root / "tl.db"
        create_schema(db)
        backend = SqliteUowFactory(db)
        tokens_path = root / "tokens.json"
        tokens = {ALICE: add_token(tokens_path, ALICE), BOB: add_token(tokens_path, BOB)}
        store = FsObjectStore(root / "objects", secret=b"k")
        service = FileService(store, secret=b"s", scan_inline=scan_inline, scanner=scanner)
        settings = ApiSettings(
            db_path=db,
            tokens_path=tokens_path,
            poll_interval_s=0.05,
            sse_keepalive_s=0.4,
            max_upload_bytes=64 * 1024,
        )
        app = create_app(
            backend,
            settings=settings,
            tokens=TokenStore(tokens_path),
            files_service=service if files else None,
        )
        return Harness(root, db, backend, app, service, store, tokens, settings)

    def close(self) -> None:
        for client in self._clients:
            client.close()
        self.backend.close()

    # --- calling the app -----------------------------------------------------------------

    def headers(self, actor: str = ALICE) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[actor]}"}

    def client_for(self, actor: str | None = ALICE) -> TestClient:
        """A client that sends ``actor``'s token (``None``: no token)."""
        client = TestClient(self.app, raise_server_exceptions=False)
        if actor is not None:
            client.headers.update(self.headers(actor))
        self._clients.append(client)
        return client

    @property
    def client(self) -> TestClient:
        if not hasattr(self, "_default"):
            self._default = self.client_for(ALICE)
        return self._default

    # --- the HTTP client -----------------------------------------------------------------

    def api(self, actor: str = ALICE) -> ApiClient:
        """An ``ApiClient`` for ``actor`` that talks to the app in process (no sockets)."""
        return ApiClient("http://testserver", self.tokens[actor], http=self.client_for(None))

    @contextmanager
    def live_api(self, actor: str = ALICE) -> Iterator[ApiClient]:
        """An ``ApiClient`` that talks to the app over a real loopback server."""
        with self.live(actor) as server:
            client = ApiClient(server.base_url, server.token)
            try:
                yield client
            finally:
                client.close()

    # --- seeding (through tl_core handlers, as any caller would) ---------------------------

    def create_record(
        self,
        key: str,
        title: str = "A record",
        *,
        scope: str = SCOPE,
        psets: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> CommandResult:
        with self.backend(False) as uow:
            return handle_create_record(
                uow,
                CreateRecord(
                    actor="user:seed",
                    source="test",
                    scope=scope,
                    record_type="core.Record",
                    title=title,
                    key=key,
                    description=description,
                    psets=psets or {},
                ),
            )

    # --- a real server -------------------------------------------------------------------

    @contextmanager
    def live(self, actor: str = ALICE) -> Iterator[LiveServer]:
        """Run the app under uvicorn on 127.0.0.1 (port chosen by the OS) for the block."""
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=0,
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
        port = server.servers[0].sockets[0].getsockname()[1]
        try:
            yield LiveServer(f"http://127.0.0.1:{port}", self.tokens[actor])
        finally:
            server.should_exit = True
            thread.join(timeout=10)
