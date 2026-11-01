"""What a screen, a client or an agent reads about the library, locations, PO lines and stock.

Every read is **viewer-filtered** (ADR-0016): ``viewer`` defaults to the context's viewer, whose
default is the lowest clearance; the class filter is part of the statement, so a hidden record never
uses up a place of the ``LIMIT``. A hidden record answers as one that never existed. Nothing here
writes and nothing checks an access word (the entry points need ``materials.view``).

S3 adds ``receipts``, ``receipt_detail``, ``mto_lines``, ``reservations_for_iwp`` and
``mto_lines_for``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection, bindparam, text
from tl_core.confidentiality import Viewer, not_hidden

from tl_mod_materials.common import dec
from tl_mod_materials.errors import LotNotFoundError
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.names import (
    COMPANY,
    ITEM_MASTER_TABLE,
    LOCATION_TABLE,
    LOT_TABLE,
    MOVEMENT_KINDS,
    MOVEMENT_TABLE,
    PO_LINE_TABLE,
    PROJECT_ITEM_TABLE,
    RESERVATION_TABLE,
    STOCK_TABLE,
)

LAST_MOVEMENTS = 10


def _limit(limit: int) -> int:
    return max(1, min(limit, MAX_VIEW_ROWS))


def _hide(*columns: str, viewer: Viewer | None) -> tuple[str, dict[str, Any]]:
    """``(AND-able clause, params)``: every column names a record the viewer may read."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for column in columns:
        clause, found = not_hidden(column, viewer)
        clauses.append(clause)
        params.update(found)
    return " AND ".join(clauses), params


class ItemView(BaseModel):
    id: str
    code: str
    title: str
    category: str
    base_uom: str
    size_text: str | None
    rating_text: str | None
    material_code: str | None
    consumable: bool
    retired: bool
    projects: int  # copies of the item held by projects (hidden ones not counted)


class LocationView(BaseModel):
    id: str
    code: str
    title: str
    kind: str
    parent_code: str | None
    depth: int
    retired: bool
    lots: int  # lots with a balance here
    lines: int  # balance rows here


class PoLineView(BaseModel):
    id: str
    key: str
    po_number: str
    line_no: int
    item_code: str
    item_title: str
    qty_ordered: Decimal
    qty_received: Decimal
    uom: str
    promised_date: str | None
    supplier_text: str


class StockRowView(BaseModel):
    lot: str  # the lot key
    heat_no: str | None
    item_code: str
    item_title: str
    location: str  # the location code
    location_title: str
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    uom: str


class ReservationView(BaseModel):
    mto_line: str  # the MTO line key
    location: str
    qty: Decimal


class MovementView(BaseModel):
    seq: int
    recorded_at: str
    kind: str
    lot: str
    heat_no: str | None
    item_code: str
    qty: Decimal
    uom: str
    direction: str | None
    from_location: str | None
    to_location: str | None
    mto_line_id: str | None
    cost_code_id: str | None
    person: str | None
    reason: str | None
    actor: str


class LotDetailView(BaseModel):
    id: str
    key: str
    heat_no: str | None
    item_code: str
    item_title: str
    uom: str
    issued_net: Decimal
    receipt: str | None  # the receipt number
    receipt_line: int
    po_line: str | None
    quantities: list[StockRowView]
    reservations: list[ReservationView]
    movements: list[MovementView]  # the last ten, newest first


# --- items ---------------------------------------------------------------------------------------


def items(
    conn: Connection,
    *,
    project: str | None = None,
    viewer: Viewer | None = None,
    limit: int = MAX_VIEW_ROWS,
) -> list[ItemView]:
    """The library by code. ``project`` (``project:<id>``) keeps the items that project adopted."""
    visible, params = _hide("t.id", viewer=viewer)
    copies, copy_params = _hide("p.id", viewer=viewer)
    params.update(copy_params)
    adopted = ""
    if project is not None:
        adopted = (
            f" AND EXISTS (SELECT 1 FROM {PROJECT_ITEM_TABLE} q "
            "WHERE q.item_master_id = t.id AND q.scope = :project)"
        )
        params["project"] = project
    statement = text(
        "SELECT t.id, t.code, r.title, t.category, t.base_uom, t.size_text, t.rating_text, "
        "t.material_code, t.consumable, t.retired, "
        f"(SELECT COUNT(*) FROM {PROJECT_ITEM_TABLE} p JOIN cur_core_record pr ON pr.id = p.id "
        f"WHERE p.item_master_id = t.id AND pr.voided = :no AND {copies}) AS projects "
        f"FROM {ITEM_MASTER_TABLE} t JOIN cur_core_record r ON r.id = t.id "
        f"WHERE t.scope = :scope AND r.voided = :no AND {visible}{adopted} "
        "ORDER BY t.code LIMIT :limit"
    )
    rows = conn.execute(
        statement, {**params, "scope": COMPANY, "no": False, "limit": _limit(limit)}
    )
    return [
        ItemView(
            id=str(r.id),
            code=str(r.code),
            title=str(r.title),
            category=str(r.category),
            base_uom=str(r.base_uom),
            size_text=r.size_text,
            rating_text=r.rating_text,
            material_code=r.material_code,
            consumable=bool(r.consumable),
            retired=bool(r.retired),
            projects=int(r.projects),
        )
        for r in rows
    ]


