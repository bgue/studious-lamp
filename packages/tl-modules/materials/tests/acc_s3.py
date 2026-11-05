"""Helpers and checks of the S3 module tests (receipts, movements, actions, hidden records)."""

from __future__ import annotations

import hashlib
import io
import threading
import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core import confidentiality
from tl_core.actions import allowed_actions
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import Holder, require_command_access
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.modules import ConfidentialSource, load_modules, use_modules
from tl_core.services import proposals
from tl_core.services.commands import Command, CommandResult
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.util import new_ulid
from tl_mod_materials import views
from tl_mod_materials.actions import RULES, rule_rows
from tl_mod_materials.api import PostedMovement, post_movements
from tl_mod_materials.commands import MATERIALS_COMMANDS
from tl_mod_materials.errors import (
    InsufficientStockError,
    InvalidQuantityError,
    LotNotFoundError,
    MovementRuleError,
    MtrRequiredError,
    NoChangesError,
    ReceiptNotFoundError,
    ReceiptStateError,
)
from tl_mod_materials.guards import receipt_upload_guard
from tl_mod_materials.handlers.items import (
    AdoptItem,
    DefineItem,
    handle_adopt_item,
    handle_define_item,
)
from tl_mod_materials.handlers.locations import (
    DefineLocation,
    RetireLocation,
    handle_define_location,
    handle_retire_location,
)
from tl_mod_materials.handlers.movements import (
    AdjustStock,
    IssueStock,
    Movement,
    ReserveStock,
    ReturnStock,
    ScrapStock,
    TransferStock,
    UnreserveStock,
    handle_adjust_stock,
    handle_issue_stock,
    handle_reserve_stock,
    handle_return_stock,
    handle_scrap_stock,
    handle_transfer_stock,
    handle_unreserve_stock,
)
from tl_mod_materials.handlers.po_lines import RecordPoLine, handle_record_po_line
from tl_mod_materials.handlers.receipts import (
    AcceptReceipt,
    CreateReceipt,
    InspectReceipt,
    RejectReceipt,
    ReviseReceipt,
    VoidReceipt,
    handle_accept_receipt,
    handle_create_receipt,
    handle_inspect_receipt,
    handle_reject_receipt,
    handle_revise_receipt,
    handle_void_receipt,
)

ACTOR = "user:accept"
SOURCE = "accept"
COMPANY = "company"
SUPER = "user:materials-super"
PLAIN = "user:plain"
MTR_KEY = "materials.receipt.mtr_required_categories"
D = Decimal
MESSAGE_NO_MTR = "an MTR is required for 2 lines; attach it in the MTR slot"
TABLES = [
    "cur_materials_item_master",
    "cur_materials_project_item",
    "cur_materials_location",
    "cur_materials_po_line",
    "cur_materials_receipt",
    "cur_materials_receipt_line",
    "cur_materials_lot",
    "cur_materials_mto",
    "cur_materials_mto_line",
    "cur_materials_movement",
    "cur_materials_stock",
    "cur_materials_reservation",
]
SPEC_WORDS = {
    "CreateReceipt": "materials.receive",
    "ReviseReceipt": "materials.receive",
    "InspectReceipt": "materials.receive",
    "AcceptReceipt": "materials.receipt.decide",
    "RejectReceipt": "materials.receipt.decide",
    "VoidReceipt": "materials.void",
    "IssueStock": "materials.move",
    "TransferStock": "materials.move",
    "ReturnStock": "materials.move",
    "ReserveStock": "materials.reserve",
    "UnreserveStock": "materials.reserve",
    "AdjustStock": "materials.adjust",
    "ScrapStock": "materials.adjust",
}


def holder(actor: str, *roles: str) -> Holder:
    return Holder(actor=actor, kind="person", account_id=f"dev:{actor}", account_roles=roles)


USER = holder(PLAIN, "user")
BOSS = holder(SUPER, "admin")
AGENT = Holder(actor="agent:helper", kind="agent", account_id="dev:agent:helper", account_roles=())


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


def expect_refused(
    call: Callable[[], object],
    error: type[BaseException] | tuple[type[BaseException], ...],
    what: str,
) -> BaseException:
    try:
        call()
    except error as caught:
        return caught
    raise AssertionError(f"{what}: expected {error}, nothing was refused")


