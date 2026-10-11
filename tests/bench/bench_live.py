"""Pieces of the realtime bench: a throw-away copy of a dataset, an app over it, an SSE reader.

The realtime bench writes records, so it never touches the cached seed: it works on a copy (a file
copy for SQLite, ``CREATE DATABASE ... TEMPLATE`` for Postgres) that is removed afterwards.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx2
import uvicorn
from bench_data import Dataset, pg_database, pg_server, pg_url_for
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from tl_adapters import db as adapter_db
from tl_adapters.postgres import admin
from tl_adapters.postgres.engine import make_engine, sqlalchemy_url
from tl_adapters.postgres.factory import PostgresUowFactory
from tl_adapters.postgres.ledger import PostgresLedger
from tl_api.app import create_app
from tl_api.backend import Backend
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_core.bus import Bus, InProcessBus
from tl_core.ledger import Ledger
from tl_core.uow import UnitOfWork


@contextmanager
def copy_of(dataset: Dataset, work: Path) -> Iterator[adapter_db.DbTarget]:
    """A private copy of ``dataset`` to write into; removed on exit."""
    if dataset.dialect == "sqlite":
        target = work / "copy.db"
        shutil.copyfile(str(dataset.target), target)
        try:
            yield target
        finally:
            for suffix in ("", "-wal", "-shm"):
                Path(str(target) + suffix).unlink(missing_ok=True)
        return
    name = f"tl_test_benchcopy_{uuid.uuid4().hex[:8]}"
    server = pg_server()
    engine = create_engine(sqlalchemy_url(server), poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql(
                f'CREATE DATABASE "{name}" TEMPLATE "{pg_database(dataset.records)}"'
            )
    finally:
        engine.dispose()
    url = pg_url_for(name)
    try:
        yield url
    finally:
        admin.drop_database(server, name)


class PostgresBackend:
    """The API's ``Backend`` over Postgres: a pooled unit-of-work factory, its ledger and a bus."""

    def __init__(self, url: str) -> None:
        self._bus: Bus = InProcessBus()
        self._engine = make_engine(url, pooled=True)
        self._factory = PostgresUowFactory(url, bus=self._bus, engine=self._engine)
        self._ledger = PostgresLedger(self._engine)

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    @property
    def bus(self) -> Bus:
        return self._bus

    def __call__(self, readonly: bool = False) -> Any:
        return self._factory(readonly)

    def close(self) -> None:
        self._factory.dispose()


def open_backend(target: adapter_db.DbTarget) -> Backend:
    if adapter_db.is_postgres(target):
        return PostgresBackend(str(target))
    return adapter_db.make_uow_factory(target)  # type: ignore[return-value]


class Live:
    """A running API: its base URL and one token per actor."""

    def __init__(self, base_url: str, tokens: dict[str, str]) -> None:
        self.base_url = base_url
        self.tokens = tokens


@contextmanager
def running_api(
    target: adapter_db.DbTarget, work: Path, *, poll_interval_s: float
) -> Iterator[Live]:
    """The real API app over ``target`` under uvicorn on a loopback port."""
    tokens_path = work / "tokens.json"
    tokens = {
        "user:alice": add_token(tokens_path, "user:alice"),
        "user:bob": add_token(tokens_path, "user:bob"),
    }
    backend = open_backend(target)
    settings = ApiSettings(
        db_path=work / "unused.db",
        tokens_path=tokens_path,
        poll_interval_s=poll_interval_s,
        sse_wait_s=0.2,  # a stream notices its closed client quickly, so shutdown is clean
    )
    app: FastAPI = create_app(backend, settings=settings, tokens=TokenStore(tokens_path))
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        lifespan="on",
        timeout_graceful_shutdown=5,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the bench API did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield Live(f"http://127.0.0.1:{port}", tokens)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        backend.close()


class SseReader:
    """Reads ``GET /stream`` on a thread and stamps the time each ``Record.Created`` key arrives."""

    def __init__(self, live: Live, actor: str) -> None:
        self._live = live
        self._actor = actor
        self.seen: dict[str, float] = {}
        self.error: Exception | None = None
        self._response: httpx2.Response | None = None
        self._cond = threading.Condition()
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> SseReader:
        self._thread.start()
        if not self._connected.wait(15):
            raise RuntimeError("the SSE stream did not open")
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        response = self._response
        if response is not None:
            try:
                response.close()  # ends the blocked read so the server can shut down cleanly
            except Exception:
                pass
        self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            self._read()
        except Exception as exc:  # the server closing the stream at shutdown ends up here too
            self.error = exc
            with self._cond:
                self._cond.notify_all()

    def _read(self) -> None:
        headers = {"Authorization": f"Bearer {self._live.tokens[self._actor]}"}
        timeout = httpx2.Timeout(10.0, read=10.0)
        with httpx2.Client(base_url=self._live.base_url, timeout=timeout) as client:
            with client.stream(
                "GET", "/stream", params={"type": "Record.Created"}, headers=headers
            ) as response:
                self._response = response
                for line in response.iter_lines():
                    now = time.perf_counter()
                    if line.startswith(": connected"):
                        self._connected.set()
                    if line.startswith("data: "):
                        key = json.loads(line[6:])["payload"].get("key")
                        with self._cond:
                            self.seen[str(key)] = now
                            self._cond.notify_all()
                    if self._stop.is_set():
                        return

    def wait_for(self, key: str, timeout_s: float = 10.0) -> float:
        """The time (``perf_counter``) the event of record ``key`` arrived."""
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while key not in self.seen:
                if self.error is not None and not self._stop.is_set():
                    raise RuntimeError("the SSE stream broke") from self.error
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"no event for {key} within {timeout_s}s")
                self._cond.wait(left)
            return self.seen[key]


def create_record_command(key: str, actor: str, scope: str) -> Any:
    from tl_core.services.commands import CreateRecord

    return CreateRecord(
        actor=actor,
        source="bench",
        scope=scope,
        record_type="core.Record",
        title=f"Realtime {key}",
        key=key,
        psets={"valve_data": {"size_in": 4.0}},
    )


def write_elsewhere(target: adapter_db.DbTarget, key: str, scope: str) -> None:
    """A write from 'another process': its own engine, no bus, no shared state with the app."""
    from tl_core.services.records import handle_create_record

    uow: UnitOfWork
    with adapter_db.open_uow(target) as uow:
        handle_create_record(uow, create_record_command(key, "user:other", scope))