# --- locations -----------------------------------------------------------------------------------


def locations_tree(
    conn: Connection, scope: str, *, viewer: Viewer | None = None, limit: int = MAX_VIEW_ROWS
) -> list[LocationView]:
    """The project's locations in tree order (a parent, then its children by code)."""
    visible, params = _hide("t.id", viewer=viewer)
    statement = text(
        "SELECT t.id, t.code, r.title, t.kind, t.parent_id, t.depth, t.retired, "
        f"(SELECT COUNT(DISTINCT s.lot_id) FROM {STOCK_TABLE} s "
        "WHERE s.location_id = t.id) AS lots, "
        f"(SELECT COUNT(*) FROM {STOCK_TABLE} s WHERE s.location_id = t.id) AS lines "
        f"FROM {LOCATION_TABLE} t JOIN cur_core_record r ON r.id = t.id "
        f"WHERE t.scope = :scope AND r.voided = :no AND {visible} "
        "ORDER BY t.depth, t.code LIMIT :limit"
    )
    rows = conn.execute(
        statement, {**params, "scope": scope, "no": False, "limit": _limit(limit)}
    ).all()
    codes = {str(r.id): str(r.code) for r in rows}
    children: dict[str | None, list[Any]] = {}
    for r in rows:
        parent = None if r.parent_id is None else str(r.parent_id)
        children.setdefault(parent if parent in codes else None, []).append(r)
    ordered: list[LocationView] = []

    def walk(parent: str | None) -> None:
        for r in sorted(children.get(parent, []), key=lambda x: str(x.code)):
            ordered.append(
                LocationView(
                    id=str(r.id),
                    code=str(r.code),
                    title=str(r.title),
                    kind=str(r.kind),
                    parent_code=None if r.parent_id is None else codes.get(str(r.parent_id)),
                    depth=int(r.depth),
                    retired=bool(r.retired),
                    lots=int(r.lots),
                    lines=int(r.lines),
                )
            )
            walk(str(r.id))

    walk(None)
    return ordered


def _subtree(rows: Sequence[Any], root: str) -> set[str]:
    """``root`` and every location below it, from ``(id, parent_id)`` rows."""
    below: dict[str, list[str]] = {}
    for r in rows:
        if r.parent_id is not None:
            below.setdefault(str(r.parent_id), []).append(str(r.id))
    found, todo = {root}, [root]
    while todo:
        for child in below.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


# --- PO lines ------------------------------------------------------------------------------------


def _like(value: str) -> str:
    return "%" + value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def po_lines(
    conn: Connection,
    scope: str,
    q: str | None = None,
    *,
    viewer: Viewer | None = None,
    limit: int = MAX_VIEW_ROWS,
) -> list[PoLineView]:
    """The project's PO lines by key; ``q`` keeps those whose key, item or supplier holds it."""
    visible, params = _hide("t.id", viewer=viewer)
    search = ""
    if q:
        search = (
            " AND (LOWER(r.key) LIKE :q ESCAPE '\\' OR LOWER(pi.key) LIKE :q ESCAPE '\\' "
            "OR LOWER(t.supplier_text) LIKE :q ESCAPE '\\')"
        )
        params["q"] = _like(q)
    statement = text(
        "SELECT t.id, r.key, t.po_number, t.line_no, pi.key AS item_code, pi.title AS item_title, "
        "t.qty_ordered, t.qty_received, t.uom, t.promised_date, t.supplier_text "
        f"FROM {PO_LINE_TABLE} t JOIN cur_core_record r ON r.id = t.id "
        "JOIN cur_core_record pi ON pi.id = t.project_item_id "
        f"WHERE t.scope = :scope AND r.voided = :no AND {visible}{search} "
        "ORDER BY t.po_number, t.line_no, r.key LIMIT :limit"
    )
    rows = conn.execute(statement, {**params, "scope": scope, "no": False, "limit": _limit(limit)})
    return [
        PoLineView(
            id=str(r.id),
            key=str(r.key),
            po_number=str(r.po_number),
            line_no=int(r.line_no),
            item_code=str(r.item_code),
            item_title=str(r.item_title),
            qty_ordered=dec(r.qty_ordered),
            qty_received=dec(r.qty_received),
            uom=str(r.uom),
            promised_date=r.promised_date,
            supplier_text=str(r.supplier_text),
        )
        for r in rows
    ]


