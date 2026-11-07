"""Reads of the materials tables the handlers, the load targets and the views share.

Every lookup joins ``cur_core_record`` and skips a voided record: a voided record is gone for the
module's rules (its key stays taken, as everywhere). Quantities come back as ``Decimal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, text

from tl_mod_materials.common import ZERO, dec
from tl_mod_materials.names import (
    COMPANY,
    ITEM_MASTER_TABLE,
    LOCATION_TABLE,
    PO_LINE_TABLE,
    PROJECT_ITEM_TABLE,
    STOCK_TABLE,
)


@dataclass(frozen=True)
class ItemRow:
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


@dataclass(frozen=True)
class ProjectItemRow:
    id: str
    code: str
    title: str
    item_master_id: str
    category: str
    uom: str
    consumable: bool


@dataclass(frozen=True)
class LocationRow:
    id: str
    code: str
    title: str
    kind: str
    parent_id: str | None
    depth: int
    retired: bool


@dataclass(frozen=True)
class PoLineRow:
    id: str
    key: str
    po_number: str
    line_no: int
    project_item_id: str
    qty_ordered: Decimal
    uom: str
    promised_date: str | None
    supplier_text: str
    qty_received: Decimal


_ITEM = text(
    "SELECT t.id, t.code, r.title, t.category, t.base_uom, t.size_text, t.rating_text, "
    f"t.material_code, t.consumable, t.retired FROM {ITEM_MASTER_TABLE} t "
    "JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.scope = :scope AND t.code = :code AND r.voided = :voided"
)
_PROJECT_ITEM = text(
    "SELECT t.id, r.key AS code, r.title, t.item_master_id, t.category, t.uom, t.consumable "
    f"FROM {PROJECT_ITEM_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.scope = :scope AND r.key = :code AND r.voided = :voided"
)
_LOCATION = text(
    "SELECT t.id, t.code, r.title, t.kind, t.parent_id, t.depth, t.retired "
    f"FROM {LOCATION_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.scope = :scope AND t.code = :code AND r.voided = :voided"
)
_ROOT = text(
    f"SELECT t.id FROM {LOCATION_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.scope = :scope AND t.parent_id IS NULL AND r.voided = :voided"
)
_ACTIVE_CHILD = text(
    f"SELECT t.id FROM {LOCATION_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.parent_id = :id AND t.retired = :retired AND r.voided = :voided"
)
_STOCK_AT = text(f"SELECT on_hand, reserved FROM {STOCK_TABLE} WHERE location_id = :id")
_PO_LINE = text(
    "SELECT t.id, r.key, t.po_number, t.line_no, t.project_item_id, t.qty_ordered, t.uom, "
    f"t.promised_date, t.supplier_text, t.qty_received FROM {PO_LINE_TABLE} t "
    "JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.scope = :scope AND r.key = :key AND r.voided = :voided"
)
_KEY_TYPE = text("SELECT type FROM cur_core_record WHERE scope = :scope AND key = :key")
_ITEM_ADOPTED = text(f"SELECT 1 FROM {PROJECT_ITEM_TABLE} WHERE item_master_id = :id")


def get_item(conn: Connection, code: str) -> ItemRow | None:
    """The live library item with ``code`` (company scope)."""
    row = conn.execute(_ITEM, {"scope": COMPANY, "code": code, "voided": False}).first()
    if row is None:
        return None
    return ItemRow(
        id=str(row.id),
        code=str(row.code),
        title=str(row.title),
        category=str(row.category),
        base_uom=str(row.base_uom),
        size_text=row.size_text,
        rating_text=row.rating_text,
        material_code=row.material_code,
        consumable=bool(row.consumable),
        retired=bool(row.retired),
    )


def get_project_item(conn: Connection, scope: str, code: str) -> ProjectItemRow | None:
    row = conn.execute(_PROJECT_ITEM, {"scope": scope, "code": code, "voided": False}).first()
    if row is None:
        return None
    return ProjectItemRow(
        id=str(row.id),
        code=str(row.code),
        title=str(row.title),
        item_master_id=str(row.item_master_id),
        category=str(row.category),
        uom=str(row.uom),
        consumable=bool(row.consumable),
    )


def item_is_adopted(conn: Connection, item_master_id: str) -> bool:
    """Whether any project holds a copy of the library item (its unit can no longer change)."""
    return conn.execute(_ITEM_ADOPTED, {"id": item_master_id}).first() is not None


def get_location(conn: Connection, scope: str, code: str) -> LocationRow | None:
    row = conn.execute(_LOCATION, {"scope": scope, "code": code, "voided": False}).first()
    if row is None:
        return None
    return LocationRow(
        id=str(row.id),
        code=str(row.code),
        title=str(row.title),
        kind=str(row.kind),
        parent_id=None if row.parent_id is None else str(row.parent_id),
        depth=int(row.depth),
        retired=bool(row.retired),
    )


def has_root(conn: Connection, scope: str) -> bool:
    """Whether the project's location tree already has its root (retired or not)."""
    return conn.execute(_ROOT, {"scope": scope, "voided": False}).first() is not None


def has_active_child(conn: Connection, location_id: str) -> bool:
    found = conn.execute(
        _ACTIVE_CHILD, {"id": location_id, "retired": False, "voided": False}
    ).first()
    return found is not None


def holds_stock(conn: Connection, location_id: str) -> bool:
    """Whether any lot has a balance at the location that is not zero (``Decimal`` compare)."""
    return any(
        dec(row.on_hand) != ZERO or dec(row.reserved) != ZERO
        for row in conn.execute(_STOCK_AT, {"id": location_id})
    )


def get_po_line(conn: Connection, scope: str, key: str) -> PoLineRow | None:
    row = conn.execute(_PO_LINE, {"scope": scope, "key": key, "voided": False}).first()
    if row is None:
        return None
    return PoLineRow(
        id=str(row.id),
        key=str(row.key),
        po_number=str(row.po_number),
        line_no=int(row.line_no),
        project_item_id=str(row.project_item_id),
        qty_ordered=dec(row.qty_ordered),
        uom=str(row.uom),
        promised_date=None if row.promised_date is None else str(row.promised_date),
        supplier_text=str(row.supplier_text),
        qty_received=dec(row.qty_received),
    )


def record_type_of_key(conn: Connection, scope: str, key: str) -> str | None:
    """The record type that holds ``key`` in ``scope`` (voided or not), else ``None``."""
    found = conn.execute(_KEY_TYPE, {"scope": scope, "key": key}).scalar_one_or_none()
    return None if found is None else str(found)
