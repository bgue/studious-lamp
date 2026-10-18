"""The ``query_db`` SQL guard: one SELECT (or WITH ... SELECT) on a SQLite dev database.

Postgres is not supported by ``query_db`` in Phase 0 (deviation C4). A deny-list of Postgres
functions cannot be complete: functions such as ``ts_stat`` and ``ts_rewrite`` run a SQL string
on the server, so a denied name split with ``||`` (``'pg_re' || 'ad_file'``) escapes any screen of
the statement text, and the dev Postgres URL is the superuser. A safe Postgres ``query_db`` needs a
non-superuser reader role *and* a function allow-list; both are a follow-up. ``check_select``
refuses a Postgres target with that message.

For SQLite the text check here only gives a clear message early. The strict layers are SQLite's own:
``execute`` accepts one statement, the connection is ``mode=ro`` with ``PRAGMA query_only``, and the
authoriser in :mod:`tl_mcp.dev.query` allows only SELECT, reads of non-secret columns, and functions
outside a short deny-list (SQLite has no function that runs SQL text; ``load_extension`` is off).
"""

from __future__ import annotations

import re

from tl_lake.guard import MAX_SQL_CHARS

from tl_mcp.dev.errors import DevGuardError

CREDENTIAL_TABLES = frozenset(
    {"auth_credential", "auth_session", "auth_token_secret", "auth_attempt", "auth_audit"}
)
"""Operational tables of authentication (ADR-0009): password hashes, session and agent token
hashes and the failed-sign-in counters."""
DENIED_TABLES = frozenset({"wh_secret", "int_secret"}) | CREDENTIAL_TABLES
"""Tables no dev tool may read: webhook signing secrets live in ``wh_secret.secret``, the inbound
and action secrets of the integration layer in ``int_secret.secret``."""

POSTGRES_REFUSAL = (
    "query_db reads SQLite dev databases only in Phase 0: a Postgres reader needs a non-superuser "
    "role and a function allow-list (follow-up, deviation C4)"
)


def _common_checks(sql: str) -> None:
    if not sql.strip():
        raise DevGuardError("the statement is empty")
    if len(sql) > MAX_SQL_CHARS:
        raise DevGuardError(f"the statement is longer than {MAX_SQL_CHARS} characters")
    if "\x00" in sql:
        raise DevGuardError("the statement contains a NUL character")


_LEADING_NOISE = re.compile(r"\A(?:\s+|--[^\n]*(?:\n|\Z)|/\*.*?\*/)*", re.DOTALL)


def check_sqlite_select(sql: str) -> None:
    """Refuse text that is not a single SELECT or WITH statement.

    This is a pre-check for a clear message. The strict layers are SQLite's one-statement rule for
    ``execute``, the read-only connection and the authoriser in :mod:`tl_mcp.dev.query`.
    """
    _common_checks(sql)
    body = sql[_LEADING_NOISE.match(sql).end() :]  # type: ignore[union-attr]
    keyword = re.match(r"[A-Za-z]+", body)
    if keyword is None or keyword.group(0).lower() not in ("select", "with"):
        raise DevGuardError("only a single SELECT (or WITH ... SELECT) statement is allowed")
    if re.search(r"wh_secret", sql, re.IGNORECASE):
        raise DevGuardError("wh_secret holds signing secrets and cannot be read")
    if re.search(r"int_secret", sql, re.IGNORECASE):
        raise DevGuardError("int_secret holds signing secrets and cannot be read")
    for table in sorted(CREDENTIAL_TABLES):
        if re.search(table, sql, re.IGNORECASE):
            raise DevGuardError(f"{table} holds credentials and cannot be read")


def check_select(sql: str, dialect: str) -> None:
    """Dispatch on the dialect of the dev target: ``sqlite`` is checked, ``postgres`` is refused."""
    if dialect == "sqlite":
        check_sqlite_select(sql)
    elif dialect == "postgres":
        raise DevGuardError(POSTGRES_REFUSAL)
    else:
        raise DevGuardError(f"unknown dialect {dialect!r}")
