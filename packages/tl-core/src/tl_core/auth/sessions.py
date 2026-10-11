"""Sign-in, sessions, bearer resolution and lockout (ADR-0009 sections 4, 6 and 7).

Sign-in runs in three steps so the slow hash never holds a write transaction:

1. a read snapshot: is the name locked, and what are the account and its stored hash;
2. outside any transaction: one full scrypt (against a dummy when there is no usable hash);
3. a short write transaction: record the failure, or clear the counters and create the session.

A failure is raised **after** the write transaction has committed, because an exception inside a
unit of work rolls it back and the counter would be lost.
"""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol, cast

from sqlalchemy import Connection, text

from tl_core.auth import password as pw
from tl_core.auth._time import Clock, iso_z
from tl_core.auth.accounts import change_password, clear_lockout
from tl_core.auth.errors import (
    AccountDisabledError,
    AccountLockedError,
    InvalidCredentialsError,
)
from tl_core.auth.names import actor_for, normalize_username, username_key
from tl_core.auth.queries import load_roles
from tl_core.auth.tokens import new_session_token, token_hash, token_kind
from tl_core.auth.types import AccountKind, Principal
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

log = logging.getLogger("tl_core.auth")

SESSION_TTL = timedelta(hours=12)
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCK_BASE = timedelta(minutes=15)
LOCK_CAP = timedelta(hours=24)
LEVEL_MEMORY = timedelta(hours=24)


class UowFactory(Protocol):
    """What a server or a CLI call holds: ``factory(readonly)`` opens an entered unit of work."""

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...


@dataclass(frozen=True)
class _Account:
    account_id: str
    username: str
    kind: AccountKind
    roles_json: Any
    status: str
    password_hash: str | None


def principal_of(
    account_id: str, username: str, kind: AccountKind, roles_json: Any, via: str
) -> Principal:
    return Principal(
        actor=actor_for(kind, username),
        account_id=account_id,
        kind=kind,
        roles=load_roles(roles_json),
        via=cast(Any, via),
    )


# --- lockout --------------------------------------------------------------------------------


def lock_duration(level: int) -> timedelta:
    """15 minutes for the first lock, doubling each time, capped at 24 hours."""
    return min(LOCK_BASE * (2 ** min(level, 16)), LOCK_CAP)


def locked_until(conn: Connection, key: str, now: datetime) -> str | None:
    """The end of the lock on ``key`` if one is in force at ``now``."""
    found = conn.execute(
        text("SELECT locked_until FROM auth_attempt WHERE username_key = :k"), {"k": key}
    ).scalar()
    if found is not None and str(found) > iso_z(now):
        return str(found)
    return None


def record_failure(conn: Connection, key: str, now: datetime) -> None:
    """Count one failed sign-in for ``key``, locking it at the threshold. Prunes stale rows."""
    stamp = iso_z(now)
    conn.execute(
        text(
            "DELETE FROM auth_attempt WHERE last_failed_at < :cutoff "
            "AND (locked_until IS NULL OR locked_until < :now)"
        ),
        {"cutoff": iso_z(now - LEVEL_MEMORY), "now": stamp},
    )
    row = (
        conn.execute(
            text(
                "SELECT failed_count, window_started_at, last_failed_at, lock_level "
                "FROM auth_attempt WHERE username_key = :k"
            ),
            {"k": key},
        )
        .mappings()
        .first()
    )
    if row is None:
        conn.execute(
            text(
                "INSERT INTO auth_attempt (username_key, failed_count, window_started_at, "
                "last_failed_at, lock_level, locked_until) VALUES (:k, 1, :t, :t, 0, NULL)"
            ),
            {"k": key, "t": stamp},
        )
        return
    count, window, level = (
        int(row["failed_count"]),
        str(row["window_started_at"]),
        int(row["lock_level"]),
    )
    if window < iso_z(now - FAILURE_WINDOW):
        count, window = 0, stamp
    if str(row["last_failed_at"]) < iso_z(now - LEVEL_MEMORY):
        level = 0
    count += 1
    until: str | None = None
    if count >= MAX_FAILURES:
        until = iso_z(now + lock_duration(level))
        count, window, level = 0, stamp, level + 1
    conn.execute(
        text(
            "UPDATE auth_attempt SET failed_count = :c, window_started_at = :w, "
            "last_failed_at = :t, lock_level = :l, locked_until = :u WHERE username_key = :k"
        ),
        {"c": count, "w": window, "t": stamp, "l": level, "u": until, "k": key},
    )


