"""The operational audit of authentication (ADR-0009 section 12): who signed in, failed, locked.

Rows live in ``auth_audit``, an operational table: not in the ledger, the archive or the lake, kept
90 days. A row never holds a password, a hash or a token; ``detail`` is a short code or an id.
``username_key`` is the name the attempt used, whether or not such an account exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text

from tl_core.auth._time import Clock, iso_z
from tl_core.util import new_ulid, utcnow

RETENTION = timedelta(days=90)
EVENTS = (
    "sign_in_ok",
    "sign_in_failed",
    "locked",
    "unlocked",
    "sign_out",
    "token_issued",
    "token_revoked",
    "password_reset",
    "bootstrap",
)
MAX_DETAIL = 200


@dataclass(frozen=True)
class AuditEntry:
    audit_id: str
    at: str
    event: str
    username_key: str | None
    account_id: str | None
    actor: str | None
    detail: str | None


def record(
    conn: Connection,
    event: str,
    *,
    now: datetime,
    username_key: str | None = None,
    account_id: str | None = None,
    actor: str | None = None,
    detail: str | None = None,
) -> None:
    """Write one row (in the caller's transaction) and drop the rows past retention."""
    if event not in EVENTS:
        raise ValueError(f"unknown audit event {event!r}")
    conn.execute(
        text("DELETE FROM auth_audit WHERE at < :cutoff"), {"cutoff": iso_z(now - RETENTION)}
    )
    conn.execute(
        text(
            "INSERT INTO auth_audit (audit_id, at, event, username_key, account_id, actor, detail) "
            "VALUES (:i, :at, :e, :k, :a, :actor, :d)"
        ),
        {
            "i": new_ulid(),
            "at": iso_z(now),
            "e": event,
            "k": username_key,
            "a": account_id,
            "actor": actor,
            "d": None if detail is None else detail[:MAX_DETAIL],
        },
    )


def list_audit(
    conn: Connection,
    *,
    limit: int = 100,
    event: str | None = None,
    username_key: str | None = None,
    clock: Clock = utcnow,
) -> list[AuditEntry]:
    """The newest ``limit`` rows, newest first, optionally of one event or one name."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    clauses = ["at >= :since"]
    params: dict[str, Any] = {"since": iso_z(clock() - RETENTION), "n": limit}
    if event is not None:
        clauses.append("event = :e")
        params["e"] = event
    if username_key is not None:
        clauses.append("username_key = :k")
        params["k"] = username_key
    rows = conn.execute(
        text(
            "SELECT audit_id, at, event, username_key, account_id, actor, detail FROM auth_audit "
            f"WHERE {' AND '.join(clauses)} ORDER BY at DESC, audit_id DESC LIMIT :n"
        ),
        params,
    ).all()
    return [AuditEntry(*(None if v is None else str(v) for v in row)) for row in rows]  # type: ignore[arg-type]
