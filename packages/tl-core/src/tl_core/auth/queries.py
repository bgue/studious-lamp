"""Reads of accounts and agent tokens (ADR-0009). Plain SQL on the projections; no secrets."""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import Connection, text

from tl_core.auth._time import Clock, iso_z
from tl_core.auth.errors import AccountNotFoundError
from tl_core.auth.names import actor_for, username_key
from tl_core.auth.types import (
    DEMO_USERNAME,
    AccountKind,
    AccountStatus,
    AccountView,
    AgentTokenView,
    Role,
)
from tl_core.util import utcnow

_ACCOUNT_SELECT = (
    "SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, "
    "a.created_at, a.last_seq, t.locked_until FROM cur_account a "
    "LEFT JOIN auth_attempt t ON t.username_key = a.username AND t.locked_until > :now "
)


def load_roles(value: Any) -> list[Role]:
    """The roles column as a list: SQLite returns JSON text, Postgres JSONB returns a list."""
    raw: Any = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    items = cast("list[Any]", raw) if isinstance(raw, list) else []
    return [cast(Role, str(r)) for r in items if str(r) in ("admin", "user")]


def account_view(row: Any) -> AccountView:
    return AccountView(
        account_id=str(row["account_id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        kind=cast(AccountKind, str(row["kind"])),
        roles=load_roles(row["roles_json"]),
        status=cast(AccountStatus, str(row["status"])),
        locked_until=None if row["locked_until"] is None else str(row["locked_until"]),
        created_at=str(row["created_at"]),
        seq=int(row["last_seq"]),
    )


def list_accounts(conn: Connection, *, clock: Clock = utcnow) -> list[AccountView]:
    """Every account, oldest first, with the lock that is in force now."""
    rows = conn.execute(
        text(_ACCOUNT_SELECT + "ORDER BY a.created_at, a.account_id"), {"now": iso_z(clock())}
    ).mappings()
    return [account_view(row) for row in rows]


def find_account(
    conn: Connection, *, account_id: str | None = None, username: str | None = None
) -> AccountView | None:
    """One account by id or by (normalised) username, or ``None``."""
    if (account_id is None) == (username is None):
        raise ValueError("give exactly one of account_id and username")
    if account_id is not None:
        where, value = "a.account_id = :v", account_id
    else:
        where, value = "a.username = :v", username_key(str(username))
    row = (
        conn.execute(text(_ACCOUNT_SELECT + "WHERE " + where), {"now": iso_z(utcnow()), "v": value})
        .mappings()
        .first()
    )
    return None if row is None else account_view(row)


def get_account(conn: Connection, account_id: str) -> AccountView:
    found = find_account(conn, account_id=account_id)
    if found is None:
        raise AccountNotFoundError(f"no account {account_id}")
    return found


def token_view(row: Any) -> AgentTokenView:
    return AgentTokenView(
        token_id=str(row["token_id"]),
        account_id=str(row["account_id"]),
        label=str(row["label"]),
        expires_at=None if row["expires_at"] is None else str(row["expires_at"]),
        revoked=bool(row["revoked"]),
        issued_by=str(row["issued_by"]),
    )


def list_agent_tokens(
    conn: Connection, *, account_id: str | None = None, include_revoked: bool = True
) -> list[AgentTokenView]:
    """Agent token metadata, oldest first. The tokens themselves cannot be read back."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if account_id is not None:
        clauses.append("account_id = :a")
        params["a"] = account_id
    if not include_revoked:
        clauses.append("revoked = 0")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        text(
            "SELECT token_id, account_id, label, expires_at, revoked, issued_by FROM "
            f"cur_agent_token{where} ORDER BY issued_at, token_id"
        ),
        params,
    ).mappings()
    return [token_view(row) for row in rows]


def count_active_admins(conn: Connection) -> int:
    row = conn.execute(
        text("SELECT COUNT(*) FROM cur_account WHERE is_admin = 1 AND status = 'active'")
    ).scalar_one()
    return int(row)


def demo_account_enabled(conn: Connection) -> bool:
    """Whether the seeded ``demo`` account exists and is enabled (checked when a server starts)."""
    row = conn.execute(
        text("SELECT status FROM cur_account WHERE username = :u"), {"u": DEMO_USERNAME}
    ).first()
    return row is not None and str(row[0]) == "active"


def actor_of(view: AccountView) -> str:
    return actor_for(view.kind, view.username)