class World:
    """One empty ledger, a project in it, and the calls a check makes against it."""

    def __init__(self, target: DbTarget, objects: Path) -> None:
        self.target = target
        self.tag = uuid.uuid4().hex[:8].upper()
        self.project = "project:A" + self.tag
        self.number = "A" + self.tag
        self.files = FileService(FsObjectStore(objects, secret=b"s"), secret=b"s")

    def code(self, prefix: str) -> str:
        return f"{prefix}-{self.tag}"

    # --- commands and reads ---------------------------------------------------------------

    def run(
        self,
        handler: Callable[[Any, Any], CommandResult],
        command_type: type[Command],
        *,
        actor: str = ACTOR,
        scope: str | None = None,
        **fields: Any,
    ) -> CommandResult:
        command = command_type(actor=actor, source=SOURCE, scope=scope or self.project, **fields)  # type: ignore[call-arg]
        with open_uow(self.target) as uow:
            return handler(uow, command)

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.target, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def one(self, sql: str, **params: Any) -> dict[str, Any]:
        found = self.rows(sql, **params)
        assert len(found) == 1, (sql, found)
        return found[0]

    def events(self) -> int:
        return int(self.one("SELECT COUNT(*) AS n FROM events")["n"])

    def id_of(self, key: str, scope: str | None = None) -> str:
        return str(
            self.one(
                "SELECT id FROM cur_core_record WHERE scope = :s AND key = :k",
                s=scope or self.project,
                k=key,
            )["id"]
        )

    def status(self, record_id: str) -> tuple[str | None, bool]:
        row = self.one("SELECT status, voided FROM cur_core_record WHERE id = :i", i=record_id)
        return row["status"], bool(row["voided"])

    def refused(
        self,
        call: Callable[[], object],
        error: type[BaseException] | tuple[type[BaseException], ...],
        what: str,
    ) -> BaseException:
        """``call`` is refused with ``error`` and the ledger holds the same events afterwards."""
        before = self.events()
        caught = expect_refused(call, error, what)
        assert self.events() == before, f"{what}: the refusal wrote events"
        return caught

    def create(
        self,
        record_type: str,
        key: str,
        title: str,
        events: list[NewEvent] | None = None,
        scope: str | None = None,
    ) -> str:
        """A record made by hand through the ledger: ``Record.Created`` then ``events``."""
        stream = new_ulid()
        created = NewEvent(
            event_type="Record.Created",
            payload={
                "record_type": record_type,
                "key": key,
                "title": title,
                "description": None,
                "psets": {},
            },
        )
        with open_uow(self.target) as uow:
            uow.append(
                stream_id=stream,
                stream_type=record_type,
                scope=scope or self.project,
                expected_version=0,
                events=[created, *(events or [])],
                actor=ACTOR,
                source=SOURCE,
                correlation_id=new_ulid(),
            )
        return stream

    # --- the project: tree, items, setting, PO line, cost code, take-off -------------------

    def tree(self) -> None:
        for code, kind, parent in [
            ("P1", "project", None),
            ("WH", "warehouse", "P1"),
            ("LA", "laydown", "WH"),
            ("LB", "laydown", "WH"),
        ]:
            self.run(
                handle_define_location,
                DefineLocation,
                code=code,
                title=code,
                kind=kind,
                parent_code=parent,
            )

    def item(
        self, code: str, *, category: str = "other", uom: str = "EA", consumable: bool = False
    ) -> str:
        """A library item adopted into the project; the project item's id."""
        self.run(
            handle_define_item,
            DefineItem,
            scope=COMPANY,
            code=code,
            title=f"Item {code}",
            category=category,
            base_uom=uom,
            consumable=consumable,
        )
        return self.run(handle_adopt_item, AdoptItem, item_code=code).stream_id

    def require_mtr(self, *categories: str) -> None:
        self.run(
            handle_change_setting,
            ChangeSetting,
            key=MTR_KEY,
            layer=self.project,
            value=list(categories),
        )

    def mto_line(
        self, item_id: str, qty: str, *, work_package: str | None = None, n: int = 1
    ) -> str:
        mto = self.rows(
            "SELECT id FROM cur_core_record WHERE type = 'materials.MTO' AND scope = :s",
            s=self.project,
        )
        mto_id = (
            mto[0]["id"]
            if mto
            else self.create(
                "materials.MTO",
                f"ISO-{self.tag}@A/MTO",
                "MTO",
                [
                    NewEvent(
                        event_type="MTO.Defined",
                        payload={
                            "derived_document_id": new_ulid(),
                            "revision_id": new_ulid(),
                            "line_count": 3,
                        },
                    )
                ],
            )
        )
        return self.create(
            "materials.MTOLine",
            f"ISO-{self.tag}@A/MTO/{n:03d}-{uuid.uuid4().hex[:4]}",
            f"Line {n}",
            [
                NewEvent(
                    event_type="MTOLine.Defined",
                    payload={
                        "mto_id": mto_id,
                        "line_no": n,
                        "project_item_id": item_id,
                        "qty": qty,
                        "uom": "EA",
                        "tag_id": None,
                        "work_package_id": work_package,
                    },
                )
            ],
        )

    # --- a delivery, from booking to stock -------------------------------------------------

    def attach_mtr(self, receipt_id: str, data: bytes = b"%PDF-1.4 mill test report") -> None:
        base = {"actor": ACTOR, "source": SOURCE, "scope": self.project}
        declared = RegisterUpload(
            **base,
            record_id=receipt_id,
            slot="mtr",
            filename="mtr.pdf",
            content_type="application/pdf",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        with open_uow(self.target) as uow:
            ticket = self.files.register_upload(uow, declared, by_module=True)
        with open_uow(self.target) as uow:
            self.files.complete_upload(
                uow,
                CompleteUpload(**base, upload_id=ticket.upload_id),
                io.BytesIO(data),
                by_module=True,
            )

    def deliver(
        self,
        lines: list[dict[str, Any]],
        *,
        location: str = "LA",
        po_line: str | None = None,
        mtr: bool = False,
        **more: Any,
    ) -> CommandResult:
        """Create, inspect, (attach the MTR) and accept a receipt; the accept's result."""
        made = self.run(
            handle_create_receipt,
            CreateReceipt,
            received_on="2026-11-02",
            location_code=location,
            po_line=po_line,
            lines=lines,
            **more,
        )
        self.run(handle_inspect_receipt, InspectReceipt, stream_id=made.stream_id)
        if mtr:
            self.attach_mtr(made.stream_id)
        version = self.one("SELECT version FROM cur_core_record WHERE id = :i", i=made.stream_id)
        return self.run(
            handle_accept_receipt,
            AcceptReceipt,
            stream_id=made.stream_id,
            expected_version=version["version"],
        )

    def lot(self, receipt_id: str, line_no: int = 1) -> str:
        return str(
            self.one(
                "SELECT lot_id FROM cur_materials_receipt_line WHERE receipt_id = :r "
                "AND line_no = :n",
                r=receipt_id,
                n=line_no,
            )["lot_id"]
        )

    def lot_key(self, lot_id: str) -> str:
        return str(self.one("SELECT key FROM cur_core_record WHERE id = :i", i=lot_id)["key"])

    def balance(self, lot_id: str, location_code: str) -> tuple[Decimal, Decimal, Decimal] | None:
        found = self.rows(
            "SELECT on_hand, reserved, available FROM cur_materials_stock WHERE lot_id = :l "
            "AND location_id = :c",
            l=lot_id,
            c=self.id_of(location_code),
        )
        if not found:
            return None
        row = found[0]
        return dec(row["on_hand"]), dec(row["reserved"]), dec(row["available"])


def mv(lot_key: str, qty: str, **more: Any) -> Movement:
    return Movement(lot_key=lot_key, qty=qty, uom=more.pop("uom", "EA"), **more)


class Stocked:
    """A project with a flange receipt accepted (lots of 12 and 8 at LA) and a consumable lot."""

    def __init__(self, w: World) -> None:
        w.tree()
        self.flange = w.item(w.code("FLG"), category="flange")
        self.glove = w.item(w.code("GLV"), category="consumable", uom="kg", consumable=True)
        self.other = w.item(w.code("OTH"))
        w.require_mtr("flange")
        po = w.run(
            handle_record_po_line,
            RecordPoLine,
            po_number="4471",
            line_no=3,
            item_code=w.code("FLG"),
            qty_ordered="20",
            uom="EA",
            supplier_text="Acme Valves",
        )
        self.po = po.stream_id
        made = w.run(
            handle_create_receipt,
            CreateReceipt,
            received_on="2026-11-02",
            location_code="LA",
            po_line="4471-3",
            lines=[
                {"item_code": w.code("FLG"), "qty": "12.000", "heat_no": "H-7781"},
                {"item_code": w.code("FLG"), "qty": "8.000", "heat_no": "H-7781"},
            ],
        )
        self.receipt = made.stream_id
        w.run(handle_inspect_receipt, InspectReceipt, stream_id=self.receipt)
        w.attach_mtr(self.receipt)
        version = w.one("SELECT version FROM cur_core_record WHERE id = :i", i=self.receipt)
        w.run(
            handle_accept_receipt,
            AcceptReceipt,
            stream_id=self.receipt,
            expected_version=version["version"],
        )
        self.lot1, self.lot2 = w.lot(self.receipt, 1), w.lot(self.receipt, 2)
        self.key1, self.key2 = w.lot_key(self.lot1), w.lot_key(self.lot2)
        gloves = w.deliver([{"item_code": w.code("GLV"), "qty": "10.000"}], location="LB")
        self.glove_lot = w.lot(gloves.stream_id)
        self.glove_key = w.lot_key(self.glove_lot)
        self.cost_code = w.create("cost.CostCode", "4210-PIP", "Piping")
        self.iwp = w.create("awp.IWP", "P1-IWP-0001", "IWP 1")
        self.line = w.mto_line(self.flange, "6.000", work_package=self.iwp)
        self.line_other = w.mto_line(self.other, "2.000", n=2)


# --- the checks ----------------------------------------------------------------------------------


def check_module(w: World) -> None:
    spec = {m.name: m for m in load_modules()}["materials"]
    names = {c.model.__name__: c.access for c in MATERIALS_COMMANDS}
    assert {k: v for k, v in names.items() if k in SPEC_WORDS} == SPEC_WORDS, names
    assert set(SPEC_WORDS) <= set(names) and len(names) >= 22, names
    assert len(MATERIALS_COMMANDS) == len(names)  # no command twice
    assert dict(spec.command_words) == names
    assert spec.offline_drafts == {
        "materials.StockLot": frozenset({"IssueStock", "TransferStock", "ReturnStock"})
    }
    assert [p.tool for p in spec.proposable] == ["propose_reservation"]
    assert spec.proposable[0].model is ReserveStock and spec.proposable[0].access == "user"
    import tl_mod_materials.commands as commands_module

    assert not hasattr(commands_module, "DRAFT_COMMAND_WORDS")
    # every row of RULES names a command of the table with that command's access word
    for rule in rule_rows():
        assert rule.command in names, rule
        assert names[rule.command] == rule.word, rule
    assert len(RULES) >= 18


def check_receipts(w: World) -> None:
    w.tree()
    flange = w.code("FLG")
    w.item(flange, category="flange")
    w.require_mtr("flange")
    po = w.run(
        handle_record_po_line,
        RecordPoLine,
        po_number="4471",
        line_no=3,
        item_code=flange,
        qty_ordered="20",
        uom="EA",
        supplier_text="Acme Valves",
    )
    lines = [
        {"item_code": flange, "qty": "12.000", "heat_no": "H-7781", "condition": "good"},
        {"item_code": flange, "qty": "7.000", "heat_no": "H-7781"},
    ]
    # an unknown item is refused and burns no number
    w.refused(
        lambda: w.run(
            handle_create_receipt,
            CreateReceipt,
            received_on="2026-11-02",
            location_code="LA",
            lines=[{"item_code": w.code("NOPE"), "qty": "1"}],
        ),
        Exception,
        "a receipt of an item not in the library",
    )
    w.refused(
        lambda: w.run(
            handle_create_receipt,
            CreateReceipt,
            received_on="2026-11-02",
            location_code="LA",
            po_line="4471-3",
            lines=[{"item_code": w.code("NOPE"), "qty": "1"}],
        ),
        Exception,
        "a delivery of another item than the PO line's",
    )
    made = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-02",
        location_code="LA",
        po_line="4471-3",
        lines=lines,
    )
    rid = made.stream_id
    assert made.key == f"{w.number}-RCPT-0001", made.key
    row = w.one("SELECT * FROM cur_materials_receipt WHERE id = :i", i=rid)
    assert row["po_line_id"] == po.stream_id and row["supplier_text"] == "Acme Valves"
    assert row["location_id"] == w.id_of("LA") and row["received_on"] == "2026-11-02"
    assert w.status(rid) == (None, False)  # Received is the initial state
    assert len(w.rows("SELECT 1 FROM cur_materials_receipt_line WHERE receipt_id = :r", r=rid)) == 2
    link = w.one(
        "SELECT relation, status FROM cur_links WHERE from_id = :f AND to_id = :t",
        f=rid,
        t=po.stream_id,
    )
    assert (link["relation"], link["status"]) == ("references", "active")
    # revise: changes the delivery ref and the second line; the same revision again changes nothing
    w.run(
        handle_revise_receipt,
        ReviseReceipt,
        stream_id=rid,
        delivery_ref="DN-8841",
        lines=[lines[0], {"item_code": flange, "qty": "8.000", "heat_no": "H-7781"}],
    )
    assert (
        w.one("SELECT delivery_ref FROM cur_materials_receipt WHERE id = :i", i=rid)["delivery_ref"]
        == "DN-8841"
    )
    quantities = [
        dec(r["qty"])
        for r in w.rows(
            "SELECT qty FROM cur_materials_receipt_line WHERE receipt_id = :r ORDER BY line_no",
            r=rid,
        )
    ]
    assert quantities == [D(12), D(8)], quantities
    w.refused(
        lambda: w.run(handle_revise_receipt, ReviseReceipt, stream_id=rid, delivery_ref="DN-8841"),
        NoChangesError,
        "a revision that changes nothing",
    )
    # the PO line can be taken off and put back; its link follows (retracted, then added again)
    w.run(handle_revise_receipt, ReviseReceipt, stream_id=rid, po_line=None)
    assert (
        w.one("SELECT po_line_id FROM cur_materials_receipt WHERE id = :i", i=rid)["po_line_id"]
        is None
    )
    assert w.one("SELECT status FROM cur_links WHERE from_id = :f", f=rid)["status"] == "retracted"
    w.run(handle_revise_receipt, ReviseReceipt, stream_id=rid, po_line="4471-3")
    states = [
        r["status"]
        for r in w.rows(
            "SELECT status FROM cur_links WHERE from_id = :f ORDER BY created_at, link_id", f=rid
        )
    ]
    assert sorted(states) == ["active", "retracted"], states
    w.refused(
        lambda: w.run(handle_accept_receipt, AcceptReceipt, stream_id=rid, expected_version=1),
        ReceiptStateError,
        "accepting a receipt that is only Received",
    )
    w.run(handle_inspect_receipt, InspectReceipt, stream_id=rid, notes="counted")
    assert w.status(rid) == ("Inspected", False)
    inspected = w.one(
        "SELECT inspected_by, inspected_on FROM cur_materials_receipt WHERE id = :i", i=rid
    )
    assert inspected["inspected_by"] == ACTOR and inspected["inspected_on"]
    w.refused(
        lambda: w.run(handle_revise_receipt, ReviseReceipt, stream_id=rid, delivery_ref="X"),
        ReceiptStateError,
        "revising an Inspected receipt",
    )
    version = w.one("SELECT version FROM cur_core_record WHERE id = :i", i=rid)["version"]
    # the MTR guard: category flange is required and the slot is empty
    caught = w.refused(
        lambda: w.run(
            handle_accept_receipt, AcceptReceipt, stream_id=rid, expected_version=version
        ),
        MtrRequiredError,
        "accept without the MTR",
    )
    assert str(caught) == MESSAGE_NO_MTR, str(caught)
    w.attach_mtr(rid)
    w.refused(
        lambda: w.run(
            handle_accept_receipt, AcceptReceipt, stream_id=rid, expected_version=version - 1
        ),
        ConcurrencyError,
        "a stale expected_version",
    )
    accepted = w.run(handle_accept_receipt, AcceptReceipt, stream_id=rid, expected_version=version)
    types = [e.event_type for e in accepted.events]
    assert types.count("StockLot.Defined") == 2 and types.count("StockLot.Moved") == 2, types
    assert types[-2:] == ["Receipt.Accepted", "Workflow.Transitioned"], types
    assert w.status(rid) == ("Accepted", False)
    lots = [w.lot(rid, 1), w.lot(rid, 2)]
    assert lots[0] != lots[1] and [w.lot_key(x) for x in lots] == [f"{made.key}@1", f"{made.key}@2"]
    assert [w.balance(x, "LA") for x in lots] == [(D(12), D(0), D(12)), (D(8), D(0), D(8))]
    assert dec(
        w.one("SELECT qty_received FROM cur_materials_po_line WHERE id = :i", i=po.stream_id)[
            "qty_received"
        ]
    ) == D(20)
    derived = [
        r
        for lot in lots
        for r in w.rows(
            "SELECT relation FROM cur_links WHERE from_id = :f AND to_id = :t", f=lot, t=rid
        )
    ]
    assert [r["relation"] for r in derived] == ["derived_from", "derived_from"], derived
    moved = w.rows("SELECT payload FROM events WHERE event_type = 'StockLot.Moved'")
    assert moved and all(
        '"feed_policy": "none"' in m["payload"] or '"feed_policy":"none"' in m["payload"]
        for m in moved
    )
    # after a decision: no void, no reject, no new inspect
    for handler, command, fields in [
        (handle_void_receipt, VoidReceipt, {"reason": "booked twice"}),
        (handle_reject_receipt, RejectReceipt, {"reason": "late"}),
        (handle_inspect_receipt, InspectReceipt, {}),
    ]:
        w.refused(
            lambda h=handler, c=command, f=fields: w.run(h, c, stream_id=rid, **f),
            ReceiptStateError,
            f"{command.__name__} of an accepted receipt",
        )
    # the upload guard: an accepted receipt takes certificate and photo only
    with open_uow(w.target, readonly=True) as uow:
        receipt_upload_guard(uow.conn(), rid, "certificate")
        expect_refused(
            lambda: receipt_upload_guard(uow.conn(), rid, "mtr"),
            Exception,
            "an MTR added to an accepted receipt",
        )
    # reject and void; numbers stay gap-free across the refused creates above
    second = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-03",
        location_code="LA",
        lines=[{"item_code": flange, "qty": "1", "condition": "damaged"}],
    )
    third = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-03",
        location_code="LB",
        lines=[{"item_code": flange, "qty": "1"}],
    )
    # a library item the project has not adopted is adopted by the receipt (written by the module)
    fresh = w.code("NEW")
    w.run(
        handle_define_item,
        DefineItem,
        scope=COMPANY,
        code=fresh,
        title="New",
        category="other",
        base_uom="m",
    )
    assert not w.rows(
        "SELECT 1 FROM cur_core_record WHERE scope = :s AND key = :k", s=w.project, k=fresh
    )
    fourth = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-04",
        location_code="LA",
        lines=[{"item_code": fresh, "qty": "2.500", "uom": "m"}],
    )
    adopted = w.one(
        "SELECT uom FROM cur_materials_project_item p JOIN cur_core_record r ON r.id = p.id "
        "WHERE r.key = :k",
        k=fresh,
    )
    assert adopted["uom"] == "m"
    w.refused(
        lambda: w.run(
            handle_create_receipt,
            CreateReceipt,
            received_on="2026-11-04",
            location_code="LA",
            lines=[{"item_code": fresh, "qty": "1", "uom": "EA"}],
        ),
        Exception,
        "a unit other than the item's",
    )
    keys = [
        r["key"]
        for r in w.rows(
            "SELECT key FROM cur_core_record WHERE type = 'materials.Receipt' ORDER BY key"
        )
    ]
    assert keys == [f"{w.number}-RCPT-000{n}" for n in (1, 2, 3, 4)], keys
    w.run(handle_reject_receipt, RejectReceipt, stream_id=second.stream_id, reason="wrong heat")
    assert w.status(second.stream_id) == ("Rejected", False)
    assert (
        w.one(
            "SELECT rejection_reason FROM cur_materials_receipt WHERE id = :i", i=second.stream_id
        )["rejection_reason"]
        == "wrong heat"
    )
    assert not w.rows("SELECT 1 FROM cur_materials_lot WHERE receipt_id = :r", r=second.stream_id)
    w.refused(
        lambda: w.run(handle_void_receipt, VoidReceipt, stream_id=second.stream_id, reason="x"),
        ReceiptStateError,
        "voiding a rejected receipt",
    )
    w.run(handle_void_receipt, VoidReceipt, stream_id=third.stream_id, reason="booked in error")
    state, voided = w.status(third.stream_id)
    assert (state, voided) == ("Void", True)
    assert w.rows(
        "SELECT 1 FROM events WHERE stream_id = :s AND event_type = 'Record.Voided'",
        s=third.stream_id,
    )
    w.refused(
        lambda: w.run(handle_inspect_receipt, InspectReceipt, stream_id=third.stream_id),
        ReceiptStateError,
        "inspecting a void receipt",
    )
    # a read: the receipt list and one receipt
    with open_uow(w.target, readonly=True) as uow:
        listed = views.receipts(uow.conn(), w.project, viewer=confidentiality.Viewer(level=1))
        assert [r.number for r in listed] == keys
        assert [r.state for r in listed] == ["Accepted", "Rejected", "Void", "Received"]
        assert listed[0].mtr == "present" and listed[1].mtr == "missing" and listed[1].mtr_required
        assert [r.number for r in views.receipts(uow.conn(), w.project, open_only=True)] == [
            fourth.key
        ]
        missing = views.receipts(uow.conn(), w.project, missing_mtr=True)
        assert [r.number for r in missing] == [r.number for r in listed if r.mtr == "missing"]
        assert [
            r.number for r in views.receipts(uow.conn(), w.project, missing_mtr=True, limit=1)
        ] == [r.number for r in listed if r.mtr == "missing"][:1]
        detail = views.receipt_detail(uow.conn(), w.project, keys[0])
        assert [x.lot for x in detail.line_rows] == [w.lot_key(x) for x in lots]
        assert [f.slot for f in detail.files] == ["mtr"] and detail.decided_by == ACTOR
        expect_refused(
            lambda: views.receipt_detail(uow.conn(), w.project, "NOPE"),
            ReceiptNotFoundError,
            "an unknown receipt number",
        )


