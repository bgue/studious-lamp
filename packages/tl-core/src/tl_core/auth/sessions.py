"""Sign-in, sessions, bearer resolution and lockout (ADR-0009 sections 4, 6 and 7).

Sign-in runs in three steps so the slow hash never holds a write transaction:

1. a read snapshot: is the name locked, and what are the account and its stored hash;
2. outside any transaction: one full scrypt (against a random salt when there is no usable hash),
   and the new hash too when the stored one is weaker than the current cost;
3. a short write transaction: record the failure, or clear the counters and create the session.

A failure is raised **after** the write transaction has committed, because an exception inside a
unit of work rolls it back and the counter would be lost. Input that cannot be hashed or stored (a
NUL, a lone surrogate, too long) is invalid credentials after the same scrypt and writes nothing.
"""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol, cast

from sqlalchemy import Connection, text

from tl_core.auth import audit
from tl_core.auth import password as pw
from tl_core.auth._time import Clock, iso_z
from tl_core.auth.accounts import change_password, clear_lockout
from tl_core.auth.env import current_env, demo_allowed
from tl_core.auth.errors import (
    AccountDisabledError,
    AccountLockedError,
    InvalidCredentialsError,
)
from tl_core.auth.names import actor_for, username_key
from tl_core.auth.queries import load_roles
from tl_core.auth.tokens import new_session_token, token_hash, token_kind
from tl_core.auth.types import DEMO_USERNAME, AccountKind, Principal
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

log = logging.getLogger("tl_core.auth")

SESSION_TTL = timedelta(hours=12)
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
#: Every lock lasts this long, for every name. A longer lock for some names (the admins, or after
#: repeated locks) would tell an attacker which names exist, so there is no doubling (ADR-0009).
LOCK_DURATION = timedelta(minutes=15)
#: Counter rows with no failure for this long, and no lock in force, are deleted.
PRUNE_AFTER = timedelta(hours=1)
MAX_USERNAME_INPUT = 256


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


def demo_usable(username: str) -> bool:
    """The seeded ``demo`` account authenticates only where ``TL_ENV`` allows it (ADR-0008 D4)."""
    return username != DEMO_USERNAME or demo_allowed(current_env())


# --- lockout --------------------------------------------------------------------------------


def locked_until(conn: Connection, key: str, now: datetime) -> str | None:
    """The end of the lock on ``key`` if one is in force at ``now``."""
    found = conn.execute(
        text("SELECT locked_until FROM auth_attempt WHERE username_key = :k"), {"k": key}
    ).scalar()
    if found is not None and str(found) > iso_z(now):
        return str(found)
    return None


