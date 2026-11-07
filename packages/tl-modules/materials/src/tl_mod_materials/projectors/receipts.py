"""ReceiptProjector: ``Receipt.*`` into the receipt and receipt line tables.

``Defined`` inserts the receipt and its lines (``row_id`` is ``<receipt id>:<line no>``);
``Revised`` changes the fields it carries and, when it carries ``lines``, replaces the lines;
``Inspected`` and ``Rejected`` record who decided and when; ``Accepted`` sets ``lot_id`` on each
line and adds the lines' ``qty`` to the PO line's ``qty_received`` (a Void after Accepted is S3's).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_materials.common import ZERO, dec, num, parse_qty
from tl_mod_materials.names import (
    PO_LINE_TABLE,
    RECEIPT_ACCEPTED,
    RECEIPT_DEFINED,
    RECEIPT_INSPECTED,
    RECEIPT_LINE_TABLE,
    RECEIPT_REJECTED,
    RECEIPT_REVISED,
    RECEIPT_TABLE,
    RECEIPT_VIEW,
)
from tl_mod_materials.projectors._common import ddl_for, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {RECEIPT_TABLE} (id, scope, po_line_id, supplier_text, delivery_ref, "
    "received_on, location_id, last_seq) VALUES (:id, :scope, :po_line_id, :supplier_text, "
    ":delivery_ref, :received_on, :location_id, :last_seq)"
)
_INSERT_LINE = text(
    f"INSERT INTO {RECEIPT_LINE_TABLE} (row_id, scope, receipt_id, line_no, project_item_id, qty, "
    "uom, heat_no, condition, serials_text, lot_id, last_seq) VALUES (:row_id, :scope, "
    ":receipt_id, :line_no, :project_item_id, :qty, :uom, :heat_no, :condition, :serials_text, "
    ":lot_id, :last_seq)"
)
#: Revised fields that are plain columns of the receipt.
_REVISED = ("po_line_id", "supplier_text", "delivery_ref", "received_on", "location_id")
_LINE_QTYS = text(f"SELECT qty FROM {RECEIPT_LINE_TABLE} WHERE receipt_id = :id")
_PO_LINE_OF = text(f"SELECT po_line_id FROM {RECEIPT_TABLE} WHERE id = :id")
_PO_RECEIVED = text(f"SELECT qty_received FROM {PO_LINE_TABLE} WHERE id = :id")
_PO_SET = text(
    f"UPDATE {PO_LINE_TABLE} SET qty_received = :qty_received, last_seq = :last_seq WHERE id = :id"
)


def line_id(receipt_id: str, line_no: int) -> str:
    """``<receipt id>:<line no>``, the key of a receipt line row."""
    return f"{receipt_id}:{line_no}"


class ReceiptProjector:
    name = "materials_receipt"
    handles = frozenset(
        {RECEIPT_DEFINED, RECEIPT_REVISED, RECEIPT_INSPECTED, RECEIPT_ACCEPTED, RECEIPT_REJECTED}
    )

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(RECEIPT_TABLE, dialect)
            + ddl_for(RECEIPT_LINE_TABLE, dialect)
            + ddl_for(RECEIPT_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == RECEIPT_DEFINED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "po_line_id": payload.get("po_line_id"),
                    "supplier_text": payload["supplier_text"],
                    "delivery_ref": payload.get("delivery_ref"),
                    "received_on": payload["received_on"],
                    "location_id": payload["location_id"],
                    "last_seq": event.seq,
                },
            )
            self._lines(conn, event, payload["lines"])
        elif kind == RECEIPT_REVISED:
            self._revise(conn, event, payload)
        elif kind == RECEIPT_INSPECTED:
            self._set(
                conn,
                event,
                {"inspected_by": payload["inspected_by"], "inspected_on": payload["inspected_on"]},
            )
        elif kind == RECEIPT_REJECTED:
            self._set(
                conn,
                event,
                {
                    "decided_by": payload["decided_by"],
                    "decided_on": payload["decided_on"],
                    "rejection_reason": payload["reason"],
                },
            )
        elif kind == RECEIPT_ACCEPTED:
            self._set(
                conn,
                event,
                {"decided_by": payload["decided_by"], "decided_on": payload["decided_on"]},
            )
            self._accept(conn, event, payload["lots"])
        else:
            raise ValueError(f"ReceiptProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    @staticmethod
    def _set(conn: Connection, event: Event, values: dict[str, Any]) -> None:
        sets = ", ".join(f"{column} = :{column}" for column in values)
        done = conn.execute(
            text(f"UPDATE {RECEIPT_TABLE} SET {sets}, last_seq = :last_seq WHERE id = :id"),
            {**values, "id": event.stream_id, "last_seq": event.seq},
        )
        require_row(done.rowcount, RECEIPT_TABLE, event)

    def _revise(self, conn: Connection, event: Event, payload: dict[str, Any]) -> None:
        self._set(conn, event, {f: payload[f] for f in _REVISED if f in payload})
        if "lines" in payload:
            conn.execute(
                text(f"DELETE FROM {RECEIPT_LINE_TABLE} WHERE receipt_id = :id"),
                {"id": event.stream_id},
            )
            self._lines(conn, event, payload["lines"])

    @staticmethod
    def _lines(conn: Connection, event: Event, lines: list[dict[str, Any]]) -> None:
        for line in lines:
            conn.execute(
                _INSERT_LINE,
                {
                    "row_id": line_id(event.stream_id, int(line["line_no"])),
                    "scope": event.scope,
                    "receipt_id": event.stream_id,
                    "line_no": int(line["line_no"]),
                    "project_item_id": line["project_item_id"],
                    "qty": num(parse_qty(line["qty"])),
                    "uom": line["uom"],
                    "heat_no": line.get("heat_no"),
                    "condition": line["condition"],
                    "serials_text": line.get("serials_text"),
                    "lot_id": None,
                    "last_seq": event.seq,
                },
            )

    @staticmethod
    def _accept(conn: Connection, event: Event, lots: list[dict[str, Any]]) -> None:
        for lot in lots:
            conn.execute(
                text(
                    f"UPDATE {RECEIPT_LINE_TABLE} SET lot_id = :lot_id, last_seq = :last_seq "
                    "WHERE receipt_id = :id AND line_no = :line_no"
                ),
                {
                    "lot_id": lot["lot_id"],
                    "last_seq": event.seq,
                    "id": event.stream_id,
                    "line_no": int(lot["line"]),
                },
            )
        po_line = conn.execute(_PO_LINE_OF, {"id": event.stream_id}).scalar_one_or_none()
        if po_line is None:
            return
        received = sum(
            (dec(q) for q in conn.execute(_LINE_QTYS, {"id": event.stream_id}).scalars()), ZERO
        )
        held = conn.execute(_PO_RECEIVED, {"id": po_line}).scalar_one_or_none()
        if held is None:
            raise LookupError(f"no {PO_LINE_TABLE} row for the receipt's PO line")
        conn.execute(
            _PO_SET,
            {"id": po_line, "qty_received": num(dec(held) + received), "last_seq": event.seq},
        )

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {RECEIPT_LINE_TABLE}"))
        conn.execute(text(f"DELETE FROM {RECEIPT_TABLE}"))