def check_issue_and_transfer(w: World) -> None:
    s = Stocked(w)
    k1 = s.key1
    # consumable without a cost code, with a cost code that is not one, over-issue
    w.refused(
        lambda: w.run(
            handle_issue_stock,
            IssueStock,
            movements=[mv(s.glove_key, "1", uom="kg", from_location="LB")],
        ),
        MovementRuleError,
        "a consumable issued without a cost code",
    )
    w.refused(
        lambda: w.run(
            handle_issue_stock,
            IssueStock,
            movements=[mv(s.glove_key, "1", uom="kg", from_location="LB", cost_code_id=new_ulid())],
        ),
        Exception,
        "an issue against a cost code that does not exist",
    )
    w.run(
        handle_issue_stock,
        IssueStock,
        movements=[
            mv(
                s.glove_key,
                "4.000",
                uom="kg",
                from_location="LB",
                cost_code_id=s.cost_code,
                person="R. Singh",
            )
        ],
    )
    assert w.balance(s.glove_lot, "LB") == (D(6), D(0), D(6))
    row = w.one("SELECT * FROM cur_materials_movement WHERE kind = 'issue'")
    assert row["cost_code_id"] == s.cost_code and row["person"] == "R. Singh"
    w.refused(
        lambda: w.run(
            handle_issue_stock, IssueStock, movements=[mv(k1, "12.001", from_location="LA")]
        ),
        InsufficientStockError,
        "an over-issue",
    )
    w.refused(
        lambda: w.run(
            handle_issue_stock,
            IssueStock,
            movements=[mv(k1, "1", from_location="LA", to_location="LB")],
        ),
        MovementRuleError,
        "an issue with a to",
    )
    w.refused(
        lambda: w.run(
            handle_issue_stock, IssueStock, movements=[mv(k1, "1", uom="kg", from_location="LA")]
        ),
        MovementRuleError,
        "a unit other than the lot's",
    )
    w.refused(
        lambda: w.run(handle_issue_stock, IssueStock, movements=[mv(k1, "1")]),
        MovementRuleError,
        "an issue without a from",
    )
    # a reservation is consumed first
    w.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(k1, "4.000", from_location="LA", mto_line_id=s.line)],
    )
    assert w.balance(s.lot1, "LA") == (D(12), D(4), D(8))
    w.run(
        handle_issue_stock,
        IssueStock,
        movements=[mv(k1, "3.000", from_location="LA", mto_line_id=s.line)],
    )
    assert w.balance(s.lot1, "LA") == (D(9), D(1), D(8)), w.balance(s.lot1, "LA")
    line = w.one(
        "SELECT reserved_qty, issued_qty FROM cur_materials_mto_line WHERE id = :i", i=s.line
    )
    assert (dec(line["reserved_qty"]), dec(line["issued_qty"])) == (D(1), D(3))
    w.refused(
        lambda: w.run(
            handle_issue_stock, IssueStock, movements=[mv(k1, "8.001", from_location="LA")]
        ),
        InsufficientStockError,
        "issuing what is reserved for a line without the line",
    )
    w.refused(
        lambda: w.run(
            handle_issue_stock,
            IssueStock,
            movements=[mv(k1, "9.001", from_location="LA", mto_line_id=s.line)],
        ),
        InsufficientStockError,
        "issuing more than available plus the line's reservation",
    )
    # transfer
    w.refused(
        lambda: w.run(
            handle_transfer_stock,
            TransferStock,
            movements=[mv(k1, "1", from_location="LA", to_location="LA")],
        ),
        MovementRuleError,
        "from = to",
    )
    w.run(
        handle_define_location,
        DefineLocation,
        code="LC",
        title="LC",
        kind="laydown",
        parent_code="WH",
    )
    w.run(handle_retire_location, RetireLocation, code="LC", reason="closed")
    w.refused(
        lambda: w.run(
            handle_transfer_stock,
            TransferStock,
            movements=[mv(k1, "1", from_location="LA", to_location="LC")],
        ),
        MovementRuleError,
        "a retired location",
    )
    w.refused(
        lambda: w.run(
            handle_transfer_stock,
            TransferStock,
            movements=[mv(k1, "1", from_location="LA", to_location="NOWHERE")],
        ),
        Exception,
        "a location not in the project",
    )
    w.refused(
        lambda: w.run(
            handle_transfer_stock,
            TransferStock,
            movements=[mv(k1, "8.001", from_location="LA", to_location="LB")],
        ),
        InsufficientStockError,
        "a transfer of more than is available",
    )
    w.run(
        handle_transfer_stock,
        TransferStock,
        movements=[mv(k1, "2.000", from_location="LA", to_location="LB")],
    )
    assert w.balance(s.lot1, "LA") == (D(7), D(1), D(6))
    assert w.balance(s.lot1, "LB") == (D(2), D(0), D(2))
    # return: at most the net issued (3 so far)
    w.refused(
        lambda: w.run(
            handle_return_stock, ReturnStock, movements=[mv(k1, "3.001", to_location="LB")]
        ),
        InsufficientStockError,
        "a return above issued_net",
    )
    w.run(handle_return_stock, ReturnStock, movements=[mv(k1, "1.000", to_location="LB")])
    assert dec(
        w.one("SELECT issued_net FROM cur_materials_lot WHERE id = :i", i=s.lot1)["issued_net"]
    ) == D(2)
    assert w.balance(s.lot1, "LB") == (D(3), D(0), D(3))
    w.refused(
        lambda: w.run(
            handle_return_stock, ReturnStock, movements=[mv(k1, "2.001", to_location="LB")]
        ),
        InsufficientStockError,
        "a return above what is left net",
    )


