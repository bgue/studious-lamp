"""PO line mirror commands: ``RecordPoLine`` and ``UpdatePoLine`` (m4 section 2; P2-Q4 A).

A PO line mirrors one line of the purchasing system, keyed ``<po>-<line>``. ``RecordPoLine``
names the
library item by ``item_code``; when the project has no ``ProjectItem`` for it, the same unit of work
adopts it first (written by the module: events with source ``rule``). The library item must
exist and
not be retired, and ``uom`` must equal the item's unit. ``UpdatePoLine`` changes the quantity
ordered
and the promised date (a date sent as null clears it).

``check_record_po_line`` is the rule, run by the handler and by the load target's plan.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import Connection
from tl_core.confidentiality import require_visible
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import DuplicateKeyError
from tl_core.services.records import create_module_record
from tl_core.text import clean_text
from tl_core.uow import UnitOfWork

from tl_mod_materials.common import (
    append,
    check_one_of,
    correlated,
    parse_qty,
    qty_text,
    require_project,
)
from tl_mod_materials.errors import (
    InvalidValueError,
    ItemNotFoundError,
    ItemRetiredError,
    NoChangesError,
    PoLineNotFoundError,
)
from tl_mod_materials.handlers.items import adopt_item, valid_item_code
from tl_mod_materials.limits import (
    ISO_DATE,
    MAX_ITEM_CODE,
    MAX_LINE_NO,
    MAX_PO_NUMBER,
    MAX_SUPPLIER,
    STOCK_UOMS,
)
from tl_mod_materials.names import PO_LINE, PO_LINE_DEFINED, PO_LINE_UPDATED
from tl_mod_materials.registry import (
    ItemRow,
    ProjectItemRow,
    get_item,
    get_po_line,
    get_project_item,
    record_type_of_key,
)

#: Source of the events the module writes on its own account (the auto-adopted project item).
MODULE_SOURCE = "rule"


def po_key(po_number: str, line_no: int) -> str:
    return f"{po_number}-{line_no}"


def _po_number(value: str) -> str:
    if not value.strip():
        raise ValueError("po_number must not be blank")
    return clean_text(value)


def _date(value: str | None) -> str | None:
    if value is None:
        return None
    if ISO_DATE.fullmatch(value) is None:
        raise ValueError("a date is written YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("not a calendar date") from exc
    return value


class RecordPoLine(Command):
    """Mirror one purchase order line into the project."""

    model_config = ConfigDict(extra="forbid")

    po_number: str = Field(min_length=1, max_length=MAX_PO_NUMBER)
    line_no: int = Field(ge=1, le=MAX_LINE_NO)
    item_code: str = Field(min_length=1, max_length=MAX_ITEM_CODE)
    qty_ordered: str = Field(min_length=1, max_length=14)
    uom: str = Field(min_length=1, max_length=8)
    promised_date: str | None = Field(default=None, min_length=10, max_length=10)
    supplier_text: str | None = Field(default=None, max_length=MAX_SUPPLIER)

    @field_validator("po_number")
    @classmethod
    def _check_po(cls, value: str) -> str:
        return _po_number(value)

    @field_validator("item_code")
    @classmethod
    def _check_item(cls, value: str) -> str:
        return valid_item_code(value)

    @field_validator("promised_date")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        return _date(value)

    @field_validator("supplier_text")
    @classmethod
    def _check_supplier(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value)


class UpdatePoLine(Command):
    """Change the quantity ordered or the promised date of a mirrored PO line."""

    model_config = ConfigDict(extra="forbid")

    po_number: str = Field(min_length=1, max_length=MAX_PO_NUMBER)
    line_no: int = Field(ge=1, le=MAX_LINE_NO)
    promised_date: str | None = Field(default=None, min_length=10, max_length=10)
    qty_ordered: str | None = Field(default=None, min_length=1, max_length=14)

    @field_validator("po_number")
    @classmethod
    def _check_po(cls, value: str) -> str:
        return _po_number(value)

    @field_validator("promised_date")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        return _date(value)


def check_record_po_line(
    conn: Connection, cmd: RecordPoLine
) -> tuple[ProjectItemRow | None, ItemRow | None, Decimal]:
    """The refusals of ``RecordPoLine``; returns ``(project item, library item to adopt, qty)``.

    Exactly one of the two items is set: the project's copy when it exists, else the library item
    that must be adopted first. The unit must equal the item's.
    """
    qty = parse_qty(cmd.qty_ordered, "qty_ordered")
    check_one_of(cmd.uom, STOCK_UOMS, "uom")
    key = po_key(cmd.po_number, cmd.line_no)
    if record_type_of_key(conn, cmd.scope, key) is not None:
        raise DuplicateKeyError("the PO line is already mirrored in the project")
    copy = get_project_item(conn, cmd.scope, cmd.item_code)
    if copy is not None:
        require_visible(conn, copy.id)
        if cmd.uom != copy.uom:
            raise InvalidValueError(f"uom must be the unit of the item: {copy.uom}")
        return copy, None, qty
    master = get_item(conn, cmd.item_code)
    if master is None:
        raise ItemNotFoundError("the item is not in the library")
    require_visible(conn, master.id)
    if master.retired:
        raise ItemRetiredError("the item is retired and cannot be ordered")
    if cmd.uom != master.base_uom:
        raise InvalidValueError(f"uom must be the unit of the item: {master.base_uom}")
    return None, master, qty


def handle_record_po_line(uow: UnitOfWork, cmd: RecordPoLine) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    copy, master, qty = check_record_po_line(conn, cmd)
    events = []
    if copy is None:
        assert master is not None
        adopted = adopt_item(uow, cmd.model_copy(update={"source": MODULE_SOURCE}), master)
        item_id = adopted.stream_id
        events.extend(adopted.events)
    else:
        item_id = copy.id
    key = po_key(cmd.po_number, cmd.line_no)
    made = create_module_record(
        uow,
        cmd,
        record_type=PO_LINE,
        title=f"PO {cmd.po_number} line {cmd.line_no}",
        key=key,
        extra_events=[
            NewEvent(
                event_type=PO_LINE_DEFINED,
                payload={
                    "po_number": cmd.po_number,
                    "line_no": cmd.line_no,
                    "project_item_id": item_id,
                    "qty_ordered": qty_text(qty),
                    "uom": cmd.uom,
                    "promised_date": cmd.promised_date,
                    "supplier_text": cmd.supplier_text or "",
                },
            )
        ],
    )
    return CommandResult(
        stream_id=made.stream_id,
        key=key,
        version=made.version,
        events=[*events, *made.events],
    )


def handle_update_po_line(uow: UnitOfWork, cmd: UpdatePoLine) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    key = po_key(cmd.po_number, cmd.line_no)
    row = get_po_line(conn, cmd.scope, key)
    if row is None:
        raise PoLineNotFoundError(f"no PO line {key!r} in {cmd.scope}")
    require_visible(conn, row.id)
    sent = cmd.model_fields_set
    payload: dict[str, str | None] = {}
    if "qty_ordered" in sent:
        if cmd.qty_ordered is None:
            raise InvalidValueError("qty_ordered cannot be cleared")
        qty = parse_qty(cmd.qty_ordered, "qty_ordered")
        if qty != row.qty_ordered:
            payload["qty_ordered"] = qty_text(qty)
    if "promised_date" in sent and cmd.promised_date != row.promised_date:
        payload["promised_date"] = cmd.promised_date
    if not payload:
        raise NoChangesError(f"the update changes nothing in PO line {key!r}")
    result = append(
        uow, cmd, row.id, PO_LINE, [NewEvent(event_type=PO_LINE_UPDATED, payload=payload)]
    )
    return CommandResult(
        stream_id=row.id, key=key, version=result.new_version, events=result.events
    )
