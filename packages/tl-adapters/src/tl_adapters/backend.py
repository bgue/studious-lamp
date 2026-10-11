"""One backend for a long-running process, opened from a SQLite path or a ``postgresql://`` URL.

``open_backend(target)`` is what the API server, the embedded TUI client, the MCP server and the
operator commands open at start-up. It returns a :class:`DatabaseBackend` that bundles the four
things those callers need, whichever database sits behind it:

* the unit-of-work factory (``backend(readonly)`` yields an entered ``UnitOfWork``);
* the change feed's two halves, ``backend.ledger`` (cursor reads for a poller) and ``backend.bus``
  (this process's own commits, published in commit order);
* a read-only snapshot connection for readers that want SQL and no unit of work
  (``backend.read_connection()``, used by the lake sync);
* ``close()``, which ends the engine.

A target is a ``DbTarget``: a ``pathlib.Path`` for SQLite, or the text of a Postgres URL. Use
:func:`tl_adapters.db.as_target` to turn a command-line or environment value into one. The URL keeps
its query string: ``?sslmode=disable|require|verify-ca|verify-full`` and a schema scope
(``?options=-csearch_path=<schema>``) reach the driver unchanged (``postgres.engine.split_url``).
Callers never print a URL; they print ``tl_adapters.db.display_target(target)``.

Opening is lazy for SQLite (the file is created by the first transaction, so check
:func:`tl_adapters.db.ledger_exists` first when a missing ledger is an error) and eager enough for
Postgres that a wrong host or password fails here, not on the first request, as
:class:`BackendUnavailableError`.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError
from tl_core.bus import Bus, InProcessBus
from tl_core.ledger import Ledger
from tl_core.projection.types import ProjectorRegistry
from tl_core.uow import UnitOfWork

from tl_adapters import db
from tl_adapters.db import DbTarget
from tl_adapters.postgres.factory import PostgresUowFactory
from tl_adapters.sqlite.factory import SqliteUowFactory

__all__ = ["BackendUnavailableError", "DatabaseBackend", "ledger_exists", "open_backend"]


class BackendUnavailableError(RuntimeError):
    """The database cannot be reached (wrong host, port or credentials, server down).

    The message names the target without its password and the kind of failure, never the driver's
    text, which can echo connection parameters.
    """


class DatabaseBackend:
    """A unit-of-work factory, a ledger, a bus and a read snapshot over one database target."""

    def __init__(
        self,
        target: DbTarget,
        *,
        registry: ProjectorRegistry | None = None,
        bus: Bus | None = None,
    ) -> None:
        self.target: DbTarget = target
        self.dialect: str = db.dialect_of(target)
        self.bus: Bus = bus if bus is not None else InProcessBus()
        self._factory: SqliteUowFactory | PostgresUowFactory
        self._ledger: Ledger
        self._engine: Engine
        if db.is_postgres(target):
            from tl_adapters.postgres.engine import make_engine
            from tl_adapters.postgres.ledger import PostgresLedger

            self._engine = make_engine(str(target), pooled=True)
            self._factory = PostgresUowFactory(
                str(target), registry=registry, bus=self.bus, engine=self._engine
            )
            self._ledger = PostgresLedger(self._engine)
        else:
            sqlite_factory = SqliteUowFactory(target, registry=registry, bus=self.bus)
            self._factory = sqlite_factory
            self._engine = sqlite_factory.engine
            self._ledger = sqlite_factory.ledger

    @property
    def ledger(self) -> Ledger:
        """Cursor reads of the ledger, for a change-feed poller or a catch-up page."""
        return self._ledger

    @property
    def engine(self) -> Engine:
        """The engine behind the factory, for callers that need ``db.read_tx`` or ``write_tx``."""
        return self._engine

    @property
    def display(self) -> str:
        """The target as text that is safe to print (a Postgres URL without its password)."""
        return db.display_target(self.target)

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        """A unit of work: a write transaction, or with ``readonly`` a consistent read snapshot."""
        return self._factory(readonly)

    def read_connection(self) -> AbstractContextManager[Connection]:
        """One read-only snapshot connection (every read in the block sees one instant)."""
        return db.read_tx(self._engine)

    def check(self) -> None:
        """Run ``SELECT 1``; ``BackendUnavailableError`` when the database cannot be reached."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise BackendUnavailableError(
                f"cannot reach the database {self.display} ({type(exc).__name__})"
            ) from None

    def close(self) -> None:
        """End the engine and its pooled connections. Safe to call twice."""
        self._engine.dispose()

    def dispose(self) -> None:
        """Alias of :meth:`close`: the name the webhook worker and the factories use."""
        self.close()

    def __enter__(self) -> DatabaseBackend:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def open_backend(
    target: DbTarget,
    *,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> DatabaseBackend:
    """Open ``target`` (a SQLite path or a ``postgresql://`` URL) as a :class:`DatabaseBackend`.

    A Postgres target is probed once (``BackendUnavailableError`` if it cannot be reached). A
    SQLite target is not touched until the first transaction. The caller closes the backend, or
    uses it as a context manager.
    """
    backend = DatabaseBackend(target, registry=registry, bus=bus)
    if db.is_postgres(target):
        try:
            backend.check()
        except BackendUnavailableError:
            backend.close()
            raise
    return backend


def ledger_exists(target: DbTarget) -> bool:
    """True when ``target`` holds a ledger: a SQLite file, or a Postgres schema with ``events``.

    It never creates anything. A Postgres server that cannot be reached raises
    ``BackendUnavailableError``, so a caller can tell "run `tl init`" from "the database is down".
    """
    if not db.is_postgres(target):
        return Path(target).is_file()
    engine = db.make_engine(target)
    try:
        with engine.connect() as conn:
            found = conn.execute(text("SELECT to_regclass('events') IS NOT NULL")).scalar()
        return bool(found)
    except SQLAlchemyError as exc:
        raise BackendUnavailableError(
            f"cannot reach the database {db.display_target(target)} ({type(exc).__name__})"
        ) from None
    finally:
        engine.dispose()
