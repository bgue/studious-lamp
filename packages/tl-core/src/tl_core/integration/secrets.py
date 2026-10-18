"""Signing secrets of inbound endpoints and webhook actions (FANOUT D4, D8; ADR-0017).

A secret lives in the operational table ``int_secret`` and nowhere else: the ledger, the logs, error
texts, API answers and the dev query tools never carry it. An event names ``secret_id``. The text of
a new secret is returned **once**, to the caller that created or rotated it (:class:`IssuedSecret`,
whose ``repr`` hides it); it cannot be read back.

The format is the Standard Webhooks one of the outbound side (``whsec_`` plus the base64 of 32
random bytes), made by ``tl_core.webhooks.signing.generate_secret``, so one verifier serves both
directions.

**Rotation.** ``rotate_secret`` issues a new secret and lets the previous one keep verifying (or
signing) for ``overlap_hours``, at most ``MAX_OVERLAP_HOURS``. A secret that already had an expiry
was rotated out before and is retired at once, so at most two secrets are live. A restore from the
archive does not bring this table back: a restored ledger re-issues its secrets (runbook).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Connection, text

from tl_core.integration.errors import InvalidIntegrationError
from tl_core.util import new_ulid
from tl_core.webhooks.base import iso_z
from tl_core.webhooks.signing import SigningSecret, generate_secret

OwnerKind = Literal["inbound", "action"]
MAX_OVERLAP_HOURS = 24.0
DEFAULT_OVERLAP_HOURS = 24.0

_INSERT = text(
    "INSERT INTO int_secret (secret_id, owner_kind, owner_id, secret, state, created_at) "
    "VALUES (:secret_id, :owner_kind, :owner_id, :secret, 'active', :now)"
)
_LIVE = text(
    "SELECT secret_id, secret FROM int_secret WHERE owner_kind = :kind AND owner_id = :owner "
    "AND state = 'active' AND (expires_at IS NULL OR expires_at > :now) "
    "ORDER BY created_at DESC, secret_id DESC"
)


@dataclass(frozen=True)
class IssuedSecret:
    """A secret as shown once. ``repr`` and ``str`` hide the text."""

    secret_id: str
    secret: str = field(repr=False)

    def __repr__(self) -> str:
        return f"IssuedSecret(secret_id={self.secret_id!r}, secret=<hidden>)"

    __str__ = __repr__


@dataclass(frozen=True)
class Rotation:
    """What a rotation did: the new secret (shown once) and what became of the previous one."""

    issued: IssuedSecret
    previous_secret_id: str | None
    previous_expires_at: str | None


def issue_secret(
    conn: Connection, kind: OwnerKind, owner_id: str, *, now: datetime
) -> IssuedSecret:
    """Make the first secret of an owner (or one more; see :func:`rotate_secret`)."""
    secret_id, secret = new_ulid(), generate_secret()
    conn.execute(
        _INSERT,
        {
            "secret_id": secret_id,
            "owner_kind": kind,
            "owner_id": owner_id,
            "secret": secret,
            "now": iso_z(now),
        },
    )
    return IssuedSecret(secret_id=secret_id, secret=secret)


def rotate_secret(
    conn: Connection,
    kind: OwnerKind,
    owner_id: str,
    *,
    now: datetime,
    overlap_hours: float = DEFAULT_OVERLAP_HOURS,
) -> Rotation:
    """Issue a new secret; the live one keeps working for ``overlap_hours`` (0 to 24)."""
    if not 0 <= overlap_hours <= MAX_OVERLAP_HOURS:
        raise InvalidIntegrationError(f"the overlap is 0 to {MAX_OVERLAP_HOURS:g} hours")
    expiry = iso_z(now + timedelta(hours=overlap_hours))
    params = {"kind": kind, "owner": owner_id}
    conn.execute(
        text(
            "UPDATE int_secret SET state = 'retired' WHERE owner_kind = :kind "
            "AND owner_id = :owner AND state = 'active' AND expires_at IS NOT NULL"
        ),
        params,
    )
    previous = conn.execute(
        text(
            "SELECT secret_id FROM int_secret WHERE owner_kind = :kind AND owner_id = :owner "
            "AND state = 'active' AND expires_at IS NULL"
        ),
        params,
    ).first()
    conn.execute(
        text(
            "UPDATE int_secret SET expires_at = :expiry WHERE owner_kind = :kind "
            "AND owner_id = :owner AND state = 'active' AND expires_at IS NULL"
        ),
        {**params, "expiry": expiry},
    )
    issued = issue_secret(conn, kind, owner_id, now=now)
    return Rotation(
        issued=issued,
        previous_secret_id=None if previous is None else str(previous.secret_id),
        previous_expires_at=None if previous is None else expiry,
    )


def live_secrets(
    conn: Connection, kind: OwnerKind, owner_id: str, *, now: datetime
) -> list[SigningSecret]:
    """The secrets that sign or verify now, newest first: active and not past their expiry.

    A secret whose text is not a valid ``whsec_`` value is skipped (it cannot verify anything)
    rather than raised, so one bad row never decides an answer.
    """
    found = conn.execute(_LIVE, {"kind": kind, "owner": owner_id, "now": iso_z(now)})
    secrets: list[SigningSecret] = []
    for row in found:
        try:
            secrets.append(SigningSecret(str(row.secret)))
        except ValueError:
            continue
    return secrets


def owner_of(conn: Connection, secret_id: str) -> tuple[str, str] | None:
    """``(kind, owner id)`` of a secret, or ``None``. For a caller that holds only ``secret_id``."""
    row = conn.execute(
        text("SELECT owner_kind, owner_id FROM int_secret WHERE secret_id = :s"), {"s": secret_id}
    ).first()
    return None if row is None else (str(row.owner_kind), str(row.owner_id))
