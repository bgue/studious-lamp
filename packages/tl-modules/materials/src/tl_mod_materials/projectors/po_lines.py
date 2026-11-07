"""PoLineProjector: ``POLineRef.*`` into ``cur_materials_po_line``.

``Defined`` inserts the mirror row with ``qty_received`` at zero; ``Updated`` changes the promised
date and the quantity ordered, whichever the payload carries. ``qty_received`` is moved by
``Receipt.Accepted`` (``projectors/receipts.py``), never here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_materials.common import ZERO, num, parse_qty
from tl_mod_materials.names import (
    PO_LINE_DEFINED,
    PO_LINE_TABLE,
    PO_LINE_UPDATED,
    PO_LINE_VIEW,
)
from tl_mod_materials.projectors._common import ddl_for, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {PO_LINE_TABLE} (id, scope, po_number, line_no, project_item_id, qty_ordered, "
    "uom, promised_date, supplier_text, qty_received, last_seq) VALUES (:id, :scope, :po_number, "
    ":line_no, :project_item_id, :qty_ordered, :uom, :promised_date, :supplier_text, "
    ":qty_received, :last_seq)"
)


class PoLineProjector:
    name = "materials_po_line"
    handles = frozenset({PO_LINE_DEFINED, PO_LINE_UPDATED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(PO_LINE_TABLE, dialect) + ddl_for(PO_LINE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == PO_LINE_DEFINED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "po_number": payload["po_number"],
                    "line_no": int(payload["line_no"]),
                    "project_item_id": payload["project_item_id"],
                    "qty_ordered": num(parse_qty(payload["qty_ordered"])),
                    "uom": payload["uom"],
                    "promised_date": payload.get("promised_date"),
                    "supplier_text": payload.get("supplier_text") or "",
                    "qty_received": num(ZERO),
                    "last_seq": event.seq,
                },
            )
        elif kind == PO_LINE_UPDATED:
            sets = ["last_seq = :last_seq"]
            params: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
            if "promised_date" in payload:
                sets.append("promised_date = :promised_date")
                params["promised_date"] = payload["promised_date"]
            if "qty_ordered" in payload:
                sets.append("qty_ordered = :qty_ordered")
                params["qty_ordered"] = num(parse_qty(payload["qty_ordered"]))
            done = conn.execute(
                text(f"UPDATE {PO_LINE_TABLE} SET {', '.join(sets)} WHERE id = :id"), params
            )
            require_row(done.rowcount, PO_LINE_TABLE, event)
        else:
            raise ValueError(f"PoLineProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {PO_LINE_TABLE}"))
