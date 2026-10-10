"""Root pytest configuration: environment defaults and the adapter parity fixtures.

Parity fixtures (P0-I5). A test that asks for ``new_db`` (or ``db``, ``adapter``) runs once per
adapter named by ``--adapters`` (default ``sqlite``; ``just test-parity`` passes
``sqlite,postgres``). Each call to ``new_db()`` returns an empty, isolated database target: a file
under ``tmp_path`` for SQLite, a fresh schema for Postgres. The Postgres schemas live in one
throw-away database per pytest session, so concurrent runs never share state or the ledger lock.
``TL_PG_URL`` names the server; when it is unreachable the Postgres runs skip, unless
``TL_REQUIRE_POSTGRES=1`` (CI) turns that into a failure.
"""

from __future__ import annotations

import atexit
import os
import signal
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType

import pytest
from sqlalchemy import Engine

# Tests sign with the public dev secret: object_secret() fails closed without TL_OBJECT_SECRET or
# TL_ENV=dev (P0-I4). A test of the fail-closed behaviour passes its own mapping instead.
os.environ.setdefault("TL_ENV", "dev")

ADAPTER_NAMES = ("sqlite", "postgres")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--adapters",
        default=os.environ.get("TL_TEST_ADAPTERS", "sqlite"),
        help="comma-separated adapters the parity fixtures run on: sqlite, postgres",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "adapter_name" not in metafunc.fixturenames:
        return
    names = [
        n.strip() for n in str(metafunc.config.getoption("--adapters")).split(",") if n.strip()
    ]
    unknown = [n for n in names if n not in ADAPTER_NAMES]
    if unknown:
        raise pytest.UsageError(f"--adapters: unknown adapter(s) {unknown}; use {ADAPTER_NAMES}")
    params = [
        pytest.param(n, marks=pytest.mark.requires_postgres) if n == "postgres" else n
        for n in names
    ]
    metafunc.parametrize("adapter_name", params, scope="function")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "adapter_name" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.parity)


@pytest.fixture(scope="session")
def pg_base_url() -> Iterator[str | None]:
    """URL of a throw-away database on the server ``TL_PG_URL`` names; ``None`` if unreachable.

    The database is dropped when the session ends, on SIGTERM, and at interpreter exit. Databases
    left by a crashed session (SIGKILL) are swept at the start of the next one once they are a few
    hours old and have no connections.
    """
    from tl_adapters.postgres import admin

    server = os.environ.get("TL_PG_URL", admin.DEFAULT_URL)
    if not admin.reachable(server):
        yield None
        return
    try:
        admin.sweep_stale_databases(server)
    except Exception:
        pass  # a sweep is housekeeping; never fail a run because of it
    name = admin.test_database_name()
    try:
        admin.create_database(server, name)
    except Exception:
        yield server  # no CREATE DATABASE right: isolate by schema in the given database
        return

    def drop() -> None:
        try:
            admin.drop_database(server, name)
        except Exception:
            pass

    atexit.register(drop)
    previous = signal.getsignal(signal.SIGTERM)

    def on_sigterm(signum: int, frame: FrameType | None) -> None:
        drop()
        if callable(previous) and previous not in (signal.SIG_DFL, signal.SIG_IGN):
            previous(signum, frame)  # whoever handled SIGTERM before us still gets it
            return
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)

    try:
        signal.signal(signal.SIGTERM, on_sigterm)
    except ValueError:  # not the main thread
        pass
    try:
        yield admin.database_url(server, name)
    finally:
        drop()
        atexit.unregister(drop)
        try:
            signal.signal(signal.SIGTERM, previous)
        except (ValueError, TypeError):
            pass


@dataclass
class Adapter:
    """Hands out empty database targets for one adapter and removes them afterwards."""

    name: str
    tmp_path: Path
    pg_url: str | None = None
    _schemas: list[str] = field(default_factory=list)
    _count: int = 0

    def new_db(self) -> str | Path:
        """An empty, isolated database target (no tables yet)."""
        if self.name == "sqlite":
            self._count += 1
            return self.tmp_path / f"tl{self._count}.db"
        from tl_adapters.postgres import admin

        assert self.pg_url is not None
        schema = "tl_t_" + uuid.uuid4().hex[:16]
        admin.create_schema_namespace(self.pg_url, schema)
        self._schemas.append(schema)
        return admin.schema_url(self.pg_url, schema)

    def close(self) -> None:
        if self.pg_url is not None:
            from tl_adapters.postgres import admin

            for schema in self._schemas:
                admin.drop_schema_namespace(self.pg_url, schema)


@pytest.fixture
def adapter(adapter_name: str, tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Adapter]:
    pg_url: str | None = None
    if adapter_name == "postgres":
        pg_url = request.getfixturevalue("pg_base_url")
        if pg_url is None:
            message = "Postgres is not reachable at TL_PG_URL"
            if os.environ.get("TL_REQUIRE_POSTGRES") == "1":
                pytest.fail(message)
            pytest.skip(message)
    current = Adapter(adapter_name, tmp_path, pg_url)
    try:
        yield current
    finally:
        current.close()


@pytest.fixture
def new_db(adapter: Adapter) -> Callable[[], str | Path]:
    """Call it for an empty database target on the adapter under test."""
    return adapter.new_db


@pytest.fixture
def dialect(adapter: Adapter) -> str:
    """``"sqlite"`` or ``"postgres"``: the argument projector ``ddl()`` methods take."""
    return "postgres" if adapter.name == "postgres" else "sqlite"


@pytest.fixture
def new_engine(new_db: Callable[[], str | Path]) -> Iterator[Callable[[], Engine]]:
    """Call it for an engine on a fresh, empty database of the adapter under test.

    For tests that drive projectors with plain ``engine.begin()`` and need no unit of work.
    Every engine is disposed after the test.
    """
    from tl_adapters.db import make_engine

    engines: list[Engine] = []

    def make() -> Engine:
        engine = make_engine(new_db())
        engines.append(engine)
        return engine

    try:
        yield make
    finally:
        for engine in engines:
            engine.dispose()


@pytest.fixture
def db(new_db: Callable[[], str | Path]) -> str | Path:
    """A database target with the default schema already created."""
    from tl_adapters.db import create_schema

    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def pg_db(pg_base_url: str | None) -> Iterator[str]:
    """An empty Postgres schema whatever ``--adapters`` says; skips if Postgres is unreachable."""
    from tl_adapters.postgres import admin

    if pg_base_url is None:
        if os.environ.get("TL_REQUIRE_POSTGRES") == "1":
            pytest.fail("Postgres is not reachable at TL_PG_URL")
        pytest.skip("Postgres is not reachable at TL_PG_URL")
    schema = "tl_t_" + uuid.uuid4().hex[:16]
    admin.create_schema_namespace(pg_base_url, schema)
    try:
        yield admin.schema_url(pg_base_url, schema)
    finally:
        admin.drop_schema_namespace(pg_base_url, schema)
