"""Receipt commands: create, revise, inspect, accept, reject and void (m4-materials.md 2, 3).

A receipt books a delivery (state Received), is looked at (Inspected) and is then accepted, which
is the only way stock enters (there is no ``Receive`` command), or rejected, or voided while it is
still open. The workflow is ``schema/fixtures/workflows/materials-receipt.yaml``; the module moves
it with ``by_module`` transitions after its own event, so a person cannot run a transition
directly.

*Accept* is one unit of work: one ``StockLot`` per line (``Record.Created``, ``StockLot.Defined``
and a ``StockLot.Moved`` of kind ``receive`` into the receipt's location, in one append), a
``derived_from`` link from each lot to the receipt, then ``Receipt.Accepted`` and
``Workflow.Transitioned``. When any line's item category is listed in the project setting
``materials.receipt.mtr_required_categories`` the ``mtr`` slot must hold an available file. The
receipt's number comes from the allocator (``P123-RCPT-0031``, gap-free, inside this transaction).

Messages name a line by its number and never repeat text the caller sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, bindparam, text
from tl_core import confidentiality
from tl_core.files.queries import list_files
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_core.services.records import create_module_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.text import clean_optional_text, clean_text
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_materials.common import (
    correlated,
    dec,
    parse_qty,
    qty_text,
    require_project,
    version_of,
)
from tl_mod_materials.errors import (
    InvalidValueError,
    ItemNotFoundError,
    ItemRetiredError,
    LocationNotFoundError,
    MtrRequiredError,
    NoChangesError,
    PoLineNotFoundError,
    ReceiptNotFoundError,
    ReceiptStateError,
)
from tl_mod_materials.handlers.items import adopt_item, valid_item_code
from tl_mod_materials.limits import (
    HEAT_NO,
    ISO_DATE,
    MAX_DELIVERY_REF,
    MAX_ITEM_CODE,
    MAX_LOCATION_CODE,
    MAX_PO_NUMBER,
    MAX_REASON,
    MAX_RECEIPT_LINES,
    MAX_SERIALS_TEXT,
    MAX_SUPPLIER,
)
from tl_mod_materials.names import (
    DERIVED_FROM,
    LOT_DEFINED,
    LOT_MOVED,
    PROJECT_ITEM_TABLE,
    RECEIPT,
    RECEIPT_ACCEPTED,
    RECEIPT_DEFINED,
    RECEIPT_INSPECTED,
    RECEIPT_LINE_TABLE,
    RECEIPT_REJECTED,
    RECEIPT_REVISED,
    RECEIPT_TABLE,
    RECEIVE,
    REFERENCES,
    STOCK_LOT,
)
from tl_mod_materials.registry import (
    ItemRow,
    LocationRow,
    PoLineRow,
    get_item,
    get_location,
    get_po_line,
    get_project_item,
)

#: Source of the events the module writes on its own account (adoptions, links).
MODULE_SOURCE = "rule"
#: ``ConditionCode`` of ``co.acme.materials@1.0.0`` (a closed list).
CONDITIONS = ("good", "damaged", "wrong_item", "nonconforming")
#: The project setting that lists the categories whose receipts need a material test report.
MTR_SETTING = "materials.receipt.mtr_required_categories"
MTR_SLOT = "mtr"
OPEN_STATES = ("Received", "Inspected")


def _date(value: str) -> str:
    if ISO_DATE.fullmatch(value) is None:
        raise ValueError("a date is written YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("not a calendar date") from exc
    return value


def _reason(value: str) -> str:
    if not value.strip():
        raise ValueError("reason must not be blank")
    return clean_text(value)


class ReceiptLineIn(BaseModel):
    """One line of a delivery. The unit is the item's; ``uom`` may be sent and must equal it."""

    model_config = ConfigDict(extra="forbid")

    item_code: str = Field(min_length=1, max_length=MAX_ITEM_CODE)
    qty: str = Field(min_length=1, max_length=20)
    uom: str | None = Field(default=None, max_length=8)
    heat_no: str | None = Field(default=None, max_length=40)
    condition: str = Field(default="good", max_length=32)
    serials_text: str | None = Field(default=None, max_length=MAX_SERIALS_TEXT)

    @field_validator("item_code")
    @classmethod
    def _check_item(cls, value: str) -> str:
        return valid_item_code(value)

    @field_validator("serials_text")
    @classmethod
    def _check_serials(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class CreateReceipt(Command):
    """Book a delivery: a receipt in state Received with its lines (up to 50)."""

    model_config = ConfigDict(extra="forbid")

    po_line: str | None = Field(default=None, min_length=1, max_length=MAX_PO_NUMBER + 8)
    supplier_text: str = Field(default="", max_length=MAX_SUPPLIER)
    delivery_ref: str | None = Field(default=None, max_length=MAX_DELIVERY_REF)
    received_on: str = Field(min_length=10, max_length=10)
    location_code: str = Field(min_length=1, max_length=MAX_LOCATION_CODE)
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=MAX_RECEIPT_LINES)

    @field_validator("supplier_text")
    @classmethod
    def _check_supplier(cls, value: str) -> str:
        return clean_text(value)

    @field_validator("delivery_ref")
    @classmethod
    def _check_delivery(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("received_on")
    @classmethod
    def _check_date(cls, value: str) -> str:
        return _date(value)


class ReviseReceipt(Command):
    """Correct a receipt that is still Received. Only the fields sent change; ``lines`` replaces
    all the lines; ``po_line`` sent as null takes the PO line away."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str = Field(min_length=1, max_length=64)
    expected_version: int | None = Field(default=None, ge=1)
    po_line: str | None = Field(default=None, min_length=1, max_length=MAX_PO_NUMBER + 8)
    supplier_text: str | None = Field(default=None, max_length=MAX_SUPPLIER)
    delivery_ref: str | None = Field(default=None, max_length=MAX_DELIVERY_REF)
    received_on: str | None = Field(default=None, min_length=10, max_length=10)
    location_code: str | None = Field(default=None, min_length=1, max_length=MAX_LOCATION_CODE)
    lines: list[ReceiptLineIn] | None = Field(
        default=None, min_length=1, max_length=MAX_RECEIPT_LINES
    )

    @field_validator("supplier_text", "delivery_ref")
    @classmethod
    def _check_text(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("received_on")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        return None if value is None else _date(value)


class InspectReceipt(Command):
    """Record that the delivery was looked at (Received to Inspected)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str = Field(min_length=1, max_length=64)
    expected_version: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("notes")
    @classmethod
    def _check_notes(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class AcceptReceipt(Command):
    """Accept an Inspected receipt: its lines become stock lots at the receipt's location."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)


class RejectReceipt(Command):
    """Refuse the delivery (Received or Inspected to Rejected). No stock is made."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str = Field(min_length=1, max_length=64)
    expected_version: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        return _reason(value)


class VoidReceipt(Command):
    """Void a receipt booked in error (Received or Inspected only; never after a decision)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str = Field(min_length=1, max_length=64)
    expected_version: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        return _reason(value)


# --- reads the handlers share ------------------------------------------------------------------


@dataclass(frozen=True)
class ReceiptRow:
    id: str
    key: str
    state: str
    voided: bool
    version: int
    po_line_id: str | None
    supplier_text: str
    delivery_ref: str | None
    received_on: str
    location_id: str


@dataclass(frozen=True)
class LineRow:
    line_no: int
    project_item_id: str
    qty: Decimal
    uom: str
    heat_no: str | None
    condition: str
    serials_text: str | None


@dataclass(frozen=True)
class ItemFacts:
    """A project item with what the receipt rules need of its library item."""

    id: str
    code: str
    title: str
    category: str
    uom: str
    consumable: bool
    retired: bool


_RECEIPT = text(
    "SELECT r.id, r.key, r.status, r.voided, r.version, t.po_line_id, t.supplier_text, "
    "t.delivery_ref, t.received_on, t.location_id "
    f"FROM {RECEIPT_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.id = :id AND t.scope = :scope"
)
_LINES = text(
    "SELECT line_no, project_item_id, qty, uom, heat_no, condition, serials_text "
    f"FROM {RECEIPT_LINE_TABLE} WHERE receipt_id = :id ORDER BY line_no"
)
_ITEMS = text(
    "SELECT p.id, pr.key AS code, pr.title, p.category, p.uom, p.consumable, pr.voided, "
    "m.retired FROM " + PROJECT_ITEM_TABLE + " p JOIN cur_core_record pr ON pr.id = p.id "
    "LEFT JOIN cur_materials_item_master m ON m.id = p.item_master_id WHERE p.id IN :ids"
).bindparams(bindparam("ids", expanding=True))
_PO_LINE_BY_ID = text("SELECT key FROM cur_core_record WHERE id = :id")
_LINK_OF = text(
    "SELECT link_id, version FROM cur_links WHERE from_id = :from_id AND to_id = :to_id "
    "AND relation = :relation AND status = 'active'"
)


def _today() -> str:
    return utcnow().date().isoformat()


def load_receipt(uow: UnitOfWork, cmd: Command, stream_id: str) -> ReceiptRow:
    """The receipt in the command's project, readable by the viewer (else it never existed)."""
    conn = uow.conn()
    row = conn.execute(_RECEIPT, {"id": stream_id, "scope": cmd.scope}).first()
    if row is None or confidentiality.is_hidden(conn, stream_id):
        raise ReceiptNotFoundError(f"no receipt {stream_id!r} in {cmd.scope}")
    return ReceiptRow(
        id=str(row.id),
        key=str(row.key),
        state="Received" if row.status is None else str(row.status),
        voided=bool(row.voided),
        version=int(row.version),
        po_line_id=None if row.po_line_id is None else str(row.po_line_id),
        supplier_text=str(row.supplier_text),
        delivery_ref=None if row.delivery_ref is None else str(row.delivery_ref),
        received_on=str(row.received_on),
        location_id=str(row.location_id),
    )


def load_lines(conn: Connection, receipt_id: str) -> list[LineRow]:
    return [
        LineRow(
            line_no=int(r.line_no),
            project_item_id=str(r.project_item_id),
            qty=dec(r.qty),
            uom=str(r.uom),
            heat_no=None if r.heat_no is None else str(r.heat_no),
            condition=str(r.condition),
            serials_text=None if r.serials_text is None else str(r.serials_text),
        )
        for r in conn.execute(_LINES, {"id": receipt_id})
    ]


def _require_state(receipt: ReceiptRow, states: tuple[str, ...], what: str) -> None:
    """Refuse a receipt that is voided or not in one of ``states`` (fixed message)."""
    if receipt.voided or receipt.state not in states:
        state = "Void" if receipt.voided else receipt.state
        raise ReceiptStateError(f"receipt {receipt.key} is {state}; {what}")


def _append(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    events: list[NewEvent],
    expected: int | None,
) -> AppendResult:
    return uow.append(
        stream_id=stream_id,
        stream_type=RECEIPT,
        scope=cmd.scope,
        expected_version=expected if expected is not None else version_of(uow, stream_id),
        events=events,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )


def _transition(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    name: str,
    reason: str | None = None,
    expected: int | None = None,
) -> CommandResult:
    return handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            stream_id=stream_id,
            expected_version=expected if expected is not None else version_of(uow, stream_id),
            transition=name,
            reason=reason,
        ),
        by_module=True,
    )


