"""IntakeItemProjector: ``Received`` inserts, ``Accepted``, ``Rejected`` and ``Purged`` set fields.

It creates ``cur_forms_intake_item`` and also the operational table ``forms_intake_body``, so both
exist in one schema. It never writes or clears ``forms_intake_body``: a rebuild resets the item
rows only, and the received text stays until the purge job removes it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_forms.names import (
    INTAKE_BODY_TABLE,
    INTAKE_ITEM_ACCEPTED,
    INTAKE_ITEM_EVENTS,
    INTAKE_ITEM_PURGED,
    INTAKE_ITEM_RECEIVED,
    INTAKE_ITEM_REJECTED,
    INTAKE_ITEM_TABLE,
    INTAKE_ITEM_VIEW,
)
from tl_mod_forms.projectors._common import (
    day_of,
    ddl_for,
    dump_json,
    require_row,
    touch_record,
)

_INSERT = text(
    f"INSERT INTO {INTAKE_ITEM_TABLE} (id, scope, code_id, template_id, template_version, "
    "template_hash, body_mac, body_bytes, received_at, last_seq) VALUES (:id, :scope, :code_id, "
    ":template_id, :template_version, :template_hash, :body_mac, :body_bytes, :received_at, "
    ":last_seq)"
)
_ACCEPT = text(
    f"UPDATE {INTAKE_ITEM_TABLE} SET accepted_as = :accepted_as, accepted_by = :by, "
    "accepted_on = :on, on_behalf_of_claim_json = :claim, last_seq = :last_seq WHERE id = :id"
)
_REJECT = text(
    f"UPDATE {INTAKE_ITEM_TABLE} SET rejected_reason = :reason, rejected_by = :by, "
    "last_seq = :last_seq WHERE id = :id"
)
_PURGE = text(
    f"UPDATE {INTAKE_ITEM_TABLE} SET purged_at = :at, last_seq = :last_seq WHERE id = :id"
)


class IntakeItemProjector:
    name = "forms_intake_item"
    handles = INTAKE_ITEM_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(INTAKE_ITEM_TABLE, dialect)
            + ddl_for(INTAKE_ITEM_VIEW, dialect)
            + ddl_for(INTAKE_BODY_TABLE, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        if kind == INTAKE_ITEM_RECEIVED:
            conn.execute(
                _INSERT,
                {
                    **base,
                    "scope": event.scope,
                    "code_id": payload["code_id"],
                    "template_id": payload["template_id"],
                    "template_version": payload["template_version"],
                    "template_hash": payload["template_hash"],
                    "body_mac": payload["body_mac"],
                    "body_bytes": payload["body_bytes"],
                    "received_at": payload["received_at"],
                },
            )
        else:
            if kind == INTAKE_ITEM_ACCEPTED:
                done = conn.execute(
                    _ACCEPT,
                    {
                        **base,
                        "accepted_as": payload["accepted_as"],
                        "by": event.actor,
                        "on": day_of(event),
                        "claim": dump_json(payload.get("on_behalf_of_claim")),
                    },
                )
            elif kind == INTAKE_ITEM_REJECTED:
                done = conn.execute(
                    _REJECT, {**base, "reason": payload["reason"], "by": event.actor}
                )
            elif kind == INTAKE_ITEM_PURGED:
                done = conn.execute(_PURGE, {**base, "at": payload["purged_at"]})
            else:
                raise ValueError(f"IntakeItemProjector cannot apply event type: {kind}")
            require_row(done.rowcount, INTAKE_ITEM_TABLE, event)
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        """Clears the item rows only: operational ``forms_intake_body`` survives a rebuild."""
        conn.execute(text(f"DELETE FROM {INTAKE_ITEM_TABLE}"))
