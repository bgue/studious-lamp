"""PermitProjector: ``Permit.Requested`` and the events after it.

``Record.Created`` makes the envelope row (``RecordProjector``); ``Permit.Requested`` follows in
the same append and makes this module's row. The workflow state is the envelope ``status``. Who
did a step is the event's actor. ``Revalidated`` and ``Resumed`` set ``valid_until`` and clear
nothing else; ``Lapsed`` sets ``lapse_flagged_for`` and nothing else. The two link events change
no column but keep ``last_seq`` and the envelope in step.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_permits.names import (
    PERMIT_APPROVED,
    PERMIT_CANCELLED,
    PERMIT_CLOSED,
    PERMIT_EVENTS,
    PERMIT_HANDED_BACK,
    PERMIT_ISOLATION_LINKED,
    PERMIT_ISOLATION_UNLINKED,
    PERMIT_ISSUED,
    PERMIT_LAPSED,
    PERMIT_REJECTED,
    PERMIT_REQUESTED,
    PERMIT_RESUMED,
    PERMIT_REVALIDATED,
    PERMIT_SUSPENDED,
    PERMIT_TABLE,
    PERMIT_VIEW,
)
from tl_mod_permits.projectors._common import aware, ddl_for, dumps, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {PERMIT_TABLE} (id, scope, permit_type, for_record_id, area, location_text, "
    "holder, requested_by, needed_from, needed_until, precautions_json, revalidation_count, "
    "last_seq) "
    "VALUES (:id, :scope, :permit_type, :for_record_id, :area, :location_text, :holder, "
    ":requested_by, :needed_from, :needed_until, '[]', 0, :last_seq)"
)


def _set(sets: str) -> Any:
    return text(f"UPDATE {PERMIT_TABLE} SET {sets}, last_seq = :last_seq WHERE id = :id")


_APPROVE = _set("approved_by = :actor")
_REJECT = _set("reject_reason = :reason")
_ISSUE = _set(
    "issued_by = :actor, issued_at = :issued_at, valid_until = :valid_until, "
    "precautions_json = :precautions"
)
_REVALIDATE = _set(
    "valid_until = :valid_until, revalidation_count = revalidation_count + 1, "
    "last_revalidated_at = :at"
)
_SUSPEND = _set("suspend_reason = :reason")
_RESUME = _set("valid_until = :valid_until")
_HAND_BACK = _set("handback_note = :note")
_CLOSE = _set("closed_by = :actor")
_CANCEL = _set("cancel_reason = :reason")
_LAPSE = _set("lapse_flagged_for = :valid_until")
_TOUCH = text(f"UPDATE {PERMIT_TABLE} SET last_seq = :last_seq WHERE id = :id")


class PermitProjector:
    name = "permits_permit"
    handles = PERMIT_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(PERMIT_TABLE, dialect) + ddl_for(PERMIT_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == PERMIT_REQUESTED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "permit_type": payload["permit_type"],
                    "for_record_id": payload.get("for_record_id"),
                    "area": payload.get("area"),
                    "location_text": payload.get("location_text"),
                    "holder": payload.get("holder"),
                    "requested_by": event.actor,
                    "needed_from": payload.get("needed_from"),
                    "needed_until": payload.get("needed_until"),
                    "last_seq": event.seq,
                },
            )
        else:
            require_row(self._update(conn, event, payload), PERMIT_TABLE, event)
        touch_record(conn, event)

    @staticmethod
    def _update(conn: Connection, event: Event, payload: dict[str, Any]) -> int:
        kind = event.event_type
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        params: dict[str, Any]
        if kind == PERMIT_APPROVED:
            return conn.execute(_APPROVE, {**base, "actor": event.actor}).rowcount
        if kind == PERMIT_REJECTED:
            return conn.execute(_REJECT, {**base, "reason": payload["reason"]}).rowcount
        if kind == PERMIT_ISSUED:
            params = {
                "actor": event.actor,
                "issued_at": aware(payload["issued_at"]),
                "valid_until": aware(payload["valid_until"]),
                "precautions": dumps(payload["precautions"]),
            }
            return conn.execute(_ISSUE, {**base, **params}).rowcount
        if kind == PERMIT_REVALIDATED:
            params = {"valid_until": aware(payload["valid_until"]), "at": aware(payload["at"])}
            return conn.execute(_REVALIDATE, {**base, **params}).rowcount
        if kind == PERMIT_SUSPENDED:
            return conn.execute(_SUSPEND, {**base, "reason": payload["reason"]}).rowcount
        if kind == PERMIT_RESUMED:
            params = {"valid_until": aware(payload["valid_until"])}
            return conn.execute(_RESUME, {**base, **params}).rowcount
        if kind == PERMIT_HANDED_BACK:
            return conn.execute(_HAND_BACK, {**base, "note": payload["note"]}).rowcount
        if kind == PERMIT_CLOSED:
            return conn.execute(_CLOSE, {**base, "actor": event.actor}).rowcount
        if kind == PERMIT_CANCELLED:
            return conn.execute(_CANCEL, {**base, "reason": payload["reason"]}).rowcount
        if kind == PERMIT_LAPSED:
            params = {"valid_until": aware(payload["valid_until"])}
            return conn.execute(_LAPSE, {**base, **params}).rowcount
        if kind in (PERMIT_ISOLATION_LINKED, PERMIT_ISOLATION_UNLINKED):
            return conn.execute(_TOUCH, base).rowcount
        raise ValueError(f"PermitProjector cannot apply event type: {kind}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {PERMIT_TABLE}"))
