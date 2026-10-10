"""Helpers to point a connection URL at one schema and to create or drop that schema.

A schema per test run (or per tenant) is how parity tests and local dev databases stay isolated
inside one Postgres database: every table, the ``events`` triggers and the functions live in the
schema the connection's ``search_path`` names.
"""

from __future__ import annotations

import os
import re
import time
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from tl_adapters.postgres.engine import sqlalchemy_url

DEFAULT_URL = "postgresql://postgres:postgres@localhost:5432/tl_test"
"""The dev cluster of ADR-0002; ``TL_PG_URL`` overrides it."""

TEST_DATABASE_PREFIX = "tl_pytest_"
_TEST_DATABASE = re.compile(r"^tl_pytest_(?:icu_)?([0-9a-f]{8})_(\d+)_[0-9a-f]{6}$")
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _checked(schema: str) -> str:
    if not _SCHEMA_NAME.match(schema):
        raise ValueError(f"not a safe schema name: {schema!r}")
    return schema


def schema_url(url: str, schema: str) -> str:
    """``url`` with its ``search_path`` set to ``schema`` (lower-case letters, digits, ``_``)."""
    parsed = make_url(sqlalchemy_url(url)).update_query_dict(
        {"options": f"-csearch_path={_checked(schema)}"}
    )
    return parsed.render_as_string(hide_password=False).replace(
        "postgresql+pg8000://", "postgresql://"
    )


def create_schema_namespace(url: str, schema: str) -> None:
    """``CREATE SCHEMA IF NOT EXISTS`` for ``schema`` using the plain (unscoped) ``url``."""
    _run(url, f"CREATE SCHEMA IF NOT EXISTS {_checked(schema)}")


def drop_schema_namespace(url: str, schema: str) -> None:
    """``DROP SCHEMA ... CASCADE`` for ``schema``; a missing schema is not an error."""
    _run(url, f"DROP SCHEMA IF EXISTS {_checked(schema)} CASCADE")


def reachable(url: str, *, timeout_s: int = 3) -> bool:
    """True when a connection to ``url`` can be opened and ``SELECT 1`` runs."""
    engine = create_engine(
        sqlalchemy_url(url), poolclass=NullPool, connect_args={"timeout": timeout_s}
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


def _run(url: str, statement: str) -> None:
    engine = create_engine(sqlalchemy_url(url), poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql(statement)
    finally:
        engine.dispose()


def database_url(url: str, database: str) -> str:
    """``url`` pointing at another database on the same server."""
    parsed = make_url(sqlalchemy_url(url)).set(database=_checked(database))
    return parsed.render_as_string(hide_password=False).replace(
        "postgresql+pg8000://", "postgresql://"
    )


def create_database(url: str, database: str, *, icu_locale: str | None = None) -> None:
    """``CREATE DATABASE`` on the server ``url`` names.

    ``icu_locale`` (for example ``"en-US"``) makes a database whose default text ordering is
    locale-aware, like the default of most server images; tests use it to prove that ordering does
    not depend on the cluster's locale.
    """
    options = ""
    if icu_locale is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", icu_locale):
            raise ValueError(f"not a safe ICU locale: {icu_locale!r}")
        options = (
            f" TEMPLATE template0 ENCODING 'UTF8' LOCALE_PROVIDER icu ICU_LOCALE '{icu_locale}'"
        )
    _run(url, f"CREATE DATABASE {_checked(database)}{options}")


def drop_database(url: str, database: str) -> None:
    """Drop ``database``, disconnecting any session still in it; a missing one is not an error."""
    _run(url, f"DROP DATABASE IF EXISTS {_checked(database)} WITH (FORCE)")


def test_database_name(kind: str = "") -> str:
    """A unique throw-away database name that records its creation time.

    ``tl_pytest_<unix time, 8 hex>_<pid>_<6 hex>``, or ``tl_pytest_icu_...`` for ``kind="icu"``. The
    time and the creating process id let :func:`sweep_stale_databases` tell a crashed session's
    leftovers from a live one, even when that session holds no connection at the moment.
    """
    middle = f"{kind}_" if kind else ""
    stamp = f"{int(time.time()):08x}_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    return f"{TEST_DATABASE_PREFIX}{middle}{stamp}"


def _process_alive(pid: int) -> bool:
    """True when ``pid`` is a running process on this host (a signal-0 probe)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def sweep_stale_databases(url: str, *, older_than_s: float = 3 * 3600) -> list[str]:
    """Drop test databases left behind by crashed sessions; return their names.

    Only names made by :func:`test_database_name`, created more than ``older_than_s`` ago, with no
    connection open, and whose creating process (the pid in the name) is no longer running on this
    host are dropped, so another session's live database is never touched.
    """
    engine = create_engine(sqlalchemy_url(url), poolclass=NullPool, isolation_level="AUTOCOMMIT")
    dropped: list[str] = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT d.datname, s.numbackends FROM pg_database d "
                    "JOIN pg_stat_database s ON s.datname = d.datname "
                    "WHERE d.datname LIKE 'tl\\_pytest\\_%'"
                )
            ).all()
            for name, backends in rows:
                match = _TEST_DATABASE.match(str(name))
                if match is None or backends != 0:
                    continue
                if time.time() - int(match.group(1), 16) < older_than_s:
                    continue
                if _process_alive(int(match.group(2))):
                    continue
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
                dropped.append(str(name))
    finally:
        engine.dispose()
    return dropped