def check_adjust_scrap_reserve(w: World) -> None:
    s = Stocked(w)
    k1, k2 = s.key1, s.key2
    # the word: a plain user holds materials.move and materials.reserve but not materials.adjust
    adjust = AdjustStock(
        actor=PLAIN,
        source=SOURCE,
        scope=w.project,
        movements=[mv(k1, "1", direction="out", from_location="LA", reason="lost")],
    )
    scrap = ScrapStock(
        actor=PLAIN,
        source=SOURCE,
        scope=w.project,
        movements=[mv(k1, "1", from_location="LA", reason="damaged")],
    )
    issue = IssueStock(
        actor=PLAIN, source=SOURCE, scope=w.project, movements=[mv(k1, "1", from_location="LA")]
    )
    with open_uow(w.target, readonly=True) as uow:
        for command in (adjust, scrap):
            caught = expect_refused(
                lambda c=command: require_command_access(uow.conn(), c, holder=USER),
                ForbiddenError,
                f"{type(command).__name__} by a plain user",
            )
            assert "materials.adjust" in str(caught) or "controller" in str(caught), str(caught)
            require_command_access(uow.conn(), command, holder=BOSS)
        require_command_access(uow.conn(), issue, holder=USER)
        void = VoidReceipt(
            actor=PLAIN, source=SOURCE, scope=w.project, stream_id=s.receipt, reason="x"
        )
        expect_refused(
            lambda: require_command_access(uow.conn(), void, holder=USER),
            ForbiddenError,
            "a user voiding a receipt",
        )
        accept = AcceptReceipt(
            actor=PLAIN, source=SOURCE, scope=w.project, stream_id=s.receipt, expected_version=1
        )
        require_command_access(uow.conn(), accept, holder=USER)  # any user accepts (answer 15)
    # adjust and scrap need a reason
    w.refused(
        lambda: w.run(
            handle_adjust_stock,
            AdjustStock,
            actor=SUPER,
            movements=[mv(k1, "1", direction="out", from_location="LA")],
        ),
        MovementRuleError,
        "an adjust without a reason",
    )
    w.refused(
        lambda: w.run(
            handle_scrap_stock,
            ScrapStock,
            actor=SUPER,
            movements=[mv(k1, "1", from_location="LA", reason="  ")],
        ),
        MovementRuleError,
        "a scrap with a blank reason",
    )
    w.refused(
        lambda: w.run(
            handle_adjust_stock,
            AdjustStock,
            actor=SUPER,
            movements=[mv(k1, "1", from_location="LA", reason="lost")],
        ),
        MovementRuleError,
        "an adjust without a direction",
    )
    # no balance goes negative, adjust included
    w.refused(
        lambda: w.run(
            handle_adjust_stock,
            AdjustStock,
            actor=SUPER,
            movements=[mv(k1, "12.001", direction="out", from_location="LA", reason="count")],
        ),
        InsufficientStockError,
        "an adjust out below zero",
    )
    w.run(
        handle_adjust_stock,
        AdjustStock,
        actor=SUPER,
        movements=[mv(k1, "2.000", direction="out", from_location="LA", reason="count_correction")],
    )
    assert w.balance(s.lot1, "LA") == (D(10), D(0), D(10))
    w.run(
        handle_adjust_stock,
        AdjustStock,
        actor=SUPER,
        movements=[mv(k1, "1.500", direction="in", to_location="LB", reason="found")],
    )
    assert w.balance(s.lot1, "LB") == (D("1.5"), D(0), D("1.5"))
    w.refused(
        lambda: w.run(
            handle_scrap_stock,
            ScrapStock,
            actor=SUPER,
            movements=[mv(k2, "8.001", from_location="LA", reason="damaged")],
        ),
        InsufficientStockError,
        "a scrap above available",
    )
    w.run(
        handle_scrap_stock,
        ScrapStock,
        actor=SUPER,
        movements=[mv(k2, "8.000", from_location="LA", reason="damaged")],
    )
    assert w.balance(s.lot2, "LA") is None, "a balance at zero has no row"
    # reserve: over available, over the line's quantity, the wrong item, an unknown line
    w.refused(
        lambda: w.run(
            handle_reserve_stock,
            ReserveStock,
            movements=[mv(k1, "10.001", from_location="LA", mto_line_id=s.line_other)],
        ),
        Exception,
        "a reserve over available",
    )
    w.refused(
        lambda: w.run(
            handle_reserve_stock,
            ReserveStock,
            movements=[mv(k1, "6.001", from_location="LA", mto_line_id=s.line)],
        ),
        InsufficientStockError,
        "a reserve over the line's quantity",
    )
    w.refused(
        lambda: w.run(
            handle_reserve_stock,
            ReserveStock,
            movements=[mv(k1, "1", from_location="LA", mto_line_id=s.line_other)],
        ),
        MovementRuleError,
        "a lot of another item",
    )
    w.refused(
        lambda: w.run(
            handle_reserve_stock,
            ReserveStock,
            movements=[mv(k1, "1", from_location="LA", mto_line_id=new_ulid())],
        ),
        Exception,
        "an unknown line",
    )
    w.refused(
        lambda: w.run(
            handle_reserve_stock, ReserveStock, movements=[mv(k1, "1", from_location="LA")]
        ),
        MovementRuleError,
        "a reserve without a line",
    )
    done = w.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[
            mv(k1, "4.000", from_location="LA", mto_line_id=s.line),
            mv(k1, "2.000", from_location="LA", mto_line_id=s.line),
        ],
    )
    assert len(done.events) == 2 and w.balance(s.lot1, "LA") == (D(10), D(6), D(4))
    row = w.one(
        "SELECT iwp_id, mto_line_id FROM cur_materials_movement WHERE kind = 'reserve' "
        "ORDER BY seq LIMIT 1"
    )
    assert row["iwp_id"] == s.iwp and row["mto_line_id"] == s.line  # copied from the line
    w.refused(
        lambda: w.run(
            handle_reserve_stock,
            ReserveStock,
            movements=[mv(k1, "0.001", from_location="LA", mto_line_id=s.line)],
        ),
        InsufficientStockError,
        "reserving once the line is fully reserved",
    )
    # a reserved quantity is not available to transfer, scrap or adjust
    w.refused(
        lambda: w.run(
            handle_transfer_stock,
            TransferStock,
            movements=[mv(k1, "4.001", from_location="LA", to_location="LB")],
        ),
        InsufficientStockError,
        "transferring reserved stock",
    )
    # unreserve
    w.refused(
        lambda: w.run(
            handle_unreserve_stock,
            UnreserveStock,
            movements=[mv(k1, "6.001", from_location="LA", mto_line_id=s.line)],
        ),
        InsufficientStockError,
        "an unreserve over reserved",
    )
    w.run(
        handle_unreserve_stock,
        UnreserveStock,
        movements=[mv(k1, "6.000", from_location="LA", mto_line_id=s.line)],
    )
    assert w.balance(s.lot1, "LA") == (D(10), D(0), D(10))
    assert not w.rows("SELECT 1 FROM cur_materials_reservation"), "a reservation at zero is gone"


