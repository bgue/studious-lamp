"""LotProjector: ``StockLot.Defined`` into ``cur_materials_lot``.

``issued_net`` starts at zero; the movement projector (``projectors/stock.py``) moves it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_materials.common import ZERO, num
from tl_mod_materials.names import LOT_DEFINED, LOT_TABLE, LOT_VIEW
from tl_mod_materials.projectors._common import ddl_for, touch_record

_INSERT = text(
    f"INSERT INTO {LOT_TABLE} (id, scope, project_item_id, heat_no, receipt_id, receipt_line, "
    "uom, issued_net, last_seq) VALUES (:id, :scope, :project_item_id, :heat_no, :receipt_id, "
    ":receipt_line, :uom, :issued_net, :last_seq)"
)


class LotProjector:
    name = "materials_lot"
    handles = frozenset({LOT_DEFINED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(LOT_TABLE, dialect) + ddl_for(LOT_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != LOT_DEFINED:
            raise ValueError(f"LotProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        conn.execute(
            _INSERT,
            {
                "id": event.stream_id,
                "scope": event.scope,
                "project_item_id": payload["project_item_id"],
                "heat_no": payload.get("heat_no"),
                "receipt_id": payload["receipt_id"],
                "receipt_line": int(payload["receipt_line"]),
                "uom": payload["uom"],
                "issued_net": num(ZERO),
                "last_seq": event.seq,
            },
        )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {LOT_TABLE}"))
