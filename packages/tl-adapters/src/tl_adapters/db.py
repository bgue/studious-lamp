"""Pick the adapter from the database target, so callers and tests are written once.

A target is a SQLite file path or a ``postgresql://`` URL. ``tl_core`` and the services see only
what these functions return; the dialect work stays in ``tl_adapters.sqlite`` and
``tl_adapters.postgres``. The parity suite runs the same test against both kinds of target.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from tl_core.bus import Bus
from tl_core.projection.types import ProjectorRegistry
from tl_core.util import new_ulid, utcnow

from tl_adapters import postgres, sqlite
from tl_adapters._unit import AppendInLedger, BaseUnitOfWork

DbTarget = str | Path
"""A SQLite ledger file, or a ``postgresql://`` URL (optionally scoped by ``schema_url``)."""


class LedgerWithSchema(AppendInLedger):
    """A ledger that can create its own tables."""

    def create_schema(self) -> None: ...


_POSTGRES_SCHEMES = ("postgresql", "postgres", "postgresql+pg8000")
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*)://")
#: The query parameters of a Postgres URL the adapter understands. Anything else is refused: the
#: driver would take ``host``/``port`` from it (so one session key could name two servers) or fail
#: on it with a raw ``TypeError``, and ``password``/``sslpassword`` would put a secret in the URL.
_ALLOWED_QUERY = ("sslmode", "options", "application_name")
#: What a printed URL shows of its query string; every other value is replaced by ``***``.
_SHOWN_QUERY = ("sslmode", "application_name")


def _scheme(text: str) -> str | None:
    """The lower-case scheme of ``text`` when it looks like ``scheme://...``, else ``None``."""
    found = _SCHEME.match(text)
    return found.group(1).lower() if found else None


def is_postgres(target: DbTarget) -> bool:
    """True when ``target`` names a Postgres database (``postgresql://``, ``postgres://`` or
    ``postgresql+pg8000://``, in any letter case)."""
    return isinstance(target, str) and _scheme(target) in _POSTGRES_SCHEMES


def as_target(value: str | Path) -> DbTarget:
    """A command-line or environment value as a database target.

    A Postgres URL stays text (``Path`` would collapse the ``//`` and mangle the password) after a
    sanity check; anything that is not a URL is a SQLite file path. Any other ``scheme://`` value is
    refused, because it would otherwise become a directory named after the URL, password included.
    ``ValueError`` messages never repeat the value: it can hold a password.
    """
    if isinstance(value, Path):
        return value
    scheme = _scheme(value)
    if scheme is None:
        return Path(value)
    if scheme not in _POSTGRES_SCHEMES:
        raise ValueError(
            "unsupported database URL scheme; use a SQLite file path or a postgresql:// URL"
        )
    try:
        parsed = make_url(value)
    except ArgumentError:
        raise ValueError("the database URL is not valid") from None
    if parsed.host is not None and "@" in parsed.host:
        raise ValueError(
            "the database URL has an unescaped '@' in the password; percent-encode it (%40)"
        )
    if not parsed.username:
        raise ValueError("the database URL needs a user name (postgresql://user:password@host/db)")
    if any(name.lower() not in _ALLOWED_QUERY for name in parsed.query):
        raise ValueError(
            "the database URL has a query parameter the adapter does not accept; "
            f"allowed: {', '.join(_ALLOWED_QUERY)} (host, port and password belong in the "
            "address part)"
        )
    try:
        postgres.engine.split_url(value)  # an unsupported sslmode fails here, not in a command
    except ValueError as exc:
        raise ValueError(str(exc)) from None
    return value


def display_target(target: DbTarget) -> str:
    """``target`` as text that is safe to print: a Postgres URL without its password.

    The query string is an allow-list: ``sslmode`` and ``application_name`` are shown, every other
    value (``options``, a stray ``password=``, ``host=``...) becomes ``***``. A URL that cannot be
    parsed safely is shown as ``<invalid database URL>``, never as written.
    """
    if not is_postgres(target):
        return str(target)
    try:
        parsed = make_url(str(target))
    except ArgumentError:
        return "<invalid database URL>"
    if parsed.host is not None and "@" in parsed.host:
        return "<invalid database URL>"
    hidden = {key: "***" for key in parsed.query if key.lower() not in _SHOWN_QUERY}
    shown = parsed.update_query_dict(hidden).render_as_string(hide_password=True)
    return shown.replace("%2A%2A%2A", "***")  # the query string percent-encodes the mask