# --- stock ---------------------------------------------------------------------------------------

_STOCK_SELECT = (
    "SELECT lr.key AS lot, l.heat_no, ir.key AS item_code, ir.title AS item_title, "
    "loc.code AS location, lcr.title AS location_title, s.on_hand, s.reserved, s.available, "
    f"l.uom FROM {STOCK_TABLE} s JOIN {LOT_TABLE} l ON l.id = s.lot_id "
    "JOIN cur_core_record lr ON lr.id = l.id "
    "JOIN cur_core_record ir ON ir.id = l.project_item_id "
    f"JOIN {LOCATION_TABLE} loc ON loc.id = s.location_id "
    "JOIN cur_core_record lcr ON lcr.id = loc.id "
)


def _stock_row(r: Any) -> StockRowView:
    return StockRowView(
        lot=str(r.lot),
        heat_no=r.heat_no,
        item_code=str(r.item_code),
        item_title=str(r.item_title),
        location=str(r.location),
        location_title=str(r.location_title),
        on_hand=dec(r.on_hand),
        reserved=dec(r.reserved),
        available=dec(r.available),
        uom=str(r.uom),
    )


def stock(
    conn: Connection,
    scope: str,
    *,
    lot: str | None = None,
    location: str | None = None,
    item: str | None = None,
    heat: str | None = None,
    subtree: bool = False,
    viewer: Viewer | None = None,
    limit: int = MAX_VIEW_ROWS,
) -> list[StockRowView]:
    """The balances of a project by lot key and location code (rows at zero do not exist).

    ``location`` is a location code (with ``subtree`` the location and all below it), ``item``
    an item code, ``heat`` a heat number, ``lot`` a lot key.
    """
    visible, params = _hide("s.lot_id", "s.location_id", "l.project_item_id", viewer=viewer)
    where = [f"s.scope = :scope AND {visible}"]
    params["scope"] = scope
    statement_params: dict[str, Any] = {}
    ids: list[str] | None = None
    if location is not None:
        locations = conn.execute(
            text(f"SELECT id, parent_id, code FROM {LOCATION_TABLE} WHERE scope = :scope"),
            {"scope": scope},
        ).all()
        root = next((str(r.id) for r in locations if r.code == location), None)
        if root is None:
            return []
        ids = sorted(_subtree(locations, root) if subtree else {root})
        where.append("s.location_id IN :location_ids")
    if lot is not None:
        where.append("lr.key = :lot")
        params["lot"] = lot
    if item is not None:
        where.append("ir.key = :item")
        params["item"] = item
    if heat is not None:
        where.append("l.heat_no = :heat")
        params["heat"] = heat
    sql = text(f"{_STOCK_SELECT}WHERE {' AND '.join(where)} ORDER BY lr.key, loc.code LIMIT :limit")
    if ids is not None:
        sql = sql.bindparams(bindparam("location_ids", expanding=True))
        statement_params["location_ids"] = ids
    rows = conn.execute(sql, {**params, **statement_params, "limit": _limit(limit)})
    return [_stock_row(r) for r in rows]


# --- movements -----------------------------------------------------------------------------------

_MOVEMENT_SELECT = (
    "SELECT m.seq, m.recorded_at, m.kind, lr.key AS lot, l.heat_no, ir.key AS item_code, m.qty, "
    "m.uom, m.direction, fl.code AS from_location, tl.code AS to_location, m.mto_line_id, "
    "m.cost_code_id, m.person, m.reason, m.actor "
    f"FROM {MOVEMENT_TABLE} m JOIN {LOT_TABLE} l ON l.id = m.lot_id "
    "JOIN cur_core_record lr ON lr.id = l.id "
    "JOIN cur_core_record ir ON ir.id = l.project_item_id "
    f"LEFT JOIN {LOCATION_TABLE} fl ON fl.id = m.from_location_id "
    f"LEFT JOIN {LOCATION_TABLE} tl ON tl.id = m.to_location_id "
)


