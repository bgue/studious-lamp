"""IntakeCodeProjector: ``Issued`` inserts the row, ``Revoked`` sets the revoke fields."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_forms.names import (
    INTAKE_CODE_EVENTS,
    INTAKE_CODE_ISSUED,
    INTAKE_CODE_TABLE,
    INTAKE_CODE_VIEW,
)
from tl_mod_forms.projectors._common import ddl_for, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {INTAKE_CODE_TABLE} (id, scope, code_hash, template_id, template_version, "
    "template_hash, context_id, context_type, heading, controller_role, issued_by, issued_at, "
    "expires_on, last_seq) VALUES (:id, :scope, :code_hash, :template_id, :template_version, "
    ":template_hash, :context_id, :context_type, :heading, :controller_role, :issued_by, "
    ":issued_at, :expires_on, :last_seq)"
)
_REVOKE = text(
    f"UPDATE {INTAKE_CODE_TABLE} SET revoked_at = :revoked_at, revoked_by = :revoked_by, "
    "last_seq = :last_seq WHERE id = :id"
)


class IntakeCodeProjector:
    name = "forms_intake_code"
    handles = INTAKE_CODE_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(INTAKE_CODE_TABLE, dialect) + ddl_for(INTAKE_CODE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == INTAKE_CODE_ISSUED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code_hash": payload["code_hash"],
                    "template_id": payload["template_id"],
                    "template_version": payload["template_version"],
                    "template_hash": payload["template_hash"],
                    "context_id": payload["context_id"],
                    "context_type": payload["context_type"],
                    "heading": payload["heading"],
                    "controller_role": payload["controller_role"],
                    "issued_by": event.actor,
                    "issued_at": stamp,
                    "expires_on": payload["expires_on"],
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
                    "last_seq": event.seq,
                },
            )
            require_row(done.rowcount, INTAKE_CODE_TABLE, event)
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {INTAKE_CODE_TABLE}"))
