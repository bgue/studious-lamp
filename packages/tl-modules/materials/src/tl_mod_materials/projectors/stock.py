"""StockProjector: ``StockLot.Moved`` into the movement log, the balances and the reservations.

One event, eight kinds (ADR-0022). Each event writes one ``cur_materials_movement`` row (``seq`` is
the event's) and moves the balances:

=========  ==============================================================================
receive    ``+to`` on hand
issue      ``-from`` on hand; the reservation of ``mto_line_id`` at ``from`` is consumed first
           (reservation, ``stock.reserved`` and the line's ``reserved_qty`` fall by the part
           consumed); the line's ``issued_qty`` and the lot's ``issued_net`` rise by ``qty``
return     ``+to`` on hand; the lot's ``issued_net`` falls
transfer   ``-from``, ``+to`` on hand; ``reserved`` stays where it is
adjust     ``direction`` ``in``: ``+to``; ``out``: ``-from`` on hand
scrap      ``-from`` on hand
reserve    ``+reserved`` at ``from``; the reservation row and the line's ``reserved_qty`` rise
unreserve  the inverse of reserve
=========  ==============================================================================

``available`` is written with ``on_hand`` and ``reserved`` (``on_hand - reserved``). All arithmetic
is ``Decimal`` (3 places); a stock row at zero on hand and zero reserved, and a reservation at zero,
are deleted in the same write. A movement that would make a balance negative is a broken stream
(the commands check first), so it raises and the append is rolled back.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_materials.common import ZERO, dec, num, parse_qty
from tl_mod_materials.names import (
    ADJUST,
    ISSUE,
    LOT_MOVED,
    LOT_TABLE,
    MOVEMENT_TABLE,
    MTO_LINE_TABLE,
    RECEIVE,
    RESERVATION_TABLE,
    RESERVE,
    RETURN,
    SCRAP,
    STOCK_TABLE,
    TRANSFER,
    UNRESERVE,
)
from tl_mod_materials.projectors._common import ddl_for, require_row, touch_record

_MOVEMENT = text(
    f"INSERT INTO {MOVEMENT_TABLE} (seq, scope, lot_id, kind, qty, uom, direction, "
    "from_location_id, to_location_id, cost_code_id, mto_line_id, iwp_id, requisition_id, "
    "person, reason, actor, recorded_at, correlation_id) VALUES (:seq, :scope, :lot_id, :kind, "
    ":qty, :uom, :direction, :from_location_id, :to_location_id, :cost_code_id, :mto_line_id, "
    ":iwp_id, :requisition_id, :person, :reason, :actor, :recorded_at, :correlation_id)"
)
_STOCK = text(
    f"SELECT on_hand, reserved FROM {STOCK_TABLE} WHERE lot_id = :lot_id AND location_id = :loc"
)
_STOCK_INSERT = text(
    f"INSERT INTO {STOCK_TABLE} (scope, lot_id, location_id, on_hand, reserved, available) "
    "VALUES (:scope, :lot_id, :loc, :on_hand, :reserved, :available)"
)
_STOCK_UPDATE = text(
    f"UPDATE {STOCK_TABLE} SET on_hand = :on_hand, reserved = :reserved, available = :available "
    "WHERE lot_id = :lot_id AND location_id = :loc"
)
_STOCK_DELETE = text(f"DELETE FROM {STOCK_TABLE} WHERE lot_id = :lot_id AND location_id = :loc")
_RESERVATION = text(
    f"SELECT qty FROM {RESERVATION_TABLE} "
    "WHERE lot_id = :lot_id AND location_id = :loc AND mto_line_id = :line"
)
_RESERVATION_INSERT = text(
    f"INSERT INTO {RESERVATION_TABLE} (scope, lot_id, location_id, mto_line_id, qty) "
    "VALUES (:scope, :lot_id, :loc, :line, :qty)"
)
_RESERVATION_UPDATE = text(
    f"UPDATE {RESERVATION_TABLE} SET qty = :qty "
    "WHERE lot_id = :lot_id AND location_id = :loc AND mto_line_id = :line"
)
_RESERVATION_DELETE = text(
    f"DELETE FROM {RESERVATION_TABLE} "
    "WHERE lot_id = :lot_id AND location_id = :loc AND mto_line_id = :line"
)
_LINE = text(f"SELECT reserved_qty, issued_qty FROM {MTO_LINE_TABLE} WHERE id = :id")
_LINE_SET = text(
    f"UPDATE {MTO_LINE_TABLE} SET reserved_qty = :reserved, issued_qty = :issued, "
    "last_seq = :last_seq WHERE id = :id"
)
_LOT = text(f"SELECT issued_net FROM {LOT_TABLE} WHERE id = :id")
_LOT_SET = text(
    f"UPDATE {LOT_TABLE} SET issued_net = :issued_net, last_seq = :last_seq WHERE id = :id"
)


def _where(payload: dict[str, Any], key: str, kind: str) -> str:
    found = payload.get(key)
    if not found:
        raise ValueError(f"a {kind} movement needs {key}")
    return str(found)


class StockProjector:
    name = "materials_stock"
    handles = frozenset({LOT_MOVED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(MOVEMENT_TABLE, dialect)
            + ddl_for(STOCK_TABLE, dialect)
            + ddl_for(RESERVATION_TABLE, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != LOT_MOVED:
            raise ValueError(f"StockProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        kind = str(payload["kind"])
        qty = parse_qty(payload["qty"])
        conn.execute(
            _MOVEMENT,
            {
                "seq": event.seq,
                "scope": event.scope,
                "lot_id": event.stream_id,
                "kind": kind,
                "qty": num(qty),
                "uom": payload["uom"],
                "direction": payload.get("direction"),
                "from_location_id": payload.get("from_location_id"),
                "to_location_id": payload.get("to_location_id"),
                "cost_code_id": payload.get("cost_code_id"),
                "mto_line_id": payload.get("mto_line_id"),
                "iwp_id": payload.get("iwp_id"),
                "requisition_id": payload.get("requisition_id"),
                "person": payload.get("person"),
                "reason": payload.get("reason"),
                "actor": event.actor,
                "recorded_at": iso_utc(event.recorded_at),
                "correlation_id": event.correlation_id,
            },
        )
        self._move(conn, event, kind, qty)
        touch_record(conn, event)

    # --- the eight kinds -------------------------------------------------------------------

    def _move(self, conn: Connection, event: Event, kind: str, qty: Decimal) -> None:
        p: dict[str, Any] = event.payload
        lot = event.stream_id
        scope = event.scope
        if kind == RECEIVE:
            self._on_hand(conn, scope, lot, _where(p, "to_location_id", kind), qty)
        elif kind == ISSUE:
            where = _where(p, "from_location_id", kind)
            line = p.get("mto_line_id")
            consumed = self._consume(conn, event, scope, lot, where, line, qty)
            self._stock(conn, scope, lot, where, on_hand=-qty, reserved=-consumed)
            if line:
                self._line(conn, event, str(line), reserved=-consumed, issued=qty)
            self._issued_net(conn, event, qty)
        elif kind == RETURN:
            self._on_hand(conn, scope, lot, _where(p, "to_location_id", kind), qty)
            self._issued_net(conn, event, -qty)
        elif kind == TRANSFER:
            self._on_hand(conn, scope, lot, _where(p, "from_location_id", kind), -qty)
            self._on_hand(conn, scope, lot, _where(p, "to_location_id", kind), qty)
        elif kind == ADJUST:
            if p.get("direction") == "in":
                self._on_hand(conn, scope, lot, _where(p, "to_location_id", kind), qty)
            elif p.get("direction") == "out":
                self._on_hand(conn, scope, lot, _where(p, "from_location_id", kind), -qty)
            else:
                raise ValueError("an adjust movement needs direction in or out")
        elif kind == SCRAP:
            self._on_hand(conn, scope, lot, _where(p, "from_location_id", kind), -qty)
        elif kind in (RESERVE, UNRESERVE):
            sign = 1 if kind == RESERVE else -1
            where = _where(p, "from_location_id", kind)
            line = _where(p, "mto_line_id", kind)
            self._stock(conn, scope, lot, where, on_hand=ZERO, reserved=sign * qty)
            self._reservation(conn, scope, lot, where, line, sign * qty)
            self._line(conn, event, line, reserved=sign * qty, issued=ZERO)
        else:
            raise ValueError(f"unknown movement kind: {kind}")

    def _on_hand(self, conn: Connection, scope: str, lot: str, where: str, change: Decimal) -> None:
        self._stock(conn, scope, lot, where, on_hand=change, reserved=ZERO)

    @staticmethod
    def _stock(
        conn: Connection,
        scope: str,
        lot: str,
        where: str,
        *,
        on_hand: Decimal,
        reserved: Decimal,
    ) -> None:
        """Add the two changes to the balance of ``lot`` at ``where``; delete a row at zero."""
        key = {"lot_id": lot, "loc": where}
        row = conn.execute(_STOCK, key).first()
        new_on_hand = (dec(row.on_hand) if row else ZERO) + on_hand
        new_reserved = (dec(row.reserved) if row else ZERO) + reserved
        if new_on_hand < ZERO or new_reserved < ZERO or new_reserved > new_on_hand:
            raise ValueError("a movement may not make a balance negative")
        if new_on_hand == ZERO and new_reserved == ZERO:
            if row is not None:
                conn.execute(_STOCK_DELETE, key)
            return
        values = {
            "on_hand": num(new_on_hand),
            "reserved": num(new_reserved),
            "available": num(new_on_hand - new_reserved),
        }
        if row is None:
            conn.execute(_STOCK_INSERT, {**key, "scope": scope, **values})
        else:
            conn.execute(_STOCK_UPDATE, {**key, **values})

    @staticmethod
    def _consume(
        conn: Connection,
        event: Event,
        scope: str,
        lot: str,
        where: str,
        line: str | None,
        qty: Decimal,
    ) -> Decimal:
        """Take the part of an issue the line's reservation at ``where`` covers; return it."""
        if not line:
            return ZERO
        held = conn.execute(
            _RESERVATION, {"lot_id": lot, "loc": where, "line": line}
        ).scalar_one_or_none()
        if held is None:
            return ZERO
        consumed = min(qty, dec(held))
        StockProjector._reservation(conn, scope, lot, where, line, -consumed)
        return consumed

    @staticmethod
    def _reservation(
        conn: Connection, scope: str, lot: str, where: str, line: str, change: Decimal
    ) -> None:
        key = {"lot_id": lot, "loc": where, "line": line}
        held = conn.execute(_RESERVATION, key).scalar_one_or_none()
        new_qty = (dec(held) if held is not None else ZERO) + change
        if new_qty < ZERO:
            raise ValueError("a movement may not make a reservation negative")
        if new_qty == ZERO:
            if held is not None:
                conn.execute(_RESERVATION_DELETE, key)
        elif held is None:
            conn.execute(_RESERVATION_INSERT, {**key, "scope": scope, "qty": num(new_qty)})
        else:
            conn.execute(_RESERVATION_UPDATE, {**key, "qty": num(new_qty)})

    @staticmethod
    def _line(
        conn: Connection, event: Event, line: str, *, reserved: Decimal, issued: Decimal
    ) -> None:
        row = conn.execute(_LINE, {"id": line}).first()
        if row is None:
            raise LookupError(f"no {MTO_LINE_TABLE} row for the movement's line")
        new_reserved = dec(row.reserved_qty) + reserved
        new_issued = dec(row.issued_qty) + issued
        if new_reserved < ZERO or new_issued < ZERO:
            raise ValueError("a movement may not make a take-off line negative")
        conn.execute(
            _LINE_SET,
            {
                "id": line,
                "reserved": num(new_reserved),
                "issued": num(new_issued),
                "last_seq": event.seq,
            },
        )

    @staticmethod
    def _issued_net(conn: Connection, event: Event, change: Decimal) -> None:
        held = conn.execute(_LOT, {"id": event.stream_id}).scalar_one_or_none()
        if held is None:
            raise LookupError(f"no {LOT_TABLE} row for stream {event.stream_id}")
        new_net = dec(held) + change
        if new_net < ZERO:
            raise ValueError("a return may not exceed what was issued")
        done = conn.execute(
            _LOT_SET, {"id": event.stream_id, "issued_net": num(new_net), "last_seq": event.seq}
        )
        require_row(done.rowcount, LOT_TABLE, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {RESERVATION_TABLE}"))
        conn.execute(text(f"DELETE FROM {STOCK_TABLE}"))
        conn.execute(text(f"DELETE FROM {MOVEMENT_TABLE}"))