def _link(uow: UnitOfWork, cmd: Command, from_id: str, to_id: str, relation: str) -> list[Any]:
    done = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=from_id,
            to_id=to_id,
            relation=relation,
            link_source="rule",
        ),
        by_module=True,
    )
    return list(done.events)


def _retract_link(uow: UnitOfWork, cmd: Command, from_id: str, to_id: str, why: str) -> list[Any]:
    found = (
        uow.conn()
        .execute(_LINK_OF, {"from_id": from_id, "to_id": to_id, "relation": REFERENCES})
        .first()
    )
    if found is None:
        return []
    done = handle_retract_link(
        uow,
        RetractLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            link_id=str(found.link_id),
            reason=why,
        ),
        by_module=True,
    )
    return list(done.events)


# --- the rules of a delivery's lines -----------------------------------------------------------


@dataclass(frozen=True)
class CheckedLine:
    line_no: int
    item_id: str | None  # None: the library item must be adopted first (``master``)
    master: ItemRow | None
    qty: Decimal
    uom: str
    heat_no: str | None
    condition: str
    serials_text: str | None


def check_po_line(conn: Connection, scope: str, key: str) -> PoLineRow:
    po = get_po_line(conn, scope, key)
    if po is None:
        raise PoLineNotFoundError(f"no PO line {key!r} in {scope}")
    confidentiality.require_visible(conn, po.id)
    return po