def _movement_row(r: Any) -> MovementView:
    return MovementView(
        seq=int(r.seq),
        recorded_at=str(r.recorded_at),
        kind=str(r.kind),
        lot=str(r.lot),
        heat_no=r.heat_no,
        item_code=str(r.item_code),
        qty=dec(r.qty),
        uom=str(r.uom),
        direction=r.direction,
        from_location=r.from_location,
        to_location=r.to_location,
        mto_line_id=r.mto_line_id,
        cost_code_id=r.cost_code_id,
        person=r.person,
        reason=r.reason,
        actor=str(r.actor),
    )


def movements(
    conn: Connection,
    scope: str,
    *,
    lot: str | None = None,
    since: str | None = None,
    until: str | None = None,
    kind: str | None = None,
    viewer: Viewer | None = None,
    limit: int = MAX_VIEW_ROWS,
) -> list[MovementView]:
    """The movement log of a project in ledger order. ``since`` and ``until`` are ISO dates (both
    days included) or ISO timestamps; ``kind`` is one of the eight movement kinds."""
    visible, params = _hide("m.lot_id", viewer=viewer)
    where = [f"m.scope = :scope AND {visible}"]
    params["scope"] = scope
    if kind is not None:
        if kind not in MOVEMENT_KINDS:
            return []
        where.append("m.kind = :kind")
        params["kind"] = kind
    if lot is not None:
        where.append("lr.key = :lot")
        params["lot"] = lot
    if since is not None:
        where.append("m.recorded_at >= :since")
        params["since"] = since
    if until is not None:
        if len(until) == 10:
            params["until"] = (date.fromisoformat(until) + timedelta(days=1)).isoformat()
        else:
            params["until"] = until
        where.append("m.recorded_at < :until")
    sql = text(f"{_MOVEMENT_SELECT}WHERE {' AND '.join(where)} ORDER BY m.seq LIMIT :limit")
    rows = conn.execute(sql, {**params, "limit": _limit(limit)})
    return [_movement_row(r) for r in rows]


# --- one lot -------------------------------------------------------------------------------------


def lot_detail(
    conn: Connection, scope: str, key: str, *, viewer: Viewer | None = None
) -> LotDetailView:
    """A lot with its balances, reservations and last ten movements. ``LotNotFoundError`` when
    there is no such lot, or the viewer may not read it."""
    visible, params = _hide("l.id", viewer=viewer)
    head = conn.execute(
        text(
            "SELECT l.id, lr.key, l.heat_no, ir.key AS item_code, ir.title AS item_title, l.uom, "
            "l.issued_net, l.receipt_line, rr.key AS receipt, "
            "(SELECT pr.key FROM cur_materials_receipt rc "
            " JOIN cur_core_record pr ON pr.id = rc.po_line_id "
            " WHERE rc.id = l.receipt_id) AS po_line "
            f"FROM {LOT_TABLE} l JOIN cur_core_record lr ON lr.id = l.id "
            "JOIN cur_core_record ir ON ir.id = l.project_item_id "
            "LEFT JOIN cur_core_record rr ON rr.id = l.receipt_id "
            f"WHERE l.scope = :scope AND lr.key = :key AND lr.voided = :no AND {visible}"
        ),
        {**params, "scope": scope, "key": key, "no": False},
    ).first()
    if head is None:
        raise LotNotFoundError(f"no lot {key!r} in {scope}")
    quantities = stock(conn, scope, lot=key, viewer=viewer)
    reservations = conn.execute(
        text(
            "SELECT mr.key AS mto_line, loc.code AS location, x.qty "
            f"FROM {RESERVATION_TABLE} x JOIN {LOCATION_TABLE} loc ON loc.id = x.location_id "
            "JOIN cur_core_record mr ON mr.id = x.mto_line_id "
            "WHERE x.lot_id = :lot ORDER BY mr.key, loc.code"
        ),
        {"lot": str(head.id)},
    )
    last = conn.execute(
        text(f"{_MOVEMENT_SELECT}WHERE m.lot_id = :lot ORDER BY m.seq DESC LIMIT :n"),
        {"lot": str(head.id), "n": LAST_MOVEMENTS},
    )
    return LotDetailView(
        id=str(head.id),
        key=str(head.key),
        heat_no=head.heat_no,
        item_code=str(head.item_code),
        item_title=str(head.item_title),
        uom=str(head.uom),
        issued_net=dec(head.issued_net),
        receipt=head.receipt,
        receipt_line=int(head.receipt_line),
        po_line=head.po_line,
        quantities=quantities,
        reservations=[
            ReservationView(mto_line=str(r.mto_line), location=str(r.location), qty=dec(r.qty))
            for r in reservations
        ],
        movements=[_movement_row(r) for r in last],
    )
