"""ScanCodeProjector: ``ScanCode.Issued`` inserts, ``ScanCode.Revoked`` sets the revoke fields."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_qr.names import (
    DEFAULT_SIZE,
    SCAN_CODE_EVENTS,
    SCAN_CODE_ISSUED,
    SCAN_CODE_TABLE,
    SCAN_CODE_VIEW,
)
from tl_mod_qr.projectors._common import ddl_for, touch_record

_INSERT = text(
    f"INSERT INTO {SCAN_CODE_TABLE} (id, scope, code_hash, target_id, target_type, label_text, "
    "size, issued_by, issued_at, expires_on, last_seq) VALUES (:id, :scope, :code_hash, "
    ":target_id, :target_type, :label_text, :size, :issued_by, :issued_at, :expires_on, :last_seq)"
)
_REVOKE = text(
    f"UPDATE {SCAN_CODE_TABLE} SET revoked_at = :revoked_at, revoked_by = :revoked_by, "
    "revoke_reason = :reason, replaced_by_id = :replaced_by_id, last_seq = :last_seq WHERE id = :id"
)


class ScanCodeProjector:
    name = "qr_scan_code"
    handles = SCAN_CODE_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(SCAN_CODE_TABLE, dialect) + ddl_for(SCAN_CODE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == SCAN_CODE_ISSUED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code_hash": payload["code_hash"],
                    "target_id": payload["target_id"],
                    "target_type": payload["target_type"],
                    "label_text": payload.get("label_text"),
                    "size": payload.get("size") or DEFAULT_SIZE,
                    "issued_by": event.actor,
                    "issued_at": stamp,
                    "expires_on": payload.get("expires_on"),
                    "last_seq": event.seq,
                },
            )
        else:
            done = conn.execute(
                _REVOKE,
                {
                    "id": event.stream_id,
                    "revoked_at": stamp,
                    "revoked_by": event.actor,
                    "reason": payload["reason"],
                    "replaced_by_id": payload.get("replaced_by_id"),
                    "last_seq": event.seq,
                },
            )
            if done.rowcount == 0:
                raise LookupError(f"no {SCAN_CODE_TABLE} row for stream {event.stream_id}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {SCAN_CODE_TABLE}"))