def check_location(conn: Connection, scope: str, code: str) -> LocationRow:
    """An active location of the project the viewer may read."""
    found = get_location(conn, scope, code)
    if found is None or confidentiality.is_hidden(conn, found.id):
        raise LocationNotFoundError(f"no location {code!r} in {scope}")
    if found.retired:
        raise InvalidValueError("the location is retired and takes no stock")
    return found


def check_lines(conn: Connection, scope: str, lines: list[ReceiptLineIn]) -> list[CheckedLine]:
    """Every rule of a line that does not depend on the other lines: quantity, heat number,
    condition, serials, and the item (the project's copy, else a library item to adopt)."""
    checked: list[CheckedLine] = []
    for number, line in enumerate(lines, start=1):
        qty = parse_qty(line.qty, f"line {number} qty")
        if line.heat_no is not None and HEAT_NO.fullmatch(line.heat_no) is None:
            raise InvalidValueError(
                f"line {number}: heat_no is letters, digits, '.', '/' or '-', at most 40"
            )
        if line.condition not in CONDITIONS:
            raise InvalidValueError(
                f"line {number}: condition must be one of: {', '.join(CONDITIONS)}"
            )
        copy = get_project_item(conn, scope, line.item_code)
        master: ItemRow | None = None
        if copy is not None:
            confidentiality.require_visible(conn, copy.id)
            uom = copy.uom
        else:
            master = get_item(conn, line.item_code)
            if master is None or confidentiality.is_hidden(conn, master.id):
                raise ItemNotFoundError(f"line {number}: the item is not in the library")
            if master.retired:
                raise ItemRetiredError(f"line {number}: the item is retired")
            uom = master.base_uom
        if line.uom is not None and line.uom != uom:
            raise InvalidValueError(f"line {number}: uom must be the unit of the item")
        checked.append(
            CheckedLine(
                line_no=number,
                item_id=None if copy is None else copy.id,
                master=master,
                qty=qty,
                uom=uom,
                heat_no=line.heat_no,
                condition=line.condition,
                serials_text=line.serials_text,
            )
        )
    return checked