def check_batches_and_quantities(w: World) -> None:
    s = Stocked(w)
    k1 = s.key1
    # a batch of 201 is refused by the command and by the public surface
    batch = [mv(k1, "0.001", from_location="LA") for _ in range(201)]
    expect_refused(
        lambda: IssueStock(actor=ACTOR, source=SOURCE, scope=w.project, movements=batch),
        ValidationError,
        "201 movements in a command",
    )
    posted = [
        PostedMovement(
            kind="issue", scope=w.project, lot_key=k1, qty="0.001", uom="EA", from_location="LA"
        )
        for _ in range(201)
    ]

    def post(items: list[PostedMovement]) -> list[str]:
        with open_uow(w.target) as uow:
            return post_movements(uow, items, actor=ACTOR, source=SOURCE, by_module=True)

    w.refused(lambda: post(posted), MovementRuleError, "201 movements through post_movements")
    w.refused(lambda: post([]), MovementRuleError, "an empty batch")
    mixed = [
        posted[0],
        PostedMovement(
            kind="transfer",
            scope=w.project,
            lot_key=k1,
            qty="1",
            uom="EA",
            from_location="LA",
            to_location="LB",
        ),
    ]
    w.refused(lambda: post(mixed), MovementRuleError, "a batch of two kinds")
    ids = post(posted[:200])
    assert len(ids) == 200 and w.balance(s.lot1, "LA") == (D("11.8"), D(0), D("11.8"))
    one = post(
        [
            PostedMovement(
                kind="issue",
                scope=w.project,
                lot_key=k1,
                qty="1",
                uom="EA",
                from_location="LA",
                requisition_id="REQ-1",
            )
        ]
    )
    assert (
        w.one("SELECT requisition_id FROM cur_materials_movement ORDER BY seq DESC LIMIT 1")[
            "requisition_id"
        ]
        == "REQ-1"
        and len(one) == 1
    )
    # a batch with one bad row writes nothing, and the second row sees the first
    before = w.balance(s.lot1, "LA")
    w.refused(
        lambda: w.run(
            handle_issue_stock,
            IssueStock,
            movements=[
                mv(k1, "1", from_location="LA"),
                mv(k1, "1", from_location="LA", to_location="LB"),
            ],
        ),
        MovementRuleError,
        "a batch with a bad second row",
    )
    w.refused(
        lambda: w.run(
            handle_issue_stock,
            IssueStock,
            movements=[mv(k1, "6", from_location="LA"), mv(k1, "6", from_location="LA")],
        ),
        InsufficientStockError,
        "two issues of 6 from 10.8",
    )
    assert w.balance(s.lot1, "LA") == before
    # quantities: the fixed message for each bad shape, nothing written
    messages = set()
    for bad in ("１２", "-1", "0", "1.2345", "1000000000.001", "1e3", " 1", "1,5"):
        caught = w.refused(
            lambda bad=bad: w.run(
                handle_issue_stock, IssueStock, movements=[mv(k1, bad, from_location="LA")]
            ),
            InvalidQuantityError,
            f"quantity {bad!r}",
        )
        assert str(caught).startswith("movement 1 qty must be "), str(caught)
        assert "\uff11" not in str(caught) and "1000000000.001" not in str(caught)
        messages.add(str(caught).split(" must ")[0])
    assert messages == {"movement 1 qty"}, messages
    big = w.refused(
        lambda: w.run(
            handle_issue_stock, IssueStock, movements=[mv(k1, "1000000000.001", from_location="LA")]
        ),
        InvalidQuantityError,
        "over the bound",
    )
    assert "at most" in str(big)
    # Decimal exactness: three moves of 0.100 are 0.300
    pennies = w.deliver([{"item_code": w.code("OTH"), "qty": "0.100"}], location="LA")
    lot = w.lot(pennies.stream_id)
    w.run(
        handle_adjust_stock,
        AdjustStock,
        actor=SUPER,
        movements=[mv(w.lot_key(lot), "0.200", direction="in", to_location="LA", reason="found")],
    )
    assert w.balance(lot, "LA") == (D("0.300"), D(0), D("0.300"))
    for _ in range(3):
        w.run(
            handle_issue_stock,
            IssueStock,
            movements=[mv(w.lot_key(lot), "0.100", from_location="LA")],
        )
    assert w.balance(lot, "LA") is None