# --- sign-in --------------------------------------------------------------------------------


def _load_account(conn: Connection, name: str) -> _Account | None:
    row = (
        conn.execute(
            text(
                "SELECT a.account_id, a.username, a.kind, a.roles_json, a.status, "
                "c.password_hash FROM cur_account a "
                "LEFT JOIN auth_credential c ON c.account_id = a.account_id "
                "WHERE a.username = :u"
            ),
            {"u": name},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return _Account(
        account_id=str(row["account_id"]),
        username=str(row["username"]),
        kind=cast(AccountKind, str(row["kind"])),
        roles_json=row["roles_json"],
        status=str(row["status"]),
        password_hash=None if row["password_hash"] is None else str(row["password_hash"]),
    )


def _locked(until: str) -> AccountLockedError:
    return AccountLockedError(f"too many failed sign-ins; try again after {until}", until)


def authenticate(
    backend: UowFactory,
    username: str,
    password: str,
    *,
    with_session: bool,
    clock: Clock = utcnow,
) -> tuple[Principal, str | None]:
    """Check a username and password; optionally open a session. See the module docstring."""
    key = username_key(username)
    name = normalize_username(username)
    now = clock()
    with backend(readonly=True) as uow:
        conn = uow.conn()
        until = locked_until(conn, key, now)
        account = None if until is not None else _load_account(conn, name)
    if until is not None:
        raise _locked(until)
    usable = account is not None and account.kind != "agent"
    stored = account.password_hash if account is not None and usable else None
    good = pw.verify_password(stored, password)  # always one full scrypt
    session: str | None = None
    failure: Exception | None = None
    principal: Principal | None = None
    with backend() as uow:
        conn = uow.conn()
        now = clock()
        until = locked_until(conn, key, now)
        if until is not None:
            failure = _locked(until)
        elif not good or account is None:
            record_failure(conn, key, now)
            failure = InvalidCredentialsError()
        elif account.status != "active":
            failure = AccountDisabledError("the account is disabled")
        else:
            clear_lockout(conn, key)
            via = "session" if with_session else "password"
            principal = principal_of(
                account.account_id, account.username, account.kind, account.roles_json, via
            )
            if with_session:
                session = new_session_token()
                conn.execute(
                    text("DELETE FROM auth_session WHERE account_id = :a AND expires_at < :now"),
                    {"a": account.account_id, "now": iso_z(now)},
                )
                conn.execute(
                    text(
                        "INSERT INTO auth_session (token_hash, account_id, created_at, expires_at) "
                        "VALUES (:h, :a, :c, :e)"
                    ),
                    {
                        "h": token_hash(session),
                        "a": account.account_id,
                        "c": iso_z(now),
                        "e": iso_z(now + SESSION_TTL),
                    },
                )
            if account.password_hash is not None and pw.needs_rehash(account.password_hash):
                _rehash(conn, account.account_id, account.password_hash, password, now)
    if failure is not None:
        raise failure
    assert principal is not None
    return principal, session


def _rehash(conn: Connection, account_id: str, old: str, password: str, now: datetime) -> None:
    """Replace a hash made with weaker parameters. A concurrent change of the hash wins."""
    conn.execute(
        text(
            "UPDATE auth_credential SET password_hash = :new, updated_at = :t "
            "WHERE account_id = :a AND password_hash = :old"
        ),
        {"new": pw.hash_password(password), "t": iso_z(now), "a": account_id, "old": old},
    )


def sign_in(
    backend: UowFactory, *, username: str, password: str, clock: Clock = utcnow
) -> tuple[Principal, str]:
    """Sign in with a username and password. Returns the principal and the session token (once)."""
    principal, session = authenticate(backend, username, password, with_session=True, clock=clock)
    assert session is not None
    return principal, session


def sign_out(backend: UowFactory, *, token: str) -> None:
    """End the session of ``token``. Unknown tokens are ignored (sign-out is idempotent)."""
    if token_kind(token) != "session":
        return
    with backend() as uow:
        uow.conn().execute(
            text("DELETE FROM auth_session WHERE token_hash = :h"), {"h": token_hash(token)}
        )


def sign_out_all(backend: UowFactory, *, account_id: str) -> None:
    """End every session of an account."""
    with backend() as uow:
        uow.conn().execute(
            text("DELETE FROM auth_session WHERE account_id = :a"), {"a": account_id}
        )


# --- bearer tokens --------------------------------------------------------------------------

_SESSION_SQL = text(
    "SELECT a.account_id, a.username, a.kind, a.roles_json, a.status, s.expires_at "
    "FROM auth_session s JOIN cur_account a ON a.account_id = s.account_id "
    "WHERE s.token_hash = :h"
)
_AGENT_SQL = text(
    "SELECT a.account_id, a.username, a.kind, a.roles_json, a.status, t.expires_at, t.revoked "
    "FROM auth_token_secret k JOIN cur_agent_token t ON t.token_id = k.token_id "
    "JOIN cur_account a ON a.account_id = t.account_id WHERE k.token_hash = :h"
)


def principal_for_bearer(backend: UowFactory, token: str, *, clock: Clock = utcnow) -> Principal:
    """The principal of a session or agent token, or ``InvalidCredentialsError`` for any bad one."""
    kind = token_kind(token)
    if kind is None:
        raise InvalidCredentialsError("invalid or expired token")
    now = iso_z(clock())
    with backend(readonly=True) as uow:
        row = (
            uow.conn()
            .execute(_SESSION_SQL if kind == "session" else _AGENT_SQL, {"h": token_hash(token)})
            .mappings()
            .first()
        )
    expires = None if row is None else row["expires_at"]
    bad = (
        row is None
        or row["status"] != "active"
        or (expires is not None and str(expires) <= now)
        or (kind == "agent" and int(row["revoked"]) == 1)
    )
    if bad or row is None:
        raise InvalidCredentialsError("invalid or expired token")
    via = "session" if kind == "session" else "agent_token"
    return principal_of(
        str(row["account_id"]),
        str(row["username"]),
        cast(AccountKind, str(row["kind"])),
        row["roles_json"],
        via,
    )


# --- changing one's own password ------------------------------------------------------------


def change_own_password(
    backend: UowFactory,
    *,
    account_id: str,
    current_password: str,
    new_password: str,
    clock: Clock = utcnow,
) -> None:
    """A signed-in person changes their password. Wrong current passwords count towards lockout."""
    with backend(readonly=True) as uow:
        row = (
            uow.conn()
            .execute(
                text(
                    "SELECT a.username, a.kind, c.password_hash FROM cur_account a "
                    "LEFT JOIN auth_credential c ON c.account_id = a.account_id "
                    "WHERE a.account_id = :a"
                ),
                {"a": account_id},
            )
            .mappings()
            .first()
        )
    if row is None or row["kind"] == "agent":
        raise InvalidCredentialsError("the current password is incorrect")
    username, kind = str(row["username"]), cast(AccountKind, str(row["kind"]))
    key = username_key(username)
    with backend(readonly=True) as uow:
        until = locked_until(uow.conn(), key, clock())
    if until is not None:
        raise _locked(until)
    stored = None if row["password_hash"] is None else str(row["password_hash"])
    if not pw.verify_password(stored, current_password):
        with backend() as uow:
            record_failure(uow.conn(), key, clock())
        raise InvalidCredentialsError("the current password is incorrect")
    with backend() as uow:
        change_password(
            uow,
            account_id=account_id,
            new_password=new_password,
            by=actor_for(kind, username),
            current_password=current_password,
            clock=clock,
        )
