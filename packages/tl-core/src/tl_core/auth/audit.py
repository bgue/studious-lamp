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

from tl_core.auth import names
from tl_core.auth._time import Clock, iso_z
from tl_core.auth.errors import InvalidAccountError
from tl_core.util import new_ulid, utcnow

RETENTION = timedelta(days=90)
#: Repeated failures of one name within this long share one row with a count.
COLLAPSE_WINDOW = timedelta(minutes=15)
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
    count: int = 1


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
    if event == "sign_in_failed" and username_key is not None and detail is not None:
        latest = conn.execute(
            text(
                "SELECT audit_id, at FROM auth_audit WHERE username_key = :k AND event = :e "
                "AND detail = :d ORDER BY at DESC, audit_id DESC LIMIT 1"
            ),
            {"k": username_key, "e": event, "d": detail},
        ).first()
        if latest is not None and str(latest[1]) >= iso_z(now - COLLAPSE_WINDOW):
            conn.execute(
                text("UPDATE auth_audit SET count = count + 1, at = :at WHERE audit_id = :i"),
                {"at": iso_z(now), "i": latest[0]},
            )
            return
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
    if event is not None and event not in EVENTS:
        raise InvalidAccountError(f"unknown audit event; one of {', '.join(EVENTS)}")
    clauses = ["at >= :since"]
    params: dict[str, Any] = {"since": iso_z(clock() - RETENTION), "n": limit}
    if event is not None:
        clauses.append("event = :e")
        params["e"] = event
    if username_key is not None:
        clauses.append("username_key = :k")
        params["k"] = names.username_key(username_key)
    rows = conn.execute(
        text(
            "SELECT audit_id, at, event, username_key, account_id, actor, detail, count "
            "FROM auth_audit "
            f"WHERE {' AND '.join(clauses)} ORDER BY at DESC, audit_id DESC LIMIT :n"
        ),
        params,
    ).all()

    def text_or_none(value: Any) -> str | None:
        return None if value is None else str(value)

    return [
        AuditEntry(
            audit_id=str(r[0]),
            at=str(r[1]),
            event=str(r[2]),
            username_key=text_or_none(r[3]),
            account_id=text_or_none(r[4]),
            actor=text_or_none(r[5]),
            detail=text_or_none(r[6]),
            count=int(r[7]),
        )
        for r in rows
    ]
