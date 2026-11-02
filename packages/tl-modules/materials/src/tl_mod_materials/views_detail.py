"""Reads the screens need beyond the lists: one take-off line in full, and an item across projects
(P2-I3-S5).

Same rules as ``views``: **viewer-filtered** (ADR-0016), a hidden record answers as one that never
existed, nothing writes. ``mto_line_detail`` is a take-off line with the lot reservations against it
and the receipts of its item that are not yet decided; ``item_projects`` is the company item's
quantities, one row per project that adopted it.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Connection, text
from tl_core.confidentiality import Viewer

from tl_mod_materials.common import ZERO, dec
from tl_mod_materials.errors import MtoLineNotFoundError
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.names import (
    COMPANY,
    ITEM_MASTER_TABLE,
    LOCATION_TABLE,
    LOT_TABLE,
    MTO_LINE_TABLE,
    PROJECT_ITEM_TABLE,
    RECEIPT_LINE_TABLE,
    RECEIPT_TABLE,
    RESERVATION_TABLE,
    STOCK_TABLE,
)
from tl_mod_materials.views import (
    LINE_SELECT,
    MtoLineView,
    ReservationRowView,
    hide,
    line_view,
)

#: A receipt in one of these states is not yet decided: its goods are not in stock.
OPEN_RECEIPT_STATES = ("Received", "Inspected")


class OpenReceiptView(BaseModel):
    number: str
    state: str  # Received or Inspected
    received_on: str
    qty: Decimal  # the sum of the receipt's lines of the line's item
    uom: str
    supplier_text: str


class MtoLineDetailView(MtoLineView):
    reservations: list[ReservationRowView]
    open_receipts: list[OpenReceiptView]


class ItemProjectView(BaseModel):
    project: str  # the project id (the scope without ``project:``)
    title: str  # no project record carries a title yet: the project id again
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    uom: str


def mto_line_detail(
    conn: Connection, scope: str, key: str, *, viewer: Viewer | None = None
) -> MtoLineDetailView:
    """One take-off line (``key`` is the line key, ``ISO-1234@A/MTO/001``) with its reservations and
    the open receipts for its item. ``MtoLineNotFoundError`` when there is no such line in the
    project, or the viewer may not read it."""
    visible, params = hide("l.id", viewer=viewer)
    head = conn.execute(
        text(
            f"{LINE_SELECT}WHERE l.scope = :scope AND lr.key = :key AND lr.voided = :no "
            f"AND {visible}"
        ),
        {**params, "scope": scope, "key": key, "no": False},
    ).first()
    if head is None:
        raise MtoLineNotFoundError(f"no take-off line {key!r} in {scope}")
    line = line_view(head)
    return MtoLineDetailView(
        **line.model_dump(),
        reservations=_reservations(conn, line, viewer),
        open_receipts=_open_receipts(conn, scope, str(head.project_item_id), viewer),
    )


def _reservations(
    conn: Connection, line: MtoLineView, viewer: Viewer | None
) -> list[ReservationRowView]:
    """The lot reservations against one line: ``reservations_for_iwp``'s rows, for one line."""
    visible, params = hide("x.lot_id", "x.mto_line_id", "x.location_id", viewer=viewer)
    rows = conn.execute(
        text(
            "SELECT lr.key AS lot, loc.code AS location, mr.key AS mto_line, x.mto_line_id, x.qty, "
            "ir.key AS item_code "
            f"FROM {RESERVATION_TABLE} x JOIN {MTO_LINE_TABLE} l ON l.id = x.mto_line_id "
            "JOIN cur_core_record lr ON lr.id = x.lot_id "
            "JOIN cur_core_record mr ON mr.id = x.mto_line_id "
            "JOIN cur_core_record ir ON ir.id = l.project_item_id "
            f"JOIN {LOCATION_TABLE} loc ON loc.id = x.location_id "
            f"WHERE x.mto_line_id = :line AND {visible} "
            "ORDER BY lr.key, loc.code"
        ),
        {**params, "line": line.id},
    )
    return [
        ReservationRowView(
            lot=str(r.lot),
            location=str(r.location),
            mto_line=str(r.mto_line),
            mto_line_id=str(r.mto_line_id),
            qty=dec(r.qty),
            item_code=str(r.item_code),
            iwp_id=line.work_package_id,
        )
        for r in rows
    ]


