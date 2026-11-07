"""Projector of the scope items: ``cur_awp_scope_item``. ``ScopeItem.Created`` inserts the row."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_awp.names import SCOPE_ITEM_CREATED, SCOPE_ITEM_TABLE, SCOPE_ITEM_VIEW
from tl_mod_awp.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {SCOPE_ITEM_TABLE} (id, scope, commodity, description_text, qty, uom, "
    "est_hours, cwp_id, last_seq) VALUES (:id, :scope, :commodity, :description, :qty, :uom, "
    ":est_hours, :cwp_id, :last_seq)"
)


class ScopeItemProjector:
    name = "awp_scope_item"
    handles = frozenset({SCOPE_ITEM_CREATED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(SCOPE_ITEM_TABLE, dialect) + ddl_for(SCOPE_ITEM_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != SCOPE_ITEM_CREATED:
            raise ValueError(f"ScopeItemProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        conn.execute(
            _INSERT_SQL,
            {
                "id": event.stream_id,
                "scope": event.scope,
                "commodity": payload["commodity"],
                "description": payload.get("description"),
                "qty": payload.get("qty"),
                "uom": payload.get("uom"),
                "est_hours": payload.get("est_hours"),
                "cwp_id": payload.get("cwp_id"),
                "last_seq": event.seq,
            },
        )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {SCOPE_ITEM_TABLE}"))


def scope_item_projectors() -> list[ScopeItemProjector]:
    return [ScopeItemProjector()]