def snapshot(w: World) -> dict[str, list[dict[str, Any]]]:
    order = {
        "cur_materials_movement": "seq",
        "cur_materials_stock": "lot_id, location_id",
        "cur_materials_reservation": "lot_id, location_id, mto_line_id",
        "cur_materials_receipt_line": "row_id",
    }
    found = {t: w.rows(f"SELECT * FROM {t} ORDER BY {order.get(t, 'id')}") for t in TABLES}
    found["cur_core_record"] = w.rows("SELECT * FROM cur_core_record ORDER BY id")
    return found


def check_rebuild(w: World) -> None:
    s = Stocked(w)
    w.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(s.key1, "4.000", from_location="LA", mto_line_id=s.line)],
    )
    w.run(
        handle_issue_stock,
        IssueStock,
        movements=[
            mv(s.key1, "3.000", from_location="LA", mto_line_id=s.line),
            mv(s.key2, "1.250", from_location="LA"),
        ],
    )
    w.run(
        handle_transfer_stock,
        TransferStock,
        movements=[mv(s.key2, "2.000", from_location="LA", to_location="LB")],
    )
    w.run(handle_return_stock, ReturnStock, movements=[mv(s.key1, "1.000", to_location="LB")])
    w.run(
        handle_adjust_stock,
        AdjustStock,
        actor=SUPER,
        movements=[mv(s.key2, "0.250", direction="out", from_location="LB", reason="lost")],
    )
    w.run(
        handle_scrap_stock,
        ScrapStock,
        actor=SUPER,
        movements=[mv(s.key1, "1.000", from_location="LB", reason="damaged")],
    )
    before = snapshot(w)
    for table in ("cur_materials_stock", "cur_materials_reservation", "cur_materials_movement"):
        assert before[table], table
    rebuild_projections(w.target)
    after = snapshot(w)
    for table, rows in before.items():
        assert after[table] == rows, f"{table} differs after a rebuild"