def check_lines_against_po(po: PoLineRow | None, items: list[str | None]) -> None:
    """A delivery against a PO line carries that line's item (``None``: not adopted, so not it)."""
    if po is None:
        return
    for number, item_id in enumerate(items, start=1):
        if item_id != po.project_item_id:
            raise InvalidValueError(f"line {number}: the item is not the item of the PO line")


def _adopt_missing(
    uow: UnitOfWork, cmd: Command, lines: list[CheckedLine]
) -> tuple[list[str], list[Any]]:
    """Adopt the library items the lines need (once each); return the item id per line and the
    events the adoptions wrote."""
    adopted: dict[str, str] = {}
    events: list[Any] = []
    ids: list[str] = []
    module_cmd = cmd.model_copy(update={"source": MODULE_SOURCE})
    for line in lines:
        if line.item_id is not None:
            ids.append(line.item_id)
            continue
        assert line.master is not None
        if line.master.code not in adopted:
            made = adopt_item(uow, module_cmd, line.master)
            adopted[line.master.code] = made.stream_id
            events.extend(made.events)
        ids.append(adopted[line.master.code])
    return ids, events


def _line_payload(line: CheckedLine, item_id: str) -> dict[str, Any]:
    return {
        "line_no": line.line_no,
        "project_item_id": item_id,
        "qty": qty_text(line.qty),
        "uom": line.uom,
        "heat_no": line.heat_no,
        "condition": line.condition,
        "serials_text": line.serials_text,
    }


# --- CreateReceipt -----------------------------------------------------------------------------