def record_failure(conn: Connection, key: str, now: datetime) -> str | None:
    """Count one failed sign-in for ``key``, locking it at the threshold; the lock's end or None.

    Prunes stale rows. The audit row for the failure is the caller's.
    """
    stamp = iso_z(now)
    conn.execute(
        text(
            "DELETE FROM auth_attempt WHERE last_failed_at < :cutoff "
            "AND (locked_until IS NULL OR locked_until < :now)"
        ),
        {"cutoff": iso_z(now - PRUNE_AFTER), "now": stamp},
    )
    row = (
        conn.execute(
            text(
                "SELECT failed_count, window_started_at FROM auth_attempt WHERE username_key = :k"
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
                "last_failed_at, locked_until) VALUES (:k, 1, :t, :t, NULL)"
            ),
            {"k": key, "t": stamp},
        )
        return None
    count, window = int(row["failed_count"]), str(row["window_started_at"])
    if window < iso_z(now - FAILURE_WINDOW):
        count, window = 0, stamp
    count += 1
    until: str | None = None
    if count >= MAX_FAILURES:
        until = iso_z(now + LOCK_DURATION)
        count, window = 0, stamp
    conn.execute(
        text(
            "UPDATE auth_attempt SET failed_count = :c, window_started_at = :w, "
            "last_failed_at = :t, locked_until = :u WHERE username_key = :k"
        ),
        {"c": count, "w": window, "t": stamp, "u": until, "k": key},
    )
    return until


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
    if not (pw.is_clean(username, MAX_USERNAME_INPUT) and pw.is_clean(password, 4 * pw.MAX_LENGTH)):
        pw.verify_password(None, "")  # the same cost as any other failure; nothing is written
        raise InvalidCredentialsError()
    key = username_key(username)  # INVALID_KEY for anything that cannot be a username
    now = clock()
    with backend(readonly=True) as uow:
        conn = uow.conn()
        until = locked_until(conn, key, now)
        account = None if until is not None else _load_account(conn, key)
    if until is not None:
        raise _locked(until)
    usable = account is not None and account.kind != "agent" and demo_usable(account.username)
    stored = account.password_hash if account is not None and usable else None
    good = pw.verify_password(stored, password)  # always one full scrypt
    new_hash = (  # computed here, not in the write transaction below
        pw.hash_password(password)
        if good and stored is not None and pw.needs_rehash(stored)
        else None
    )
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
            lock = record_failure(conn, key, now)
            audit.record(
                conn, "sign_in_failed", now=now, username_key=key, detail="bad_credentials"
            )
            if lock is not None:
                audit.record(conn, "locked", now=now, username_key=key, detail=lock)
            failure = InvalidCredentialsError()
        elif account.status != "active":
            audit.record(
                conn,
                "sign_in_failed",
                now=now,
                username_key=key,
                account_id=account.account_id,
                detail="disabled",
            )
            failure = AccountDisabledError("the account is disabled")
        else:
            clear_lockout(conn, key)
            via = "session" if with_session else "password"
            principal = principal_of(
                account.account_id, account.username, account.kind, account.roles_json, via
            )
            audit.record(
                conn,
                "sign_in_ok",
                now=now,
                username_key=key,
                account_id=account.account_id,
                actor=principal.actor,
                detail=via,
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
            if new_hash is not None and account.password_hash is not None:
                _rehash(conn, account.account_id, account.password_hash, new_hash, now)
    if failure is not None:
        raise failure
    assert principal is not None
    return principal, session


def _rehash(conn: Connection, account_id: str, old: str, new: str, now: datetime) -> None:
    """Replace a hash made with weaker parameters. A concurrent change of the hash wins."""
    conn.execute(
        text(
            "UPDATE auth_credential SET password_hash = :new, updated_at = :t "
            "WHERE account_id = :a AND password_hash = :old"
        ),
        {"new": new, "t": iso_z(now), "a": account_id, "old": old},
    )


def sign_in(
    backend: UowFactory, *, username: str, password: str, clock: Clock = utcnow
) -> tuple[Principal, str]:
    """Sign in with a username and password. Returns the principal and the session token (once)."""
    principal, session = authenticate(backend, username, password, with_session=True, clock=clock)
    assert session is not None
    return principal, session


def sign_out(backend: UowFactory, *, token: str, clock: Clock = utcnow) -> None:
    """End the session of ``token``. Unknown tokens are ignored (sign-out is idempotent)."""
    if token_kind(token) != "session":
        return
    with backend() as uow:
        conn = uow.conn()
        found = conn.execute(
            text("SELECT account_id FROM auth_session WHERE token_hash = :h"),
            {"h": token_hash(token)},
        ).scalar()
        if found is None:
            return
        conn.execute(
            text("DELETE FROM auth_session WHERE token_hash = :h"), {"h": token_hash(token)}
        )
        audit.record(conn, "sign_out", now=clock(), account_id=str(found))


def sign_out_all(backend: UowFactory, *, account_id: str) -> None:
    """End every session of an account."""
    with backend() as uow:
        uow.conn().execute(
            text("DELETE FROM auth_session WHERE account_id = :a"), {"a": account_id}
        )


# --- bearer tokens --------------------------------------------------------------------------

#: Sessions belong to people and simulator accounts; agents authenticate by token only.
_SESSION_SQL = text(
    "SELECT a.account_id, a.username, a.kind, a.roles_json, a.status, s.expires_at "
    "FROM auth_session s JOIN cur_account a ON a.account_id = s.account_id "
    "WHERE s.token_hash = :h AND a.kind <> 'agent'"
)
_AGENT_SQL = text(
    "SELECT a.account_id, a.username, a.kind, a.roles_json, a.status, t.expires_at, t.revoked "
    "FROM auth_token_secret k JOIN cur_agent_token t ON t.token_id = k.token_id "
    "JOIN cur_account a ON a.account_id = t.account_id "
    "WHERE k.token_hash = :h AND a.kind = 'agent'"
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
    bad = (
        row is None
        or row["status"] != "active"
        or (row["expires_at"] is not None and str(row["expires_at"]) <= now)
        or (kind == "agent" and int(row["revoked"]) == 1)
        or not demo_usable(str(row["username"]))
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
    """A signed-in person changes their password. Wrong current passwords count towards lockout.

    The current password is checked and the new one hashed before the write transaction opens.
    """
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
        pw.verify_password(None, "")
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
            now = clock()
            lock = record_failure(uow.conn(), key, now)
            audit.record(
                uow.conn(), "sign_in_failed", now=now, username_key=key, detail="password_change"
            )
            if lock is not None:
                audit.record(uow.conn(), "locked", now=now, username_key=key, detail=lock)
        raise InvalidCredentialsError("the current password is incorrect")
    prepared = pw.prepare_password(new_password, username=username, public=True)
    with backend() as uow:
        change_password(
            uow,
            account_id=account_id,
            new_password=prepared,
            by=actor_for(kind, username),
            clock=clock,
        )
