"""The telemetry of needs (ADR-0028 decision 7): one append-only write path, no reader.

``note_need`` records that a need was shown, accepted, dismissed, expired or went unmet, into the
operational table ``telemetry_need`` (not in the ledger, the archive, the lake, the outbox, webhooks
or sync). It takes ids and words only: every text argument is checked against a closed set or a
fixed shape, and there is no parameter that could carry record text. It runs in a savepoint and
swallows a database error, so a refused write can never abort the caller's transaction. Reads of
Activity and Checks never call it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event
from tl_core.settings.resolver import value_of
from tl_core.util import new_ulid, utcnow

log = logging.getLogger(__name__)

REQUEST_KINDS: Final = ("check", "suggestion", "analysis", "ask")
OUTCOMES: Final = ("shown", "accepted", "dismissed", "expired", "unmet")
VIEWER_ROLES: Final = ("admin", "document_controller", "user", "unknown")
RETENTION_SETTING: Final = "telemetry.retention_days"
MAX_TRIGGER: Final = 80
_TRIGGER = re.compile(
    r"^(request|screen:insights\.[a-z_]{1,32}|event:[A-Za-z][A-Za-z0-9_.]{0,60})$"
)
_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,63}$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9_.-]{0,31}$")
_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

_INSERT = text(
    "INSERT INTO telemetry_need (row_id, need_id, scope, recorded_at, request_kind, trigger, "
    "record_type, record_id, viewer_role, provider_kind, duration_ms, outcome, why) "
    "VALUES (:row_id, :need_id, :scope, :at, :kind, :trigger, :rtype, :rid, :role, :provider, "
    ":ms, :outcome, NULL)"
)
_PRUNE = text("DELETE FROM telemetry_need WHERE recorded_at < :cutoff")


def role_word(roles: Sequence[str]) -> str:
    """The one role word a principal's roles give: the most powerful, ``unknown`` when none."""
    for word in VIEWER_ROLES[:-1]:
        if word in roles:
            return word
    return "unknown"


def _iso_z(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate(
    *,
    request_kind: str,
    trigger: str,
    record_type: str,
    viewer_role: str,
    outcome: str,
    record_id: str | None,
    provider_kind: str | None,
    duration_ms: int | None,
    need_id: str | None,
) -> None:
    if request_kind not in REQUEST_KINDS:
        raise ValueError(f"request_kind must be one of {', '.join(REQUEST_KINDS)}")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if viewer_role not in VIEWER_ROLES:
        raise ValueError(f"viewer_role must be one of {', '.join(VIEWER_ROLES)}")
    if len(trigger) > MAX_TRIGGER or not _TRIGGER.match(trigger):
        raise ValueError("trigger must be screen:insights.<subtab>, request or event:<type>")
    if not _TYPE.match(record_type):
        raise ValueError("record_type must be a record type name")
    if record_id is not None and not _ULID.match(record_id):
        raise ValueError("record_id must be a record id")
    if need_id is not None and not _ULID.match(need_id):
        raise ValueError("need_id must be an id")
    if provider_kind is not None and not _PROVIDER.match(provider_kind):
        raise ValueError("provider_kind must be a short word")
    if duration_ms is not None and not 0 <= duration_ms <= 86_400_000:
        raise ValueError("duration_ms must be between 0 and a day")
    if record_id is not None and trigger.startswith("screen:"):
        raise ValueError("a screen opening names no record")


def note_need(
    conn: Connection,
    *,
    request_kind: str,
    trigger: str,
    record_type: str,
    viewer_role: str,
    outcome: str,
    scope: str | None = None,
    record_id: str | None = None,
    provider_kind: str | None = None,
    duration_ms: int | None = None,
    need_id: str | None = None,
    now: datetime | None = None,
) -> None:
    """Append one row and prune the rows past retention, in one savepoint.

    Raises ``ValueError`` for a value outside the closed sets (a caller's bug, before any write).
    A database error is logged with a fixed code, never with row data, and swallowed: the caller's
    transaction stays usable on both dialects. ``why`` is always written null.
    """
    _validate(
        request_kind=request_kind,
        trigger=trigger,
        record_type=record_type,
        viewer_role=viewer_role,
        outcome=outcome,
        record_id=record_id,
        provider_kind=provider_kind,
        duration_ms=duration_ms,
        need_id=need_id,
    )
    moment = now if now is not None else utcnow()
    try:
        with conn.begin_nested():
            days = int(value_of(conn, RETENTION_SETTING))
            conn.execute(_PRUNE, {"cutoff": _iso_z(moment - timedelta(days=days))})
            conn.execute(
                _INSERT,
                {
                    "row_id": new_ulid(),
                    "need_id": need_id or new_ulid(),
                    "scope": scope,
                    "at": _iso_z(moment),
                    "kind": request_kind,
                    "trigger": trigger,
                    "rtype": record_type,
                    "rid": record_id,
                    "role": viewer_role,
                    "provider": provider_kind,
                    "ms": duration_ms,
                    "outcome": outcome,
                },
            )
    except SQLAlchemyError:
        log.warning("telemetry write failed", extra={"code": "telemetry_write_failed"})


class TelemetryStateTables:
    """``telemetry_need``, created with the rest of the schema and never reset by a rebuild.

    Not a projection: ``handles`` is empty, ``create_schema`` runs ``ddl``, ``apply`` is never
    called and ``reset`` leaves the rows alone (as ``WebhookStateTables`` and ``AuthStateTables``).
    """

    name = "telemetry_state"
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        if dialect != "sqlite" and dialect != "postgres":
            raise ValueError(f"unsupported dialect: {dialect}")
        return list(statements("telemetry_need", dialect))

    def apply(self, conn: Connection, event: Event) -> None:
        raise ValueError(f"{self.name} handles no events, got {event.event_type}")

    def reset(self, conn: Connection) -> None:
        """Deliberately empty: operational state is not rebuilt from the ledger."""