def handle_create_receipt(uow: UnitOfWork, cmd: CreateReceipt) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    where = check_location(conn, cmd.scope, cmd.location_code)
    po = None if cmd.po_line is None else check_po_line(conn, cmd.scope, cmd.po_line)
    checked = check_lines(conn, cmd.scope, cmd.lines)
    check_lines_against_po(po, [c.item_id for c in checked])
    supplier = cmd.supplier_text or (po.supplier_text if po is not None else "")
    item_ids, events = _adopt_missing(uow, cmd, checked)
    made = create_module_record(
        uow,
        cmd,
        record_type=RECEIPT,
        title=f"Receipt from {supplier}" if supplier else "Receipt",
        key=None,
        extra_events=[
            NewEvent(
                event_type=RECEIPT_DEFINED,
                payload={
                    "po_line_id": None if po is None else po.id,
                    "supplier_text": supplier,
                    "delivery_ref": cmd.delivery_ref,
                    "received_on": cmd.received_on,
                    "location_id": where.id,
                    "lines": [_line_payload(c, i) for c, i in zip(checked, item_ids, strict=True)],
                },
            )
        ],
    )
    events.extend(made.events)
    if po is not None:
        events.extend(_link(uow, cmd, made.stream_id, po.id, REFERENCES))
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=version_of(uow, made.stream_id),
        events=events,
    )


# --- ReviseReceipt -----------------------------------------------------------------------------


def _same_lines(old: list[LineRow], new: list[dict[str, Any]]) -> bool:
    if len(old) != len(new):
        return False
    return all(
        (o.line_no, o.project_item_id, o.qty, o.uom, o.heat_no, o.condition, o.serials_text)
        == (
            int(n["line_no"]),
            n["project_item_id"],
            Decimal(n["qty"]),
            n["uom"],
            n["heat_no"],
            n["condition"],
            n["serials_text"],
        )
        for o, n in zip(old, new, strict=True)
    )


def handle_revise_receipt(uow: UnitOfWork, cmd: ReviseReceipt) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    receipt = load_receipt(uow, cmd, cmd.stream_id)
    _require_state(receipt, ("Received",), "only a receipt that is Received can be revised")
    sent = cmd.model_fields_set
    payload: dict[str, Any] = {}
    events: list[Any] = []
    new_po: PoLineRow | None = None
    po_changed = False
    if "po_line" in sent:
        if cmd.po_line is None:
            po_changed = receipt.po_line_id is not None
            payload["po_line_id"] = None
        else:
            new_po = check_po_line(conn, cmd.scope, cmd.po_line)
            po_changed = new_po.id != receipt.po_line_id
            if po_changed:
                payload["po_line_id"] = new_po.id
    if "supplier_text" in sent and cmd.supplier_text is not None:
        if cmd.supplier_text != receipt.supplier_text:
            payload["supplier_text"] = cmd.supplier_text
    if "delivery_ref" in sent and cmd.delivery_ref != receipt.delivery_ref:
        payload["delivery_ref"] = cmd.delivery_ref
    if "received_on" in sent and cmd.received_on is not None:
        if cmd.received_on != receipt.received_on:
            payload["received_on"] = cmd.received_on
    if "location_code" in sent and cmd.location_code is not None:
        where = check_location(conn, cmd.scope, cmd.location_code)
        if where.id != receipt.location_id:
            payload["location_id"] = where.id
    current = load_lines(conn, receipt.id)
    new_lines: list[dict[str, Any]] | None = None
    if "lines" in sent and cmd.lines is not None:
        checked = check_lines(conn, cmd.scope, cmd.lines)
        po_now = new_po if "po_line" in sent and cmd.po_line is not None else None
        if po_now is None and "po_line" not in sent and receipt.po_line_id is not None:
            po_now = _po_by_id(conn, cmd.scope, receipt.po_line_id)
        check_lines_against_po(po_now, [c.item_id for c in checked])
        item_ids, adopted = _adopt_missing(uow, cmd, checked)
        events.extend(adopted)
        new_lines = [_line_payload(c, i) for c, i in zip(checked, item_ids, strict=True)]
        if not _same_lines(current, new_lines):
            payload["lines"] = new_lines
    elif po_changed and new_po is not None:
        check_lines_against_po(new_po, [line.project_item_id for line in current])
    if not payload:
        raise NoChangesError(f"the revision changes nothing in receipt {receipt.key}")
    done = _append(
        uow,
        cmd,
        receipt.id,
        [NewEvent(event_type=RECEIPT_REVISED, payload=payload)],
        cmd.expected_version,
    )
    events.extend(done.events)
    if po_changed:
        if receipt.po_line_id is not None:
            events.extend(
                _retract_link(uow, cmd, receipt.id, receipt.po_line_id, "PO line changed")
            )
        if new_po is not None:
            events.extend(_link(uow, cmd, receipt.id, new_po.id, REFERENCES))
    return CommandResult(
        stream_id=receipt.id, key=receipt.key, version=version_of(uow, receipt.id), events=events
    )


