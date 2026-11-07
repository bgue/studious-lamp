"""Helpers and checks of the S2 module tests (items, locations, PO lines, replay, targets)."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import (
    DbTarget,
    as_target,
    create_schema,
    open_uow,
    rebuild_projections,
)
from tl_core.confidentiality import LOWEST, Viewer
from tl_core.ledger import NewEvent
from tl_core.modules import ConfidentialSource, load_modules, use_modules
from tl_core.services.commands import CommandResult
from tl_core.services.errors import DuplicateKeyError
from tl_core.util import new_ulid
from tl_mod_legacy.model import Grid
from tl_mod_legacy.targets import installed_targets
from tl_mod_materials import views
from tl_mod_materials.commands import MATERIALS_COMMANDS
from tl_mod_materials.errors import (
    InvalidValueError,
    ItemRetiredError,
    LocationTreeError,
    LotNotFoundError,
)
from tl_mod_materials.handlers.items import (
    AdoptItem,
    DefineItem,
    RetireItem,
    ReviseItem,
    handle_adopt_item,
    handle_define_item,
    handle_retire_item,
    handle_revise_item,
)
from tl_mod_materials.handlers.locations import (
    DefineLocation,
    RetireLocation,
    handle_define_location,
    handle_retire_location,
)
from tl_mod_materials.handlers.po_lines import (
    RecordPoLine,
    UpdatePoLine,
    handle_record_po_line,
    handle_update_po_line,
)

ACTOR = "user:accept"
SOURCE = "accept"
COMPANY = "company"
MATERIAL_TABLES = [
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
    "DefineItem": "materials.library.edit",
    "ReviseItem": "materials.library.edit",
    "RetireItem": "materials.library.edit",
    "AdoptItem": "materials.item.adopt",
    "DefineLocation": "materials.location.configure",
    "ReviseLocation": "materials.location.configure",
    "RetireLocation": "materials.location.configure",
    "RecordPoLine": "materials.po.edit",
    "UpdatePoLine": "materials.po.edit",
}


class World:
    """One empty ledger and the calls a command or a test step makes against it."""

    def __init__(self, target: DbTarget) -> None:
        self.target = target
        self.tag = uuid.uuid4().hex[:8].upper()
        self.project = "project:A" + self.tag

    def code(self, prefix: str) -> str:
        """A code no earlier run used (the library is the company's, one per ledger)."""
        return f"{prefix}-{self.tag}"

    def run(self, handler: Callable[[Any, Any], CommandResult], command_type: Any, **fields: Any):
        scope = fields.pop("scope", self.project)
        command = command_type(actor=ACTOR, source=SOURCE, scope=scope, **fields)
        with open_uow(self.target) as uow:
            return handler(uow, command)

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.target, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def one(self, sql: str, **params: Any) -> dict[str, Any]:
        found = self.rows(sql, **params)
        assert len(found) == 1, (sql, found)
        return found[0]

    def create(
        self,
        record_type: str,
        key: str,
        title: str,
        events: list[NewEvent],
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
                events=[created, *events],
                actor=ACTOR,
                source=SOURCE,
                correlation_id=new_ulid(),
            )
        return stream

    def add(self, stream: str, record_type: str, events: list[NewEvent]) -> None:
        with open_uow(self.target) as uow:
            version = (
                uow.conn()
                .execute(text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": stream})
                .scalar_one()
            )
            uow.append(
                stream_id=stream,
                stream_type=record_type,
                scope=self.project,
                expected_version=int(version),
                events=events,
                actor=ACTOR,
                source=SOURCE,
                correlation_id=new_ulid(),
            )

    def id_of(self, key: str, scope: str | None = None) -> str:
        return str(
            self.one(
                "SELECT id FROM cur_core_record WHERE scope = :s AND key = :k",
                s=scope or self.project,
                k=key,
            )["id"]
        )

    def move(self, lot: str, **payload: Any) -> None:
        body = {"feed_policy": "none", "uom": "EA", **payload}
        self.add(lot, "materials.StockLot", [NewEvent(event_type="StockLot.Moved", payload=body)])


def fresh_sqlite(tmp: Path) -> World:
    target = as_target(tmp / f"{uuid.uuid4().hex}.db")
    create_schema(target)
    return World(target)


def expect_refused(call: Callable[[], object], error: type[Exception], what: str) -> None:
    try:
        call()
    except error:
        return
    raise AssertionError(f"{what}: expected {error.__name__}, nothing was refused")


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


# --- the checks ----------------------------------------------------------------------------------


def check_module(w: World) -> None:
    found = {m.name: m for m in load_modules()}
    spec = found["materials"]
    assert spec.company_roles is True
    assert spec.offline_drafts == {
        "materials.StockLot": frozenset({"IssueStock", "TransferStock", "ReturnStock"})
    }
    assert len(spec.record_types) == 8 and all(
        t.startswith("materials.") for t in spec.record_types
    )
    names = {c.model.__name__: c.access for c in MATERIALS_COMMANDS}
    assert {k: names.get(k) for k in SPEC_WORDS} == SPEC_WORDS, names  # S3 and S4 add more
    for command, word in SPEC_WORDS.items():
        assert spec.command_words[command] == word, command
    assert "materials.ItemMaster" not in spec.generic_commands
    assert "materials.InventoryLocation" not in spec.generic_commands
    for record_type, allowed in spec.generic_commands.items():
        assert not allowed & {"UpdateRecord", "VoidRecord", "TransitionWorkflow"}, record_type


def check_items(w: World) -> None:
    master = w.run(
        handle_define_item,
        DefineItem,
        scope=COMPANY,
        code=w.code("FLG"),
        title="Flange WN 6 in 150#",
        category="flange",
        base_uom="EA",
        size_text="6 in",
        rating_text="150#",
        material_code="CS",
        consumable=False,
    )
    code = master.key
    assert code is not None
    row = w.one("SELECT * FROM cur_materials_item_master WHERE code = :c", c=code)
    assert row["scope"] == COMPANY and row["category"] == "flange" and row["base_uom"] == "EA"
    assert bool(row["consumable"]) is False and bool(row["retired"]) is False
    record = w.one(
        "SELECT scope, type, title FROM cur_core_record WHERE id = :i", i=master.stream_id
    )
    assert (record["scope"], record["type"]) == (COMPANY, "materials.ItemMaster")
    expect_refused(
        lambda: w.run(
            handle_define_item,
            DefineItem,
            scope=COMPANY,
            code=code,
            title="x",
            category="flange",
            base_uom="EA",
        ),  # fmt: skip
        DuplicateKeyError,
        "a second item with the same code",
    )
    expect_refused(
        lambda: w.run(
            handle_define_item,
            DefineItem,
            scope=w.project,
            code=w.code("P"),
            title="x",
            category="flange",
            base_uom="EA",
        ),  # fmt: skip
        Exception,
        "an item defined in a project",
    )
    adopted = w.run(handle_adopt_item, AdoptItem, item_code=code)
    copy = w.one("SELECT * FROM cur_materials_project_item WHERE id = :i", i=adopted.stream_id)
    assert (copy["category"], copy["uom"], bool(copy["consumable"])) == ("flange", "EA", False)
    assert copy["item_master_id"] == master.stream_id
    w.run(handle_revise_item, ReviseItem, scope=COMPANY, code=code, category="fitting",
          consumable=True)  # fmt: skip
    copy = w.one("SELECT * FROM cur_materials_project_item WHERE id = :i", i=adopted.stream_id)
    assert (copy["category"], bool(copy["consumable"])) == ("fitting", True), copy
    row = w.one("SELECT * FROM cur_materials_item_master WHERE code = :c", c=code)
    assert row["category"] == "fitting" and row["rating_text"] == "150#"
    expect_refused(
        lambda: w.run(handle_revise_item, ReviseItem, scope=COMPANY, code=code, base_uom="m"),
        Exception,
        "a unit change after a project adopted the item",
    )
    # a second project follows the revision too
    other = "project:B" + uuid.uuid4().hex[:8].upper()
    w.run(handle_adopt_item, AdoptItem, scope=other, item_code=code)
    w.run(handle_revise_item, ReviseItem, scope=COMPANY, code=code, category="pipe")
    categories = {r["category"] for r in w.rows("SELECT category FROM cur_materials_project_item")}
    assert categories == {"pipe"}, categories
    # a retired item cannot be adopted
    retired = w.code("OLD")
    w.run(handle_define_item, DefineItem, scope=COMPANY, code=retired, title="Old", category="pipe",
          base_uom="m")  # fmt: skip
    w.run(handle_retire_item, RetireItem, scope=COMPANY, code=retired, reason="superseded")
    assert bool(w.one("SELECT retired FROM cur_materials_item_master WHERE code = :c",
                      c=retired)["retired"])  # fmt: skip
    expect_refused(
        lambda: w.run(handle_adopt_item, AdoptItem, item_code=retired),
        ItemRetiredError,
        "adopting a retired item",
    )


def check_locations(w: World) -> None:
    def define(code: str, kind: str, parent: str | None) -> CommandResult:
        return w.run(handle_define_location, DefineLocation, code=code, title=code.title(),
                     kind=kind, parent_code=parent)  # fmt: skip

    define("P1", "project", None)
    expect_refused(lambda: define("P2", "project", None), LocationTreeError, "a second root")
    previous = "P1"
    for depth, code in enumerate(["D1", "D2", "D3", "D4", "D5"], start=1):
        define(code, "warehouse" if depth == 1 else "laydown", previous)
        got = w.one("SELECT depth FROM cur_materials_location WHERE code = :c", c=code)
        assert got["depth"] == depth, (code, got)
        previous = code
    expect_refused(lambda: define("D6", "laydown", "D5"), LocationTreeError, "depth 6")
    assert not w.rows("SELECT 1 FROM cur_materials_location WHERE code = 'D6'")
    expect_refused(
        lambda: define("X1", "laydown", "NOPE"), Exception, "a parent that does not exist"
    )
    # retire: refused with a child, refused with stock 0.001, allowed at zero
    expect_refused(
        lambda: w.run(handle_retire_location, RetireLocation, code="D4", reason="r"),
        LocationTreeError,
        "retiring a parent with an active child",
    )
    define("L3", "laydown", "P1")
    lot = make_lot(w, "L3", "0.001", suffix="ST")
    expect_refused(
        lambda: w.run(handle_retire_location, RetireLocation, code="L3", reason="gone"),
        LocationTreeError,
        "retiring a location with stock 0.001",
    )
    w.move(lot, kind="scrap", qty="0.001", from_location_id=w.id_of("L3"), reason="damaged")
    assert not w.rows("SELECT 1 FROM cur_materials_stock WHERE location_id = :l", l=w.id_of("L3"))
    w.run(handle_retire_location, RetireLocation, code="L3", reason="gone")
    assert bool(w.one("SELECT retired FROM cur_materials_location WHERE code = 'L3'")["retired"])
    expect_refused(lambda: define("L4", "laydown", "L3"), LocationTreeError, "a retired parent")


def make_item(w: World, code: str, uom: str = "EA", consumable: bool = False) -> str:
    """The project item for a new library item (made by the commands); its record id."""
    w.run(handle_define_item, DefineItem, scope=COMPANY, code=code, title=f"Item {code}",
          category="other", base_uom=uom, consumable=consumable)  # fmt: skip
    return w.run(handle_adopt_item, AdoptItem, item_code=code).stream_id


def make_lot(
    w: World, location_code: str, qty: str, *, suffix: str, po_line: str | None = None
) -> str:
    """A receipt of one line accepted into ``location_code``, with its lot and the receive move."""
    code = w.code("LOT" + suffix)
    item = make_item(w, code)
    location = w.id_of(location_code)
    number = f"{w.project[8:]}-RCPT-{suffix}"
    receipt = w.create(
        "materials.Receipt",
        number,
        f"Receipt {suffix}",
        [
            NewEvent(
                event_type="Receipt.Defined",
                payload={
                    "po_line_id": po_line,
                    "supplier_text": "Acme Valves",
                    "delivery_ref": None,
                    "received_on": "2026-11-02",
                    "location_id": location,
                    "lines": [
                        {
                            "line_no": 1,
                            "project_item_id": item,
                            "qty": qty,
                            "uom": "EA",
                            "heat_no": "H-7781",
                            "condition": "good",
                            "serials_text": None,
                        }  # fmt: skip
                    ],
                },
            )
        ],
    )
    lot = w.create(
        "materials.StockLot",
        f"{number}@1",
        f"Lot {suffix}",
        [
            NewEvent(
                event_type="StockLot.Defined",
                payload={
                    "project_item_id": item,
                    "heat_no": "H-7781",
                    "receipt_id": receipt,
                    "receipt_line": 1,
                    "uom": "EA",
                },  # fmt: skip
            )
        ],
    )
    w.move(lot, kind="receive", qty=qty, to_location_id=location)
    w.add(
        receipt,
        "materials.Receipt",
        [
            NewEvent(
                event_type="Receipt.Accepted",
                payload={
                    "decided_by": ACTOR,
                    "decided_on": "2026-11-02",
                    "lots": [{"line": 1, "lot_id": lot}],
                },  # fmt: skip
            )
        ],
    )
    return lot


def check_po_lines(w: World) -> None:
    code = w.code("PO")
    w.run(handle_define_item, DefineItem, scope=COMPANY, code=code, title="Gasket",
          category="other",
          base_uom="EA")  # fmt: skip
    assert not w.rows("SELECT 1 FROM cur_materials_project_item")
    made = w.run(handle_record_po_line, RecordPoLine, po_number="4471", line_no=3, item_code=code,
                 qty_ordered="20", uom="EA", promised_date="2026-12-01",
                 supplier_text="Acme Valves")  # fmt: skip
    assert made.key == "4471-3"
    adopted = w.one("SELECT * FROM cur_materials_project_item")
    assert adopted["uom"] == "EA"
    line = w.one("SELECT * FROM cur_materials_po_line")
    assert line["project_item_id"] == adopted["id"]
    assert (dec(line["qty_ordered"]), dec(line["qty_received"])) == (Decimal(20), Decimal(0))
    assert (line["po_number"], line["line_no"], line["supplier_text"]) == ("4471", 3, "Acme Valves")
    expect_refused(
        lambda: w.run(
            handle_record_po_line,
            RecordPoLine,
            po_number="4471",
            line_no=4,
            item_code=code,
            qty_ordered="1",
            uom="m",
        ),  # fmt: skip
        InvalidValueError,
        "a unit other than the item's",
    )
    expect_refused(
        lambda: w.run(
            handle_record_po_line,
            RecordPoLine,
            po_number="4471",
            line_no=5,
            item_code=w.code("NONE"),
            qty_ordered="1",
            uom="EA",
        ),  # fmt: skip
        Exception,
        "an item that is not in the library",
    )
    for bad in ("0", "-1", "1.0001", "1000000000.001", "١٢"):
        expect_refused(
            lambda bad=bad: w.run(
                handle_record_po_line,
                RecordPoLine,
                po_number="4471",
                line_no=6,
                item_code=code,
                qty_ordered=bad,
                uom="EA",
            ),  # fmt: skip
            Exception,
            f"quantity {bad!r}",
        )
    w.run(handle_update_po_line, UpdatePoLine, po_number="4471", line_no=3, qty_ordered="25.500")
    line = w.one("SELECT * FROM cur_materials_po_line")
    assert dec(line["qty_ordered"]) == Decimal("25.5") and line["promised_date"] == "2026-12-01"
    w.run(handle_update_po_line, UpdatePoLine, po_number="4471", line_no=3, promised_date=None)
    assert w.one("SELECT promised_date FROM cur_materials_po_line")["promised_date"] is None
    expect_refused(
        lambda: w.run(
            handle_update_po_line, UpdatePoLine, po_number="4471", line_no=3, qty_ordered="25.5"
        ),  # fmt: skip
        Exception,
        "an update that changes nothing",
    )


def snapshot(w: World) -> dict[str, list[dict[str, Any]]]:
    order = {
        "cur_materials_movement": "seq",
        "cur_materials_stock": "lot_id, location_id",
        "cur_materials_reservation": "lot_id, location_id, mto_line_id",
        "cur_materials_receipt_line": "row_id",
    }
    found = {t: w.rows(f"SELECT * FROM {t} ORDER BY {order.get(t, 'id')}") for t in MATERIAL_TABLES}
    found["cur_core_record"] = w.rows("SELECT * FROM cur_core_record ORDER BY id")
    return found


def check_replay(w: World) -> None:
    """Accepted receipt and lot; receive 12.5, reserve 4, issue 3 (with the line), transfer 2."""
    for code, kind, parent in [("P1", "project", None), ("LA", "laydown", "P1"),
                               ("LB", "laydown", "P1")]:  # fmt: skip
        w.run(handle_define_location, DefineLocation, code=code, title=code, kind=kind,
              parent_code=parent)  # fmt: skip
    item = w.code("FL")
    w.run(handle_define_item, DefineItem, scope=COMPANY, code=item, title="Flange",
          category="flange",
          base_uom="EA")  # fmt: skip
    po = w.run(handle_record_po_line, RecordPoLine, po_number="4471", line_no=3, item_code=item,
               qty_ordered="20", uom="EA")  # fmt: skip
    project_item = w.id_of(item)
    la, lb = w.id_of("LA"), w.id_of("LB")
    mto = w.create(
        "materials.MTO",
        "ISO-1@A/MTO",
        "MTO",
        [
            NewEvent(
                event_type="MTO.Defined",
                payload={
                    "derived_document_id": new_ulid(),
                    "revision_id": new_ulid(),
                    "line_count": 1,
                },
            )
        ],  # fmt: skip
    )
    line = w.create(
        "materials.MTOLine",
        "ISO-1@A/MTO/001",
        "Line 1",
        [
            NewEvent(
                event_type="MTOLine.Defined",
                payload={
                    "mto_id": mto,
                    "line_no": 1,
                    "project_item_id": project_item,
                    "qty": "6.000",
                    "uom": "EA",
                    "tag_id": None,
                    "work_package_id": None,
                },
            )
        ],  # fmt: skip
    )
    number = f"{w.project[8:]}-RCPT-0031"
    receipt = w.create(
        "materials.Receipt",
        number,
        "Flanges",
        [
            NewEvent(
                event_type="Receipt.Defined",
                payload={
                    "po_line_id": po.stream_id,
                    "supplier_text": "Acme Valves",
                    "delivery_ref": None,
                    "received_on": "2026-11-02",
                    "location_id": la,
                    "lines": [
                        {
                            "line_no": 1,
                            "project_item_id": project_item,
                            "qty": "12.500",
                            "uom": "EA",
                            "heat_no": "H-7781",
                            "condition": "good",
                            "serials_text": None,
                        }
                    ],
                },
            )
        ],  # fmt: skip
    )
    lot = w.create(
        "materials.StockLot",
        f"{number}@1",
        "Lot 1",
        [
            NewEvent(
                event_type="StockLot.Defined",
                payload={
                    "project_item_id": project_item,
                    "heat_no": "H-7781",
                    "receipt_id": receipt,
                    "receipt_line": 1,
                    "uom": "EA",
                },
            )
        ],  # fmt: skip
    )
    w.move(lot, kind="receive", qty="12.500", to_location_id=la)
    w.add(receipt, "materials.Receipt",
          [NewEvent(event_type="Receipt.Accepted",
                    payload={"decided_by": ACTOR, "decided_on": "2026-11-02",
                             "lots": [{"line": 1, "lot_id": lot}]})])  # fmt: skip
    assert dec(w.one("SELECT qty_received FROM cur_materials_po_line")["qty_received"]) == Decimal(
        "12.5"
    )
    assert w.one("SELECT lot_id FROM cur_materials_receipt_line")["lot_id"] == lot

    def stock(location: str) -> tuple[Decimal, Decimal, Decimal] | None:
        found = w.rows("SELECT * FROM cur_materials_stock WHERE lot_id = :l AND location_id = :c",
                       l=lot, c=location)  # fmt: skip
        if not found:
            return None
        row = found[0]
        return dec(row["on_hand"]), dec(row["reserved"]), dec(row["available"])

    D = Decimal
    assert stock(la) == (D("12.5"), D(0), D("12.5"))
    w.move(lot, kind="reserve", qty="4.000", from_location_id=la, mto_line_id=line)
    assert stock(la) == (D("12.5"), D(4), D("8.5"))  # available = on_hand - reserved, stored
    reservation = w.one("SELECT qty FROM cur_materials_reservation")
    assert dec(reservation["qty"]) == D(4)
    w.move(lot, kind="issue", qty="3.000", from_location_id=la, mto_line_id=line,
           person="R. Singh")  # fmt: skip
    assert stock(la) == (D("9.5"), D(1), D("8.5"))  # the reservation is consumed first
    assert dec(w.one("SELECT qty FROM cur_materials_reservation")["qty"]) == D(1)
    mto_line = w.one("SELECT * FROM cur_materials_mto_line")
    assert (dec(mto_line["reserved_qty"]), dec(mto_line["issued_qty"])) == (D(1), D(3))
    assert dec(w.one("SELECT issued_net FROM cur_materials_lot")["issued_net"]) == D(3)
    w.move(lot, kind="transfer", qty="2.000", from_location_id=la, to_location_id=lb)
    assert stock(la) == (D("7.5"), D(1), D("6.5")) and stock(lb) == (D(2), D(0), D(2))
    moves = w.rows("SELECT * FROM cur_materials_movement ORDER BY seq")
    assert [m["kind"] for m in moves] == ["receive", "reserve", "issue", "transfer"]
    events = w.rows(
        "SELECT seq, event_type FROM events WHERE event_type = 'StockLot.Moved' ORDER BY seq"
    )
    assert [m["seq"] for m in moves] == [e["seq"] for e in events]  # seq is the event's
    assert moves[2]["person"] == "R. Singh" and moves[2]["mto_line_id"] == line
    assert moves[0]["actor"] == ACTOR and moves[0]["recorded_at"]
    # a return puts issued stock back, an unreserve and a scrap take rows to zero and delete them
    w.move(lot, kind="return", qty="1.000", to_location_id=lb)
    assert stock(lb) == (D(3), D(0), D(3))
    assert dec(w.one("SELECT issued_net FROM cur_materials_lot")["issued_net"]) == D(2)
    w.move(lot, kind="unreserve", qty="1.000", from_location_id=la, mto_line_id=line)
    assert not w.rows("SELECT 1 FROM cur_materials_reservation"), "a reservation at zero is deleted"
    assert stock(la) == (D("7.5"), D(0), D("7.5"))
    w.move(lot, kind="scrap", qty="7.500", from_location_id=la, reason="damaged")
    assert stock(la) is None, "a stock row at zero is deleted"
    w.move(lot, kind="adjust", direction="out", qty="3.000", from_location_id=lb, reason="lost")
    assert stock(lb) is None
    # Decimal exactness: three moves of 0.100 are 0.300, not 0.30000000000000004
    other = make_lot(w, "LA", "0.100", suffix="DEC")
    for _ in range(2):
        w.move(other, kind="receive", qty="0.100", to_location_id=la)
    row = w.one("SELECT on_hand, available FROM cur_materials_stock WHERE lot_id = :l", l=other)
    assert dec(row["on_hand"]) == D("0.300") and dec(row["available"]) == D("0.300"), row
    for _ in range(3):
        w.move(other, kind="issue", qty="0.100", from_location_id=la)
    assert not w.rows("SELECT 1 FROM cur_materials_stock WHERE lot_id = :l", l=other)
    # a movement that would make a balance negative is refused (nothing is written)
    before = w.one("SELECT COUNT(*) AS n FROM events")["n"]
    expect_refused(
        lambda: w.move(other, kind="scrap", qty="0.001", from_location_id=la, reason="x"),
        Exception,
        "a negative balance",
    )
    assert w.one("SELECT COUNT(*) AS n FROM events")["n"] == before


def check_rebuild(w: World) -> None:
    check_replay(w)
    before = snapshot(w)
    assert before["cur_materials_movement"] and before["cur_materials_receipt_line"]
    rebuild_projections(w.target)
    after = snapshot(w)
    for table, rows in before.items():
        assert after[table] == rows, f"{table} differs after a rebuild"


def check_targets(w: World) -> None:
    targets = installed_targets()
    wanted = {"materials_item_master": "company", "materials_location": "project",
              "materials_po_line": "project"}  # fmt: skip
    assert {k: targets[k].scope for k in wanted} == wanted
    assert all(targets[k].module == "materials" for k in wanted)
    target = targets["materials_item_master"]
    a, b, c = w.code("TA"), w.code("TB"), w.code("TC")
    grid = Grid(
        columns=[
            "code",
            "description",
            "category",
            "uom",
            "size",
            "rating",
            "material",
            "consumable",
        ],
        rows=[
            [a, "Item A", "valve", "EA", "6 in", "150#", "CS", "false"],
            [b, "Item B", "consumable", "kg", "", "", "", "true"],
            [c, "Item C", "valve", "XX", "", "", "", "false"],
        ],  # fmt: skip
    )
    with open_uow(w.target, readonly=True) as uow:
        plan = target.plan(uow.conn(), COMPANY, None, grid)  # type: ignore[arg-type]
    assert plan.counts() == {"new": 2, "existing": 0, "invalid": 1}, plan.counts()
    assert plan.invalid[0][0] == 4 and c not in plan.invalid[0][1]
    corr = new_ulid()
    with open_uow(w.target) as uow:
        made = target.apply(uow, COMPANY, None, plan, actor=ACTOR, source="legacy:test",  # type: ignore[arg-type]
                            correlation_id=corr, confidentiality=None)  # fmt: skip
    assert [m.key for m in made] == [a, b]
    assert w.one("SELECT consumable FROM cur_materials_item_master WHERE code = :c", c=b)[
        "consumable"
    ]
    with open_uow(w.target, readonly=True) as uow:
        again = target.plan(uow.conn(), COMPANY, None, grid)  # type: ignore[arg-type]
        compared = target.compare(uow.conn(), COMPANY, None, grid, {a, b})  # type: ignore[arg-type]
        reasons = target.reversals(uow.conn(), COMPANY, [m.record_id for m in made], corr)
    assert again.counts() == {"new": 0, "existing": 2, "invalid": 1}, again.counts()
    assert (compared.valid, compared.matched, compared.invalid) == (2, 2, 1), compared
    assert all(r.reversible for r in reasons), reasons
    with open_uow(w.target) as uow:
        n = target.reverse(uow, COMPANY, [m.record_id for m in made], actor=ACTOR,
                           source="legacy:test", correlation_id=corr, reason="undo")  # fmt: skip
    assert n == 2
    assert all(
        bool(r["voided"])
        for r in w.rows("SELECT voided FROM cur_core_record WHERE key IN (:a, :b)", a=a, b=b)
    )
    # locations: parents first, a tree deeper than 5 is refused row by row, a second root too
    locations = targets["materials_location"]
    rows = [["R", "Root", "project", ""], ["WH", "Warehouse", "warehouse", "R"],
            ["Q2", "Another root", "project", ""], ["S1", "Sub 1", "laydown", "WH"],
            ["S2", "Sub 2", "laydown", "S1"], ["S3", "Sub 3", "laydown", "S2"],
            ["S4", "Sub 4", "laydown", "S3"], ["S5", "Sub 5", "laydown", "S4"]]  # fmt: skip
    grid = Grid(columns=["code", "title", "kind", "parent_code"], rows=rows)  # type: ignore[arg-type]
    with open_uow(w.target, readonly=True) as uow:
        plan = locations.plan(uow.conn(), w.project, None, grid)  # type: ignore[arg-type]
    assert [r.key for r in plan.rows] == ["R", "WH", "S1", "S2", "S3", "S4"], plan.rows
    assert sorted(line for line, _ in plan.invalid) == [4, 9], plan.invalid  # Q2 and S5 (depth 6)


def check_class_filter(w: World) -> None:
    for code, kind, parent in [("P1", "project", None), ("LA", "laydown", "P1")]:
        w.run(handle_define_location, DefineLocation, code=code, title=code, kind=kind,
              parent_code=parent)  # fmt: skip
    hidden = make_lot(w, "LA", "5.000", suffix="HID")
    shown = make_lot(w, "LA", "2.000", suffix="SEE")
    hidden_key = w.one("SELECT key FROM cur_core_record WHERE id = :i", i=hidden)["key"]
    with open_uow(w.target) as uow:
        uow.conn().execute(text("CREATE TABLE x_class (id TEXT PRIMARY KEY, cls TEXT)"))
        uow.conn().execute(text("INSERT INTO x_class VALUES (:i, 'restricted')"), {"i": hidden})
        uow.conn().execute(text("INSERT INTO x_class VALUES (:i, 'internal')"), {"i": shown})
    real = {m.name: m for m in load_modules()}
    source = ConfidentialSource(
        record_types=frozenset({"materials.StockLot"}),
        table="x_class",
        id_column="id",
        class_column="cls",  # fmt: skip
    )
    changed = [
        dataclasses.replace(m, confidential=(source,)) if m.name == "materials" else m
        for m in real.values()
    ]
    with use_modules(changed), open_uow(w.target, readonly=True) as uow:
        conn = uow.conn()
        low = views.stock(conn, w.project, viewer=LOWEST)
        assert [r.lot for r in low] != [] and hidden_key not in {r.lot for r in low}
        assert views.stock(conn, w.project, limit=1)  # the default viewer; a hidden row is no place
        assert {r.lot for r in views.stock(conn, w.project, viewer=Viewer(level=1))} >= {hidden_key}
        assert hidden_key not in {m.lot for m in views.movements(conn, w.project, viewer=LOWEST)}
        assert hidden_key in {
            m.lot for m in views.movements(conn, w.project, viewer=Viewer(level=1))
        }
        expect_refused(
            lambda: views.lot_detail(conn, w.project, hidden_key, viewer=LOWEST),
            LotNotFoundError,
            "a hidden lot's detail",
        )
        assert (
            views.lot_detail(conn, w.project, hidden_key, viewer=Viewer(level=1)).key == hidden_key
        )
        assert not views.stock(conn, w.project, lot=hidden_key)  # filtered before the lot filter