def check_concurrent_issues(w: World) -> None:
    w.tree()
    item = w.code("CON")
    w.item(item)
    made = w.deliver([{"item_code": item, "qty": "5.000"}], location="LA")
    key = w.lot_key(w.lot(made.stream_id))
    gate = threading.Barrier(2)
    outcomes: list[str] = []

    def issue(who: str) -> None:
        command = IssueStock(
            actor=who,
            source=SOURCE,
            scope=w.project,
            movements=[mv(key, "5.000", from_location="LA")],
        )
        try:
            gate.wait(timeout=10)
            with open_uow(w.target) as uow:
                handle_issue_stock(uow, command)
            outcomes.append("ok")
        except InsufficientStockError:
            outcomes.append("refused")
        except Exception as error:  # a busy lock is not an answer either way
            outcomes.append(f"error {type(error).__name__}: {error}")

    threads = [threading.Thread(target=issue, args=(f"user:p{n}",)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(outcomes) == ["ok", "refused"], outcomes
    assert w.balance(w.lot(made.stream_id), "LA") is None
    issues = w.rows("SELECT 1 FROM cur_materials_movement WHERE kind = 'issue'")
    assert len(issues) == 1


def check_offers(w: World) -> None:
    s = Stocked(w)

    def offered(record_id: str, who: Holder, actor: str | None = None) -> list[str]:
        with open_uow(w.target, readonly=True) as uow:
            got = allowed_actions(
                uow, record_id, actor=actor or who.actor, holds=lambda level: False, holder=who
            )
        return [a.command for a in got.actions]

    # a receipt walks Received -> Inspected -> Accepted
    made = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-02",
        location_code="LA",
        lines=[{"item_code": w.code("FLG"), "qty": "1", "heat_no": "H-1"}],
    )
    rid = made.stream_id
    assert offered(rid, USER) == ["ReviseReceipt", "InspectReceipt", "RejectReceipt"]
    assert offered(rid, BOSS) == ["ReviseReceipt", "InspectReceipt", "RejectReceipt", "VoidReceipt"]
    w.run(handle_inspect_receipt, InspectReceipt, stream_id=rid)
    # flange needs an MTR: Accept is offered only once one is attached
    assert offered(rid, USER) == ["RejectReceipt"]
    assert offered(rid, BOSS) == ["RejectReceipt", "VoidReceipt"]
    w.attach_mtr(rid)
    assert offered(rid, USER) == ["AcceptReceipt", "RejectReceipt"]
    version = w.one("SELECT version FROM cur_core_record WHERE id = :i", i=rid)["version"]
    w.run(handle_accept_receipt, AcceptReceipt, stream_id=rid, expected_version=version)
    assert offered(rid, USER) == [] and offered(rid, BOSS) == []
    # an agent is offered nothing, whatever it holds
    assert offered(s.receipt, AGENT) == [] and offered(s.lot1, AGENT) == []
    assert offered(s.lot1, BOSS, actor="agent:helper") == []
    # a lot: stock, issued_net and a reservation drive the offers
    assert offered(s.lot1, USER) == ["IssueStock", "TransferStock", "ReserveStock"]
    assert offered(s.lot1, BOSS) == [
        "IssueStock",
        "TransferStock",
        "ReserveStock",
        "AdjustStock",
        "ScrapStock",
    ]
    w.run(handle_issue_stock, IssueStock, movements=[mv(s.key1, "1", from_location="LA")])
    assert "ReturnStock" in offered(s.lot1, USER)
    w.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(s.key1, "2", from_location="LA", mto_line_id=s.line)],
    )
    assert offered(s.lot1, USER) == [
        "IssueStock",
        "TransferStock",
        "ReserveStock",
        "ReturnStock",
        "UnreserveStock",
    ]
    w.run(
        handle_scrap_stock,
        ScrapStock,
        actor=SUPER,
        movements=[mv(s.key2, "8", from_location="LA", reason="damaged")],
    )
    assert offered(s.lot2, BOSS) == []  # nothing on hand, nothing issued
    # a take-off line: short -> reserve from a lot
    assert offered(s.line, USER) == ["ReserveStock"]
    w.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(s.key1, "4", from_location="LA", mto_line_id=s.line)],
    )
    assert offered(s.line, USER) == []  # 6 of 6 held
    # the table's words are the commands' words
    assert {r.command: r.word for r in rule_rows()}["AdjustStock"] == "materials.adjust"


