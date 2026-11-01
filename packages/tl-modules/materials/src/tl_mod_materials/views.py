"""What a screen, a client or an agent reads about the library, locations, PO lines and stock.

Every read is **viewer-filtered** (ADR-0016): ``viewer`` defaults to the context's viewer, whose
default is the lowest clearance; the class filter is part of the statement, so a hidden record never
uses up a place of the ``LIMIT``. A hidden record answers as one that never existed. Nothing here
writes and nothing checks an access word (the entry points need ``materials.view``).

S3 added ``receipts``, ``receipt_detail``, ``mto_lines``, ``reservations_for_iwp`` and
``mto_lines_for`` (the figures of a take-off line are ``Decimal``, shortages computed in Python).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import Connection, bindparam, text
from tl_core.confidentiality import Viewer, not_hidden
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of

from tl_mod_materials.common import ZERO, dec
from tl_mod_materials.errors import LotNotFoundError, ReceiptNotFoundError
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.names import (
    COMPANY,
    ITEM_MASTER_TABLE,
    LOCATION_TABLE,
    LOT_TABLE,
    MOVEMENT_KINDS,
    MOVEMENT_TABLE,
    MTO_LINE_TABLE,
    PO_LINE_TABLE,
    PROJECT_ITEM_TABLE,
    RECEIPT_LINE_TABLE,
    RECEIPT_TABLE,
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


# --- receipts ------------------------------------------------------------------------------------

MTR_SLOT = "mtr"
MTR_SETTING = "materials.receipt.mtr_required_categories"
#: ``present``: an available MTR file; ``missing``: none, and a line is of a category that needs
#: one; ``n/a``: none, and none is needed.
MtrState = Literal["present", "missing", "n/a"]


class ReceiptView(BaseModel):
    id: str
    number: str
    title: str
    state: str  # Received, Inspected, Accepted, Rejected or Void
    received_on: str
    location: str  # the location code
    supplier_text: str
    delivery_ref: str | None
    po_line: str | None  # the PO line key
    lines: int
    mtr: MtrState
    mtr_required: bool


class ReceiptLineView(BaseModel):
    line_no: int
    item_code: str
    item_title: str
    qty: Decimal
    uom: str
    heat_no: str | None
    condition: str
    serials_text: str | None
    lot: str | None  # the lot key, set when the receipt is accepted


class ReceiptFileView(BaseModel):
    file_id: str
    slot: str | None
    filename: str
    status: str
    uploaded_at: str


class ReceiptDetailView(ReceiptView):
    created_at: str
    inspected_by: str | None
    inspected_on: str | None
    decided_by: str | None
    decided_on: str | None
    rejection_reason: str | None
    line_rows: list[ReceiptLineView]
    files: list[ReceiptFileView]


_RECEIPT_SELECT = (
    "SELECT t.id, r.key, r.title, r.status, r.voided, r.created_at, t.received_on, "
    "t.supplier_text, t.delivery_ref, t.inspected_by, t.inspected_on, t.decided_by, "
    "t.decided_on, t.rejection_reason, loc.code AS location, po.key AS po_line, "
    f"(SELECT COUNT(*) FROM {RECEIPT_LINE_TABLE} x WHERE x.receipt_id = t.id) AS line_count, "
    "(SELECT COUNT(*) FROM cur_files f WHERE f.record_id = t.id AND f.slot = :mtr_slot "
    "AND f.status = 'available' AND f.superseded_by IS NULL) AS mtr_files "
    f"FROM {RECEIPT_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    f"JOIN {LOCATION_TABLE} loc ON loc.id = t.location_id "
    "LEFT JOIN cur_core_record po ON po.id = t.po_line_id "
)
_CATEGORIES_OF = text(
    "SELECT x.receipt_id, p.category "
    f"FROM {RECEIPT_LINE_TABLE} x JOIN {PROJECT_ITEM_TABLE} p ON p.id = x.project_item_id "
    "WHERE x.receipt_id IN :ids"
).bindparams(bindparam("ids", expanding=True))


def _mtr_categories(conn: Connection, scope: str) -> set[str]:
    listed = value_of(conn, MTR_SETTING, project=project_of_scope(scope))
    return {str(c) for c in listed} if isinstance(listed, list) else set()


def _receipt_state(r: Any) -> str:
    if bool(r.voided):
        return "Void"
    return "Received" if r.status is None else str(r.status)


def _receipt_views(conn: Connection, scope: str, rows: Sequence[Any]) -> list[ReceiptView]:
    if not rows:
        return []
    required = _mtr_categories(conn, scope)
    by_receipt: dict[str, set[str]] = {}
    for found in conn.execute(_CATEGORIES_OF, {"ids": [str(r.id) for r in rows]}):
        by_receipt.setdefault(str(found.receipt_id), set()).add(str(found.category))
    views: list[ReceiptView] = []
    for r in rows:
        needs = bool(by_receipt.get(str(r.id), set()) & required)
        present = int(r.mtr_files) > 0
        views.append(
            ReceiptView(
                id=str(r.id),
                number=str(r.key),
                title=str(r.title),
                state=_receipt_state(r),
                received_on=str(r.received_on),
                location=str(r.location),
                supplier_text=str(r.supplier_text),
                delivery_ref=r.delivery_ref,
                po_line=r.po_line,
                lines=int(r.line_count),
                mtr="present" if present else ("missing" if needs else "n/a"),
                mtr_required=needs,
            )
        )
    return views


def receipts(
    conn: Connection,
    scope: str,
    *,
    open_only: bool = False,
    missing_mtr: bool = False,
    viewer: Viewer | None = None,
    limit: int = MAX_VIEW_ROWS,
) -> list[ReceiptView]:
    """The project's receipts by number. ``open_only`` keeps those not yet decided (Received or
    Inspected); ``missing_mtr`` keeps those that still lack a required MTR."""
    visible, params = _hide("t.id", viewer=viewer)
    where = [f"t.scope = :scope AND {visible}"]
    if open_only:
        where.append(
            "r.voided = :no AND (r.status IS NULL OR r.status IN ('Received', 'Inspected'))"
        )
    sql = text(f"{_RECEIPT_SELECT}WHERE {' AND '.join(where)} ORDER BY r.key LIMIT :limit")
    rows = conn.execute(
        sql, {**params, "scope": scope, "no": False, "mtr_slot": MTR_SLOT, "limit": _limit(limit)}
    ).all()
    found = _receipt_views(conn, scope, rows)
    return [v for v in found if v.mtr == "missing"] if missing_mtr else found


def receipt_detail(
    conn: Connection, scope: str, number: str, *, viewer: Viewer | None = None
) -> ReceiptDetailView:
    """One receipt by number with its lines and files. ``ReceiptNotFoundError`` when there is no
    such receipt, or the viewer may not read it."""
    visible, params = _hide("t.id", viewer=viewer)
    row = conn.execute(
        text(f"{_RECEIPT_SELECT}WHERE t.scope = :scope AND r.key = :key AND {visible}"),
        {**params, "scope": scope, "key": number, "mtr_slot": MTR_SLOT},
    ).first()
    if row is None:
        raise ReceiptNotFoundError(f"no receipt {number!r} in {scope}")
    head = _receipt_views(conn, scope, [row])[0]
    lines = conn.execute(
        text(
            "SELECT x.line_no, ir.key AS item_code, ir.title AS item_title, x.qty, x.uom, "
            "x.heat_no, x.condition, x.serials_text, lr.key AS lot "
            f"FROM {RECEIPT_LINE_TABLE} x JOIN cur_core_record ir ON ir.id = x.project_item_id "
            "LEFT JOIN cur_core_record lr ON lr.id = x.lot_id "
            "WHERE x.receipt_id = :id ORDER BY x.line_no"
        ),
        {"id": head.id},
    )
    files = conn.execute(
        text(
            "SELECT file_id, slot, filename, status, uploaded_at FROM cur_files "
            "WHERE record_id = :id ORDER BY COALESCE(slot, ''), revision, file_id"
        ),
        {"id": head.id},
    )
    return ReceiptDetailView(
        **head.model_dump(),
        created_at=str(row.created_at),
        inspected_by=row.inspected_by,
        inspected_on=row.inspected_on,
        decided_by=row.decided_by,
        decided_on=row.decided_on,
        rejection_reason=row.rejection_reason,
        line_rows=[
            ReceiptLineView(
                line_no=int(x.line_no),
                item_code=str(x.item_code),
                item_title=str(x.item_title),
                qty=dec(x.qty),
                uom=str(x.uom),
                heat_no=x.heat_no,
                condition=str(x.condition),
                serials_text=x.serials_text,
                lot=x.lot,
            )
            for x in lines
        ],
        files=[
            ReceiptFileView(
                file_id=str(f.file_id),
                slot=f.slot,
                filename=str(f.filename),
                status=str(f.status),
                uploaded_at=str(f.uploaded_at),
            )
            for f in files
        ],
    )


# --- take-off lines and reservations -------------------------------------------------------------


class MtoLineView(BaseModel):
    id: str
    key: str  # the line key, ``ISO-1234@A/MTO/001``
    mto: str  # the take-off key
    line_no: int
    item_code: str
    item_title: str
    uom: str
    required: Decimal
    reserved: Decimal
    issued: Decimal
    short: Decimal  # required - reserved - issued, never below zero
    work_package: str | None  # the work package number (the key of its record)
    work_package_id: str | None
    need_by: str | None  # the work package's planned start; None until the awp module provides it


class ReservationRowView(BaseModel):
    lot: str
    location: str
    mto_line: str
    mto_line_id: str
    qty: Decimal
    item_code: str
    iwp_id: str | None


_LINE_SELECT = (
    "SELECT l.id, lr.key, mr.key AS mto, l.line_no, ir.key AS item_code, ir.title AS item_title, "
    "l.uom, l.qty, l.reserved_qty, l.issued_qty, l.work_package_id, wp.key AS work_package "
    f"FROM {MTO_LINE_TABLE} l JOIN cur_core_record lr ON lr.id = l.id "
    "JOIN cur_core_record mr ON mr.id = l.mto_id "
    "JOIN cur_core_record ir ON ir.id = l.project_item_id "
    "LEFT JOIN cur_core_record wp ON wp.id = l.work_package_id "
)


def _line_view(r: Any) -> MtoLineView:
    required, reserved, issued = dec(r.qty), dec(r.reserved_qty), dec(r.issued_qty)
    return MtoLineView(
        id=str(r.id),
        key=str(r.key),
        mto=str(r.mto),
        line_no=int(r.line_no),
        item_code=str(r.item_code),
        item_title=str(r.item_title),
        uom=str(r.uom),
        required=required,
        reserved=reserved,
        issued=issued,
        short=max(ZERO, required - reserved - issued),
        work_package=r.work_package,
        work_package_id=None if r.work_package_id is None else str(r.work_package_id),
        need_by=None,
    )


def mto_lines(
    conn: Connection,
    scope: str,
    *,
    work_package: str | None = None,
    short_only: bool = False,
    viewer: Viewer | None = None,
    limit: int = MAX_VIEW_ROWS,
) -> list[MtoLineView]:
    """The project's take-off lines by key. ``work_package`` is a work package number;
    ``short_only`` keeps the lines not covered by reservations and issues."""
    visible, params = _hide("l.id", viewer=viewer)
    where = [f"l.scope = :scope AND lr.voided = :no AND {visible}"]
    if work_package is not None:
        where.append("wp.key = :wp")
        params["wp"] = work_package
    rows = conn.execute(
        text(f"{_LINE_SELECT}WHERE {' AND '.join(where)} ORDER BY lr.key"),
        {**params, "scope": scope, "no": False},
    )
    found: list[MtoLineView] = []
    for r in rows:
        view = _line_view(r)
        if short_only and view.short <= ZERO:
            continue
        found.append(view)
        if len(found) >= _limit(limit):
            break
    return found


def mto_lines_for(
    conn: Connection, record_id: str, *, viewer: Viewer | None = None, limit: int = MAX_VIEW_ROWS
) -> list[MtoLineView]:
    """The take-off lines of a work package (a CWP or an IWP, by record id)."""
    visible, params = _hide("l.id", viewer=viewer)
    rows = conn.execute(
        text(
            f"{_LINE_SELECT}WHERE l.work_package_id = :wp AND lr.voided = :no AND {visible} "
            "ORDER BY lr.key LIMIT :limit"
        ),
        {**params, "wp": record_id, "no": False, "limit": _limit(limit)},
    )
    return [_line_view(r) for r in rows]


def reservations_for_iwp(
    conn: Connection, iwp_id: str, *, viewer: Viewer | None = None, limit: int = MAX_VIEW_ROWS
) -> list[ReservationRowView]:
    """What is reserved for the take-off lines of an IWP: lot, location, line and quantity."""
    visible, params = _hide("x.lot_id", "x.mto_line_id", "x.location_id", viewer=viewer)
    rows = conn.execute(
        text(
            "SELECT lr.key AS lot, loc.code AS location, mr.key AS mto_line, x.mto_line_id, x.qty, "
            "ir.key AS item_code, l.work_package_id "
            f"FROM {RESERVATION_TABLE} x JOIN {MTO_LINE_TABLE} l ON l.id = x.mto_line_id "
            "JOIN cur_core_record lr ON lr.id = x.lot_id "
            "JOIN cur_core_record mr ON mr.id = x.mto_line_id "
            "JOIN cur_core_record ir ON ir.id = l.project_item_id "
            f"JOIN {LOCATION_TABLE} loc ON loc.id = x.location_id "
            f"WHERE l.work_package_id = :iwp AND {visible} "
            "ORDER BY mr.key, lr.key, loc.code LIMIT :limit"
        ),
        {**params, "iwp": iwp_id, "limit": _limit(limit)},
    )
    return [
        ReservationRowView(
            lot=str(r.lot),
            location=str(r.location),
            mto_line=str(r.mto_line),
            mto_line_id=str(r.mto_line_id),
            qty=dec(r.qty),
            item_code=str(r.item_code),
            iwp_id=iwp_id,
        )
        for r in rows
    ]