def target_key(target: DbTarget) -> str:
    """A stable name for the ledger ``target`` that is safe to store and to print: no password.

    ``db:<absolute path>`` for SQLite; ``pg:user@host:port/database`` for Postgres (the host in
    lower case), plus ``?options=sha256:<16 hex>`` when the URL scopes the schema with ``options``:
    the options are hashed, so nothing written there is stored in clear. ``sslmode`` and every other
    parameter are left out, so the same ledger reached with another TLS mode keeps one name. The CLI
    keys its stored sign-in by this (ADR-0009 section 4 and the P1-I0 workstream B addendum).
    ``as_target`` refuses ``host=`` and ``port=`` in the query string, which would let two servers
    share one key.
    """
    if not is_postgres(target):
        return f"db:{Path(target).expanduser().resolve()}"
    parsed = make_url(str(target))
    host = (parsed.host or "localhost").lower()
    key = f"pg:{parsed.username or ''}@{host}:{parsed.port or 5432}/{parsed.database or ''}"
    options = parsed.query.get("options")
    if options:
        joined = options if isinstance(options, str) else " ".join(options)
        key += f"?options=sha256:{hashlib.sha256(joined.encode()).hexdigest()[:16]}"
    return key


def dialect_of(target: DbTarget) -> str:
    """``"postgres"`` or ``"sqlite"``."""
    return "postgres" if is_postgres(target) else "sqlite"


def make_engine(target: DbTarget) -> Engine:
    """A SQLAlchemy engine for ``target``. The caller disposes it."""
    if is_postgres(target):
        return postgres.engine.make_engine(str(target))
    return sqlite.engine.make_engine(target)


def write_tx(engine: Engine) -> AbstractContextManager[Connection]:
    """One write transaction on an engine from :func:`make_engine`."""
    if engine.dialect.name == "postgresql":
        return postgres.engine.write_tx(engine)
    return sqlite.engine.write_tx(engine)


def read_tx(engine: Engine) -> AbstractContextManager[Connection]:
    """One read transaction (a consistent snapshot) on an engine from :func:`make_engine`."""
    if engine.dialect.name == "postgresql":
        return postgres.engine.read_tx(engine)
    return sqlite.engine.read_tx(engine)


def make_ledger(
    engine: Engine,
    *,
    clock: Callable[[], datetime] = utcnow,
    id_gen: Callable[[], str] = new_ulid,
) -> Any:
    """The ledger class for the engine's dialect (``SqliteLedger`` or ``PostgresLedger``)."""
    if engine.dialect.name == "postgresql":
        return postgres.ledger.PostgresLedger(engine, clock=clock, id_gen=id_gen)
    return sqlite.ledger.SqliteLedger(engine, clock=clock, id_gen=id_gen)


def open_uow(
    target: DbTarget,
    *,
    readonly: bool = False,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> AbstractContextManager[BaseUnitOfWork]:
    """Open ``target`` and yield an entered unit of work (one transaction)."""
    if is_postgres(target):
        return postgres.uow.open_uow(str(target), readonly=readonly, registry=registry, bus=bus)
    return sqlite.uow.open_uow(target, readonly=readonly, registry=registry, bus=bus)


def create_schema(target: DbTarget, *, registry: ProjectorRegistry | None = None) -> None:
    """Create the events table and every registered projector's tables. Idempotent."""
    if is_postgres(target):
        postgres.uow.create_schema(str(target), registry=registry)
    else:
        sqlite.uow.create_schema(target, registry=registry)


def rebuild_projections(
    target: DbTarget,
    *,
    types: Sequence[str] | None = None,
    registry: ProjectorRegistry | None = None,
    on_progress: Callable[[int], None] | None = None,
    after_replay: Callable[[Connection, int], None] | None = None,
) -> int:
    """Reset projectors and replay the whole ledger into them, in one transaction.

    ``after_replay(conn, last_seq)`` runs in that transaction after the last event.
    """
    if is_postgres(target):
        return postgres.uow.rebuild_projections(
            str(target),
            types=types,
            registry=registry,
            on_progress=on_progress,
            after_replay=after_replay,
        )
    return sqlite.uow.rebuild_projections(
        target,
        types=types,
        registry=registry,
        on_progress=on_progress,
        after_replay=after_replay,
    )


def make_uow_factory(
    target: DbTarget,
    *,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> sqlite.factory.SqliteUowFactory | postgres.factory.PostgresUowFactory:
    """A long-lived unit-of-work factory for ``target`` (one engine, many short transactions).

    ``factory()`` opens a write unit of work and ``factory(readonly=True)`` a read snapshot on
    either adapter; ``dispose()`` ends it. Servers and workers (the webhook worker, the API) build
    one at start-up and pass it around.
    """
    if is_postgres(target):
        return postgres.factory.PostgresUowFactory(str(target), registry=registry, bus=bus)
    return sqlite.factory.SqliteUowFactory(target, registry=registry, bus=bus)