def check_proposal(w: World) -> None:
    s = Stocked(w)
    command = ReserveStock(
        actor="agent:helper",
        source="mcp:helper",
        scope=w.project,
        movements=[mv(s.key1, "2.000", from_location="LA", mto_line_id=s.line)],
    )
    before = w.events()
    moved = w.rows("SELECT 1 FROM cur_materials_movement WHERE kind = 'reserve'")
    with open_uow(w.target) as uow:
        view = proposals.propose(
            uow,
            tool="propose_reservation",
            agent="agent:helper",
            command=command,
            summary="reserve 2 flanges for the line",
        )
    assert view.status == "pending" and view.command_type == "ReserveStock"
    assert w.rows("SELECT 1 FROM cur_materials_movement WHERE kind = 'reserve'") == moved
    assert w.balance(s.lot1, "LA") == (D(12), D(0), D(12))
    new = w.rows("SELECT event_type FROM events WHERE seq > (SELECT MAX(seq) - 1 FROM events)")
    assert [e["event_type"] for e in new] == ["Proposal.Created"] and w.events() == before + 1
    assert proposals.access_of("ReserveStock") == "user"
    assert proposals.proposable_tools()["propose_reservation"] == "ReserveStock"
    # a person who holds materials.reserve accepts: now the reservation exists, made by them
    with open_uow(w.target) as uow:
        proposals.accept_proposal(
            uow,
            proposal_id=view.proposal_id,
            by=PLAIN,
            holds=lambda level: level == "user",
            holder=USER,
        )
    assert w.balance(s.lot1, "LA") == (D(12), D(2), D(10))
    made = w.one("SELECT actor FROM cur_materials_movement WHERE kind = 'reserve'")
    assert made["actor"] == PLAIN


def check_hidden(w: World) -> None:
    s = Stocked(w)
    hidden_lot = s.lot1
    with open_uow(w.target) as uow:
        uow.conn().execute(text("CREATE TABLE x_class (id TEXT PRIMARY KEY, cls TEXT)"))
        for record_id, cls in [
            (s.lot1, "restricted"),
            (s.lot2, "internal"),
            (s.receipt, "restricted"),
            (s.line, "restricted"),
        ]:
            uow.conn().execute(
                text("INSERT INTO x_class VALUES (:i, :c)"), {"i": record_id, "c": cls}
            )
    real = {m.name: m for m in load_modules()}
    import dataclasses

    source = ConfidentialSource(
        record_types=frozenset({"materials.StockLot", "materials.Receipt", "materials.MTOLine"}),
        table="x_class",
        id_column="id",
        class_column="cls",
    )
    changed = [
        dataclasses.replace(m, confidential=(source,)) if m.name == "materials" else m
        for m in real.values()
    ]
    with use_modules(changed):
        low = confidentiality.LOWEST
        with open_uow(w.target, readonly=True) as uow:
            conn = uow.conn()
            assert s.key1 not in {r.lot for r in views.stock(conn, w.project, viewer=low)}
            assert s.key1 in {
                r.lot for r in views.stock(conn, w.project, viewer=confidentiality.Viewer(level=1))
            }
            assert s.receipt not in {r.id for r in views.receipts(conn, w.project, viewer=low)}
            expect_refused(
                lambda: views.receipt_detail(
                    conn,
                    w.project,
                    w.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.receipt)["key"],
                    viewer=low,
                ),
                ReceiptNotFoundError,
                "a hidden receipt's detail",
            )
            assert s.line not in {r.id for r in views.mto_lines(conn, w.project, viewer=low)}
            assert s.line in {
                r.id
                for r in views.mto_lines(conn, w.project, viewer=confidentiality.Viewer(level=1))
            }
            assert not views.reservations_for_iwp(conn, s.iwp, viewer=low)
        # a command on a hidden lot answers as one that never existed, and writes nothing
        with confidentiality.use_viewer(low):
            w.refused(
                lambda: w.run(
                    handle_issue_stock, IssueStock, movements=[mv(s.key1, "1", from_location="LA")]
                ),
                LotNotFoundError,
                "an issue from a hidden lot",
            )
            w.refused(
                lambda: w.run(handle_inspect_receipt, InspectReceipt, stream_id=s.receipt),
                ReceiptNotFoundError,
                "inspecting a hidden receipt",
            )
    assert hidden_lot


def check_views(w: World) -> None:
    s = Stocked(w)
    w.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(s.key1, "4.000", from_location="LA", mto_line_id=s.line)],
    )
    w.run(
        handle_issue_stock,
        IssueStock,
        movements=[mv(s.key1, "1.000", from_location="LA", mto_line_id=s.line)],
    )
    with open_uow(w.target, readonly=True) as uow:
        conn = uow.conn()
        viewer = confidentiality.Viewer(level=1)
        lines = views.mto_lines(conn, w.project, viewer=viewer)
        assert [(x.required, x.reserved, x.issued, x.short) for x in lines] == [
            (D(6), D(3), D(1), D(2)),
            (D(2), D(0), D(0), D(2)),
        ]
        assert [x.id for x in views.mto_lines(conn, w.project, short_only=True, viewer=viewer)] == [
            s.line,
            s.line_other,
        ]
        assert [x.work_package for x in lines] == ["P1-IWP-0001", None]
        assert [
            x.id
            for x in views.mto_lines(conn, w.project, work_package="P1-IWP-0001", viewer=viewer)
        ] == [s.line]
        assert [x.id for x in views.mto_lines_for(conn, s.iwp, viewer=viewer)] == [s.line]
        reserved = views.reservations_for_iwp(conn, s.iwp, viewer=viewer)
        assert [(r.lot, r.location, r.qty) for r in reserved] == [(s.key1, "LA", D(3))]
        assert views.reservations_for_iwp(conn, new_ulid(), viewer=viewer) == []


# --- the seed ledger -----------------------------------------------------------------------------
