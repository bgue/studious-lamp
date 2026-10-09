"""Helpers to point a connection URL at one schema and to create or drop that schema.

A schema per test run (or per tenant) is how parity tests and local dev databases stay isolated
inside one Postgres database: every table, the ``events`` triggers and the functions live in the
schema the connection's ``search_path`` names.
"""

from __future__ import annotations

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from tl_adapters.postgres.engine import sqlalchemy_url

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
        "postgresql+psycopg://", "postgresql://"
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
        sqlalchemy_url(url), poolclass=NullPool, connect_args={"connect_timeout": timeout_s}
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
        "postgresql+psycopg://", "postgresql://"
    )


def create_database(url: str, database: str) -> None:
    """``CREATE DATABASE`` on the server ``url`` names."""
    _run(url, f"CREATE DATABASE {_checked(database)}")


def drop_database(url: str, database: str) -> None:
    """Drop ``database``, disconnecting any session still in it; a missing one is not an error."""
    _run(url, f"DROP DATABASE IF EXISTS {_checked(database)} WITH (FORCE)")