def _po_by_id(conn: Connection, scope: str, po_id: str) -> PoLineRow | None:
    key = conn.execute(_PO_LINE_BY_ID, {"id": po_id}).scalar_one_or_none()
    return None if key is None else get_po_line(conn, scope, str(key))


# --- InspectReceipt, RejectReceipt, VoidReceipt ------------------------------------------------


def handle_inspect_receipt(uow: UnitOfWork, cmd: InspectReceipt) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    receipt = load_receipt(uow, cmd, cmd.stream_id)
    _require_state(receipt, ("Received",), "only a receipt that is Received can be inspected")
    done = _append(
        uow,
        cmd,
        receipt.id,
        [
            NewEvent(
                event_type=RECEIPT_INSPECTED,
                payload={
                    "inspected_by": cmd.actor,
                    "inspected_on": _today(),
                    "notes": cmd.notes,
                },
            )
        ],
        cmd.expected_version,
    )
    moved = _transition(uow, cmd, receipt.id, "inspect")
    return CommandResult(
        stream_id=receipt.id,
        key=receipt.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def handle_reject_receipt(uow: UnitOfWork, cmd: RejectReceipt) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    receipt = load_receipt(uow, cmd, cmd.stream_id)
    _require_state(
        receipt, OPEN_STATES, "only a receipt that is Received or Inspected can be rejected"
    )
    done = _append(
        uow,
        cmd,
        receipt.id,
        [
            NewEvent(
                event_type=RECEIPT_REJECTED,
                payload={"decided_by": cmd.actor, "decided_on": _today(), "reason": cmd.reason},
            )
        ],
        cmd.expected_version,
    )
    moved = _transition(uow, cmd, receipt.id, "reject", cmd.reason)
    return CommandResult(
        stream_id=receipt.id,
        key=receipt.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def handle_void_receipt(uow: UnitOfWork, cmd: VoidReceipt) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    receipt = load_receipt(uow, cmd, cmd.stream_id)
    _require_state(
        receipt, OPEN_STATES, "only a receipt that is Received or Inspected can be voided"
    )
    moved = _transition(uow, cmd, receipt.id, "void", cmd.reason, cmd.expected_version)
    done = _append(
        uow,
        cmd,
        receipt.id,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
        None,
    )
    return CommandResult(
        stream_id=receipt.id,
        key=receipt.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )


# --- AcceptReceipt -----------------------------------------------------------------------------


def _item_facts(conn: Connection, ids: list[str]) -> dict[str, ItemFacts]:
    found: dict[str, ItemFacts] = {}
    for r in conn.execute(_ITEMS, {"ids": sorted(set(ids))}):
        if bool(r.voided):
            continue
        found[str(r.id)] = ItemFacts(
            id=str(r.id),
            code=str(r.code),
            title=str(r.title),
            category=str(r.category),
            uom=str(r.uom),
            consumable=bool(r.consumable),
            retired=bool(r.retired) if r.retired is not None else False,
        )
    return found


def mtr_required_lines(
    conn: Connection, scope: str, lines: list[LineRow], items: dict[str, ItemFacts]
) -> int:
    """How many lines are of a category the project setting says needs a material test report."""
    listed = value_of(conn, MTR_SETTING, project=project_of_scope(scope))
    required = {str(c) for c in listed} if isinstance(listed, list | tuple) else set()
    return sum(
        1
        for line in lines
        if line.project_item_id in items and items[line.project_item_id].category in required
    )


def has_mtr(uow: UnitOfWork, scope: str, receipt_id: str) -> bool:
    return bool(list_files(uow, scope, receipt_id, slot=MTR_SLOT, current_only=True))


def handle_accept_receipt(uow: UnitOfWork, cmd: AcceptReceipt) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    receipt = load_receipt(uow, cmd, cmd.stream_id)
    _require_state(receipt, ("Inspected",), "only a receipt that is Inspected can be accepted")
    lines = load_lines(conn, receipt.id)
    items = _item_facts(conn, [line.project_item_id for line in lines])
    for line in lines:
        facts = items.get(line.project_item_id)
        if facts is None:
            raise ItemNotFoundError(f"line {line.line_no}: the item no longer exists")
        if facts.retired:
            raise ItemRetiredError(f"line {line.line_no}: the item is retired")
    needing = mtr_required_lines(conn, cmd.scope, lines, items)
    if needing and not has_mtr(uow, cmd.scope, receipt.id):
        raise MtrRequiredError(f"an MTR is required for {needing} lines; attach it in the MTR slot")
    where = get_location_by_id(conn, receipt.location_id)
    if where is None or where.retired:
        raise InvalidValueError("the location of the receipt is retired and takes no stock")

    events: list[Any] = []
    lots: list[dict[str, Any]] = []
    for line in lines:
        facts = items[line.project_item_id]
        key = f"{receipt.key}@{line.line_no}"
        made = create_module_record(
            uow,
            cmd,
            record_type=STOCK_LOT,
            title=f"{line.heat_no} {facts.title}" if line.heat_no else facts.title,
            key=key,
            composed_key=True,
            extra_events=[
                NewEvent(
                    event_type=LOT_DEFINED,
                    payload={
                        "project_item_id": line.project_item_id,
                        "heat_no": line.heat_no,
                        "receipt_id": receipt.id,
                        "receipt_line": line.line_no,
                        "uom": line.uom,
                    },
                ),
                NewEvent(
                    event_type=LOT_MOVED,
                    payload={
                        "kind": RECEIVE,
                        "qty": qty_text(line.qty),
                        "uom": line.uom,
                        "direction": None,
                        "from_location_id": None,
                        "to_location_id": receipt.location_id,
                        "cost_code_id": None,
                        "mto_line_id": None,
                        "iwp_id": None,
                        "requisition_id": None,
                        "person": None,
                        "reason": None,
                        "feed_policy": "none",
                    },
                ),
            ],
        )
        events.extend(made.events)
        events.extend(_link(uow, cmd, made.stream_id, receipt.id, DERIVED_FROM))
        lots.append({"line": line.line_no, "lot_id": made.stream_id})
    accepted = _append(
        uow,
        cmd,
        receipt.id,
        [
            NewEvent(
                event_type=RECEIPT_ACCEPTED,
                payload={"decided_by": cmd.actor, "decided_on": _today(), "lots": lots},
            )
        ],
        cmd.expected_version,
    )
    events.extend(accepted.events)
    moved = _transition(uow, cmd, receipt.id, "accept")
    events.extend(moved.events)
    return CommandResult(
        stream_id=receipt.id, key=receipt.key, version=moved.version, events=events
    )


_LOCATION_BY_ID = text(
    "SELECT t.id, t.code, r.title, t.kind, t.parent_id, t.depth, t.retired "
    "FROM cur_materials_location t JOIN cur_core_record r ON r.id = t.id WHERE t.id = :id"
)


def get_location_by_id(conn: Connection, location_id: str) -> LocationRow | None:
    row = conn.execute(_LOCATION_BY_ID, {"id": location_id}).first()
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


__all__ = [
    "CONDITIONS",
    "AcceptReceipt",
    "CreateReceipt",
    "InspectReceipt",
    "RejectReceipt",
    "ReviseReceipt",
    "VoidReceipt",
    "handle_accept_receipt",
    "handle_create_receipt",
    "handle_inspect_receipt",
    "handle_reject_receipt",
    "handle_revise_receipt",
    "handle_void_receipt",
]