def _open_receipts(
    conn: Connection, scope: str, project_item_id: str, viewer: Viewer | None
) -> list[OpenReceiptView]:
    """The project's receipts in state Received or Inspected that have a line of the item."""
    visible, params = hide("t.id", viewer=viewer)
    states = ", ".join(f"'{s}'" for s in OPEN_RECEIPT_STATES)
    rows = conn.execute(
        text(
            "SELECT r.key AS number, r.status, t.received_on, t.supplier_text, x.qty, x.uom "
            f"FROM {RECEIPT_TABLE} t JOIN cur_core_record r ON r.id = t.id "
            f"JOIN {RECEIPT_LINE_TABLE} x ON x.receipt_id = t.id "
            "WHERE t.scope = :scope AND x.project_item_id = :item AND r.voided = :no "
            f"AND (r.status IS NULL OR r.status IN ({states})) AND {visible} "
            "ORDER BY t.received_on, r.key, x.line_no"
        ),
        {**params, "scope": scope, "item": project_item_id, "no": False},
    )
    found: dict[str, OpenReceiptView] = {}
    for r in rows:
        number = str(r.number)
        qty = dec(r.qty)
        if number in found:
            found[number].qty += qty
        else:
            found[number] = OpenReceiptView(
                number=number,
                state="Received" if r.status is None else str(r.status),
                received_on=str(r.received_on),
                qty=qty,
                uom=str(r.uom),
                supplier_text=str(r.supplier_text),
            )
    return list(found.values())


def item_projects(
    conn: Connection, code: str, *, viewer: Viewer | None = None
) -> list[ItemProjectView]:
    """The quantities of one company item in each project that adopted it, by project id. An
    unknown item, or one the viewer may not read, answers ``[]``; a project whose copy of the item
    the viewer may not read is left out."""
    visible, params = hide("t.id", viewer=viewer)
    master = conn.execute(
        text(
            f"SELECT t.id, t.base_uom FROM {ITEM_MASTER_TABLE} t "
            "JOIN cur_core_record r ON r.id = t.id "
            f"WHERE t.scope = :company AND t.code = :code AND r.voided = :no AND {visible}"
        ),
        {**params, "company": COMPANY, "code": code, "no": False},
    ).first()
    if master is None:
        return []
    copy_visible, copy_params = hide("p.id", viewer=viewer)
    copies = conn.execute(
        text(
            f"SELECT p.id, p.scope, p.uom FROM {PROJECT_ITEM_TABLE} p "
            "JOIN cur_core_record pr ON pr.id = p.id "
            f"WHERE p.item_master_id = :master AND pr.voided = :no AND {copy_visible} "
            "ORDER BY p.scope, p.id"
        ),
        {**copy_params, "master": str(master.id), "no": False},
    ).all()
    if not copies:
        return []
    stock_visible, stock_params = hide(
        "s.lot_id", "s.location_id", "l.project_item_id", viewer=viewer
    )
    balances = conn.execute(
        text(
            "SELECT l.project_item_id, s.on_hand, s.reserved, s.available "
            f"FROM {STOCK_TABLE} s JOIN {LOT_TABLE} l ON l.id = s.lot_id "
            f"JOIN {PROJECT_ITEM_TABLE} p ON p.id = l.project_item_id "
            f"WHERE p.item_master_id = :master AND {stock_visible}"
        ),
        {**stock_params, "master": str(master.id)},
    )
    totals: dict[str, list[Decimal]] = {}
    for b in balances:
        sums = totals.setdefault(str(b.project_item_id), [ZERO, ZERO, ZERO])
        sums[0] += dec(b.on_hand)
        sums[1] += dec(b.reserved)
        sums[2] += dec(b.available)
    rows: dict[str, ItemProjectView] = {}
    for c in copies:
        project = str(c.scope).removeprefix("project:")
        on_hand, reserved, available = totals.get(str(c.id), [ZERO, ZERO, ZERO])
        if project in rows:
            row = rows[project]
            row.on_hand += on_hand
            row.reserved += reserved
            row.available += available
        else:
            rows[project] = ItemProjectView(
                project=project,
                title=project,
                on_hand=on_hand,
                reserved=reserved,
                available=available,
                uom=str(c.uom or master.base_uom),
            )
    return list(rows.values())[:MAX_VIEW_ROWS]
