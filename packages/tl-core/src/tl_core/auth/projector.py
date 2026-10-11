"""Projectors for accounts (ADR-0009): ``Account.*`` and ``AgentToken.*`` events into two tables.

``cur_account`` and ``cur_agent_token`` are rebuilt from the ledger like any projection. They hold
no secret: a password hash, a session or agent token hash and the failed-sign-in counters live in
the ``auth_*`` operational tables, which no event produces and a rebuild never clears (they ride on
:class:`AuthStateTables`, a projector that handles no event, like ``WebhookStateTables``).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.auth._time import iso_z
from tl_core.auth.types import (
    ACCOUNT_CREATED,
    ACCOUNT_DISABLED,
    ACCOUNT_ENABLED,
    ACCOUNT_PASSWORD_CHANGED,
    ACCOUNT_ROLES_SET,
    AGENT_TOKEN_ISSUED,
    AGENT_TOKEN_REVOKED,
)
from tl_core.ledger import Event

ACCOUNT_STREAM_TYPE = "core.Account"
ACCOUNT_STREAM_PREFIX = "account:"
ACCOUNT_EVENT_TYPES = frozenset(
    {
        ACCOUNT_CREATED,
        ACCOUNT_ROLES_SET,
        ACCOUNT_DISABLED,
        ACCOUNT_ENABLED,
        ACCOUNT_PASSWORD_CHANGED,
        AGENT_TOKEN_ISSUED,
        AGENT_TOKEN_REVOKED,
    }
)
OPERATIONAL_TABLES = (
    "auth_credential",
    "auth_session",
    "auth_token_secret",
    "auth_attempt",
)


def account_stream_id(account_id: str) -> str:
    return f"{ACCOUNT_STREAM_PREFIX}{account_id}"


def _roles_json(roles: Any) -> str:
    return json.dumps(sorted({str(r) for r in roles}), separators=(",", ":"))


_INSERT_ACCOUNT = text(
    "INSERT INTO cur_account (account_id, username, display_name, kind, roles_json, is_admin, "
    "status, created_by, created_at, updated_at, version, last_seq) VALUES (:account_id, "
    ":username, :display_name, :kind, :roles_json, :is_admin, 'active', :created_by, :stamp, "
    ":stamp, :version, :last_seq)"
)
_INSERT_TOKEN = text(
    "INSERT INTO cur_agent_token (token_id, account_id, label, expires_at, revoked, issued_by, "
    "issued_at, last_seq) VALUES (:token_id, :account_id, :label, :expires_at, 0, :issued_by, "
    ":stamp, :last_seq)"
)


class AccountProjector:
    name = "accounts"
    handles = ACCOUNT_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_account", dialect) + statements("cur_agent_token", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_agent_token"))
        conn.execute(text("DELETE FROM cur_account"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type not in ACCOUNT_EVENT_TYPES:
            raise ValueError(f"AccountProjector cannot apply: {event.event_type}")
        payload = event.payload
        account_id = str(payload["account_id"])
        if event.stream_id != account_stream_id(account_id):
            raise ValueError(f"{event.event_type} is on stream {event.stream_id}, not its account")
        stamp = iso_z(event.recorded_at)
        if event.event_type == ACCOUNT_CREATED:
            roles = payload["roles"]
            conn.execute(
                _INSERT_ACCOUNT,
                {
                    "account_id": account_id,
                    "username": payload["username"],
                    "display_name": payload["display_name"],
                    "kind": payload["kind"],
                    "roles_json": _roles_json(roles),
                    "is_admin": 1 if "admin" in roles else 0,
                    "created_by": event.actor,
                    "stamp": stamp,
                    "version": event.stream_version,
                    "last_seq": event.seq,
                },
            )
            return
        changes: dict[str, Any] = {}
        if event.event_type == ACCOUNT_ROLES_SET:
            roles = payload["roles"]
            changes = {"roles_json": _roles_json(roles), "is_admin": 1 if "admin" in roles else 0}
        elif event.event_type == ACCOUNT_DISABLED:
            changes = {"status": "disabled"}
        elif event.event_type == ACCOUNT_ENABLED:
            changes = {"status": "active"}
        elif event.event_type == AGENT_TOKEN_ISSUED:
            conn.execute(
                _INSERT_TOKEN,
                {
                    "token_id": payload["token_id"],
                    "account_id": account_id,
                    "label": payload["label"],
                    "expires_at": payload.get("expires_at"),
                    "issued_by": event.actor,
                    "stamp": stamp,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == AGENT_TOKEN_REVOKED:
            conn.execute(
                text(
                    "UPDATE cur_agent_token SET revoked = 1, revoked_at = :stamp, "
                    "revoke_reason = :reason, last_seq = :seq WHERE token_id = :token_id"
                ),
                {
                    "stamp": stamp,
                    "reason": payload.get("reason"),
                    "seq": event.seq,
                    "token_id": payload["token_id"],
                },
            )
        # Every event bumps the account's version, last_seq and updated_at; the column names
        # below are fixed here, never taken from event data.
        assignments = "".join(f"{column} = :{column}, " for column in changes)
        updated = conn.execute(
            text(
                f"UPDATE cur_account SET {assignments}updated_at = :stamp, version = :version, "
                "last_seq = :last_seq WHERE account_id = :account_id"
            ),
            {
                **changes,
                "stamp": stamp,
                "version": event.stream_version,
                "last_seq": event.seq,
                "account_id": account_id,
            },
        )
        if updated.rowcount == 0:
            raise LookupError(f"no account row for stream {event.stream_id}")


class AuthStateTables:
    """The operational tables of authentication, created with the rest of the schema.

    ``handles`` is empty: ``create_schema`` runs ``ddl`` and ``apply`` is never called. ``reset``
    leaves the data alone, because a hash, a session or a lockout cannot be derived from events.
    """

    name = "auth_state"
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        if dialect != "sqlite" and dialect != "postgres":
            raise ValueError(f"unsupported dialect: {dialect}")
        found: list[str] = []
        for table in OPERATIONAL_TABLES:
            found.extend(statements(table, dialect))
        return found

    def apply(self, conn: Connection, event: Event) -> None:
        raise ValueError(f"{self.name} handles no events, got {event.event_type}")

    def reset(self, conn: Connection) -> None:
        """Deliberately empty: operational state is not rebuilt from the ledger."""
