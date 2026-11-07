"""materials section: the item library, the location tree, PO lines and receipts with and without an
MTR, the stock lots those receipts make, movements of every kind, and a take-off (MTO) with
reservations and shortages.

Everything is written through the real command handlers, one unit of work per command, as the
people of the roster (``core``): the library, the locations and the cost codes as the admin, the
receipts and the stock as the materials coordinator. The take-off is a derived document of kind
``mto``: a CSV that the extraction job reads and checks against a schema, then published with
``PublishDerivedMto``. Its lines are assigned to the project's work packages when the awp section
made any; with none, they stay unassigned and the section says so.
"""

from __future__ import annotations

import csv
import hashlib
import io
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from tl_adapters.db import open_uow
from tl_core.files.service import CompleteUpload, RegisterUpload
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot, handle_import_cost_snapshot
from tl_mod_cost.imports.model import CostRow
from tl_mod_documents.derivation import rows as derived_rows
from tl_mod_documents.derivation.derived import (
    OpenDerivedDocument,
    StartExtraction,
    handle_open_derived_document,
    handle_start_extraction,
)
from tl_mod_documents.derivation.schemas import (
    RegisterDocumentSchema,
    handle_register_document_schema,
)
from tl_mod_documents.derivation.worker import build_worker
from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document
from tl_mod_documents.handlers.revisions import CreateRevision, handle_create_revision
from tl_mod_materials.errors import MtrRequiredError
from tl_mod_materials.handlers.items import (
    AdoptItem,
    DefineItem,
    handle_adopt_item,
    handle_define_item,
)
from tl_mod_materials.handlers.locations import DefineLocation, handle_define_location
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
from tl_mod_materials.handlers.mto import (
    AssignMtoLines,
    PublishDerivedMto,
    handle_assign_mto_lines,
    handle_publish_derived_mto,
)
from tl_mod_materials.handlers.po_lines import RecordPoLine, handle_record_po_line
from tl_mod_materials.handlers.receipts import (
    AcceptReceipt,
    CreateReceipt,
    InspectReceipt,
    ReceiptLineIn,
    handle_accept_receipt,
    handle_create_receipt,
    handle_inspect_receipt,
)

from dev.seed.demo_project.core import ADMIN
from dev.seed.demo_project.pdf import make_pdf
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import PROJECT, SOURCE, START, TODAY, World, actor_of

ITEMS = Path(__file__).resolve().parent / "data" / "materials" / "items.csv"
COMPANY = "company"
STORES = "treyes"  # materials coordinator, company materials superuser
DOCUMENTS = "ipetrov"  # document controller: the take-off's source document and its extraction
ENGINEER = "lhartmann"
TAKEOFF_DOC = "P200-200-ISO-0901"  # the isometrics the take-off is read from
TAKEOFF_SCHEMA = "material-takeoff"
MTR_CATEGORIES = ("pipe", "fitting", "flange", "valve", "steel")
MTR_SETTING = "materials.receipt.mtr_required_categories"
PERSONS = ("Callum Brooks", "Priya Nair", "Hana Sato", "Lena Hartmann")
SUPPLIERS = ("Bayou Steel Pipe Co.", "Coastal Flange and Fitting", "Harbour Valve Supply")
COST_CODES = (
    ("4210-PIP", "Piping, installation"),
    ("4220-PIP-WLD", "Piping, welding"),
    ("4310-STR", "Structural steel"),
    ("4410-ELE", "Electrical, cable and tray"),
    ("4510-INS", "Instrumentation"),
    ("4610-MEC", "Mechanical equipment"),
    ("4710-INS-M", "Insulation"),
    ("4810-PNT", "Painting and coatings"),
)
LOCATIONS = (  # code, title, kind, parent: project > laydown > warehouse > toolcrib > gang box
    ("P200", "P200 North Refinery HT-2 site", "project", None),
    ("L1", "Laydown yard L1, north", "laydown", "P200"),
    ("L2", "Laydown yard L2, pipe rack", "laydown", "P200"),
    ("L3", "Laydown yard L3, tank farm", "laydown", "P200"),
    ("WH1", "Warehouse WH1", "warehouse", "L1"),
    ("TC1", "Tool crib TC1", "toolcrib", "WH1"),
    ("GB1", "Gang box GB1, piping", "gang_box", "TC1"),
    ("GB2", "Gang box GB2, civil", "gang_box", "TC1"),
    ("GB3", "Gang box GB3, electrical", "gang_box", "TC1"),
    ("GB4", "Gang box GB4, insulation", "gang_box", "TC1"),
)
RECEIPT_LOCATIONS = ("L1", "L2", "L3", "WH1")
MOVE_LOCATIONS = ("WH1", "TC1", "GB1", "GB2", "GB3", "GB4")
QTY_RANGE = {  # one heat of a delivery line, by unit
    "m": (20, 120),
    "EA": (2, 30),
    "SET": (20, 200),
    "BOX": (1, 10),
    "kg": (50, 800),
    "L": (5, 60),
    "m3": (2, 10),
}
TAKEOFF_RANGE = {  # one take-off line, by unit: most lines outrun the stock on hand
    "m": (40, 300),
    "EA": (4, 60),
    "SET": (20, 120),
    "BOX": (1, 8),
    "kg": (100, 1500),
    "L": (10, 200),
    "m3": (2, 8),
}
PO_LINES = 55  # one receipt against each
PO_COUNT = 11
TAKEOFF_LINES = 150
NO_MTR_RECEIPTS = 10  # receipts of an MTR category that Accept refuses
LEFT_RECEIVED = 4  # of those, the last four are left Received, not Inspected
RESERVATIONS = 70
UNRESERVATIONS = 15
TRANSFERS = 90
ISSUES = 100
RETURNS = 25
ADJUSTMENTS = 30
SCRAPS = 15

TAKEOFF_SCHEMA_JSON: dict[str, Any] = {
    "type": "object",
    "required": ["line", "item", "qty", "uom"],
    "properties": {
        "line": {"type": "string"},
        "item": {"type": "string"},
        "qty": {"type": "string"},
        "uom": {"type": "string"},
    },
}
TAKEOFF_MAPPING: dict[str, Any] = {
    "target": "mto",
    "key_column": "line",
    "columns": [
        {"column": "line", "to": "number"},
        {"column": "item", "to": "item_code"},
        {"column": "qty", "to": "qty"},
        {"column": "uom", "to": "uom"},
    ],
}


@dataclass(frozen=True)
class Item:
    code: str
    title: str
    category: str
    uom: str
    size: str | None
    rating: str | None
    material: str | None
    consumable: bool


@dataclass(frozen=True)
class Stock:
    lot: str
    loc: str
    item_id: str
    uom: str
    available: Decimal


def load_items() -> list[Item]:
    with ITEMS.open(newline="") as fh:
        return [
            Item(
                code=row["code"],
                title=row["title"],
                category=row["category"],
                uom=row["base_uom"],
                size=row["size_text"] or None,
                rating=row["rating_text"] or None,
                material=row["material_code"] or None,
                consumable=row["consumable"] == "true",
            )
            for row in csv.DictReader(fh)
        ]


def define_library(world: World, items: list[Item]) -> None:
    for item in items:
        world.run(
            handle_define_item,
            DefineItem,
            by=ADMIN,
            scope=COMPANY,
            code=item.code,
            title=item.title,
            category=item.category,
            base_uom=item.uom,
            size_text=item.size,
            rating_text=item.rating,
            material_code=item.material,
            consumable=item.consumable,
        )


def adopt(world: World, rng: random.Random, items: list[Item]) -> list[Item]:
    """The project adopts 130 of the 152 library items; the others stay library-only."""
    chosen = sorted(rng.sample(range(len(items)), 130))
    adopted = [items[i] for i in chosen]
    for item in adopted:
        world.run(handle_adopt_item, AdoptItem, by=STORES, item_code=item.code)
    return adopted


def define_tree(world: World) -> None:
    for code, title, kind, parent in LOCATIONS:
        world.run(
            handle_define_location,
            DefineLocation,
            by=ADMIN,
            code=code,
            title=title,
            kind=kind,
            parent_code=parent,
        )


def require_mtr(world: World) -> None:
    world.run(
        handle_change_setting,
        ChangeSetting,
        by=ADMIN,
        key=MTR_SETTING,
        layer=PROJECT,
        value=list(MTR_CATEGORIES),
    )


def cost_codes(world: World) -> None:
    """The cost codes come from a cost snapshot (the cost module's one way in); as of October."""
    world.run(
        handle_import_cost_snapshot,
        ImportCostSnapshot,
        by=ADMIN,
        period="2026-10",
        as_of="2026-10-31",
        currency="USD",
        source_name="demo cost export",
        rows=[CostRow(code=code, description=text) for code, text in COST_CODES],
    )


def qty_for(rng: random.Random, uom: str) -> int:
    low, high = QTY_RANGE[uom]
    return rng.randint(low, high)


def record_po_lines(
    world: World, rng: random.Random, adopted: list[Item]
) -> list[tuple[str, int, Item]]:
    """PO_LINES lines over PO_COUNT purchase orders: (po number, line number, item)."""
    lines: list[tuple[str, int, Item]] = []
    for position in range(PO_LINES):
        po = f"P200-PO-{101 + position // 5:04d}"
        line_no = position % 5 + 1
        item = rng.choice(adopted)
        with world.on(START + timedelta(days=2 + position // 10)):
            world.run(
                handle_record_po_line,
                RecordPoLine,
                by=STORES,
                po_number=po,
                line_no=line_no,
                item_code=item.code,
                qty_ordered=str(qty_for(rng, item.uom) * 6),
                uom=item.uom,
                promised_date=(START + timedelta(days=45)).isoformat(),
                supplier_text=SUPPLIERS[position // 5 % len(SUPPLIERS)],
            )
        lines.append((po, line_no, item))
    return lines


def attach_mtr(world: World, receipt_id: str, label: str, data: bytes) -> None:
    """The MTR into the receipt's ``mtr`` slot, through the file service as the module's own
    write (``by_module``: the receipt type's generic allow-list does not apply)."""
    base = {"actor": actor_of(STORES), "source": SOURCE, "scope": PROJECT}
    declared = RegisterUpload(
        **base,
        record_id=receipt_id,
        slot="mtr",
        filename=f"{label}-mtr.pdf",
        content_type="application/pdf",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    with open_uow(world.target) as uow:
        ticket = world.files.register_upload(uow, declared, by_module=True)
    with open_uow(world.target) as uow:
        world.files.complete_upload(
            uow,
            CompleteUpload(**base, upload_id=ticket.upload_id),
            io.BytesIO(data),
            by_module=True,
        )


def deliver(
    world: World,
    rng: random.Random,
    po_lines: list[tuple[str, int, Item]],
) -> tuple[list[str], date]:
    """One receipt per PO line, 3 to 5 heats each. Returns the lot keys and the last day.

    Of the PO lines whose item needs an MTR, ``NO_MTR_RECEIPTS`` get no MTR: Accept is refused for
    the inspected ones (the last ``LEFT_RECEIVED`` stay Received). Every other receipt is accepted.
    """
    candidates = [i for i, (_, _, item) in enumerate(po_lines) if item.category in MTR_CATEGORIES]
    no_mtr = set(rng.sample(candidates, NO_MTR_RECEIPTS))
    left = set(sorted(no_mtr)[-LEFT_RECEIVED:])
    span = (TODAY - START).days - 25
    lots: list[str] = []
    refused = 0
    day = START
    for position, (po, line_no, item) in enumerate(po_lines):
        day = START + timedelta(days=10 + position * span // PO_LINES)
        heats = rng.randint(3, 5)
        lines = [
            ReceiptLineIn(
                item_code=item.code,
                qty=str(qty_for(rng, item.uom)),
                heat_no=f"HT{rng.randint(1000, 9999)}-{heat}",
            )
            for heat in range(1, heats + 1)
        ]
        with world.on(day):
            made = world.run(
                handle_create_receipt,
                CreateReceipt,
                by=STORES,
                po_line=f"{po}-{line_no}",
                received_on=day.isoformat(),
                location_code=RECEIPT_LOCATIONS[position % len(RECEIPT_LOCATIONS)],
                lines=lines,
            )
            if position in left:
                continue
            world.run(handle_inspect_receipt, InspectReceipt, by=STORES, stream_id=made.stream_id)
            if item.category in MTR_CATEGORIES and position not in no_mtr:
                attach_mtr(
                    world,
                    made.stream_id,
                    made.key,
                    make_pdf(
                        f"Mill test report {made.key}",
                        [item.title, "Heats " + ", ".join(str(x.heat_no) for x in lines)],
                    ),
                )
            version = world.version(made.stream_id)
            if position in no_mtr:
                events_before = world.event_count()
                try:
                    world.run(
                        handle_accept_receipt,
                        AcceptReceipt,
                        by=STORES,
                        stream_id=made.stream_id,
                        expected_version=version,
                    )
                except MtrRequiredError:
                    refused += 1
                assert world.event_count() == events_before, "a refused accept wrote events"
                continue
            world.run(
                handle_accept_receipt,
                AcceptReceipt,
                by=STORES,
                stream_id=made.stream_id,
                expected_version=version,
            )
            lots.extend(f"{made.key}@{n}" for n in range(1, heats + 1))
    assert refused == NO_MTR_RECEIPTS - LEFT_RECEIVED, refused
    return lots, day


def stock_rows(world: World) -> list[Stock]:
    found = world.rows(
        "SELECT lot.key AS lot, loc.key AS loc, c.project_item_id AS item_id, c.uom AS uom, "
        "s.available AS available FROM cur_materials_stock s "
        "JOIN cur_core_record lot ON lot.id = s.lot_id "
        "JOIN cur_core_record loc ON loc.id = s.location_id "
        "JOIN cur_materials_lot c ON c.id = s.lot_id "
        "WHERE s.scope = :s AND s.on_hand > 0 ORDER BY lot.key, loc.key",
        s=PROJECT,
    )
    return [
        Stock(
            lot=str(r["lot"]),
            loc=str(r["loc"]),
            item_id=str(r["item_id"]),
            uom=str(r["uom"]),
            available=Decimal(str(r["available"])),
        )
        for r in found
    ]


def publish_takeoff(world: World, rng: random.Random, adopted: list[Item], day: date) -> list[str]:
    """The take-off: a source document and its revision, the schema, the CSV that the extraction
    job reads, the derived document published as the MTO. Returns the take-off line keys."""
    with world.on(START + timedelta(days=1)):
        doc = world.run(
            handle_register_document,
            RegisterDocument,
            by=ENGINEER,
            number=TAKEOFF_DOC,
            title="Piping isometrics, area 200, take-off source",
            doc_type="ISO",
            discipline="PIP",
        )
        revision = world.run(
            handle_create_revision, CreateRevision, by=ENGINEER, document_id=doc.stream_id
        )
        world.run(
            handle_register_document_schema,
            RegisterDocumentSchema,
            by=ADMIN,
            scope="company",
            code=TAKEOFF_SCHEMA,
            semver="1.0.0",
            title="Material take-off",
            json_schema=TAKEOFF_SCHEMA_JSON,
            key_column="line",
            target_kind="mto",
            mapping=TAKEOFF_MAPPING,
        )
    with world.on(day):
        opened = world.run(
            handle_open_derived_document,
            OpenDerivedDocument,
            by=DOCUMENTS,
            revision_id=revision.stream_id,
            schema_code=TAKEOFF_SCHEMA,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["line", "item", "qty", "uom"])
        for number in range(1, TAKEOFF_LINES + 1):
            item = rng.choice(adopted)
            writer.writerow(
                [f"{number:03d}", item.code, str(rng.randint(*TAKEOFF_RANGE[item.uom])), item.uom]
            )
        world.upload(
            opened.stream_id,
            slot="content",
            filename="takeoff.csv",
            data=buffer.getvalue().encode("utf-8"),
            by=DOCUMENTS,
            content_type="text/csv",
        )
        world.run(
            handle_start_extraction, StartExtraction, by=DOCUMENTS, derived_id=opened.stream_id
        )
        worker = build_worker(world.target, world.files)
        try:
            worker.runner.run_until_idle()
        finally:
            worker.close()
        with open_uow(world.target, readonly=True) as uow:
            derived = derived_rows.get_derived(uow.conn(), opened.stream_id)
        assert derived is not None and derived.state == "Valid", derived
        world.run(
            handle_publish_derived_mto,
            PublishDerivedMto,
            by=STORES,
            derived_id=opened.stream_id,
            expected_content_rev=derived.content_rev,
        )
    return [
        str(r["key"])
        for r in world.rows(
            "SELECT r.key AS key FROM cur_materials_mto_line l "
            "JOIN cur_core_record r ON r.id = l.id WHERE l.scope = :s AND r.voided = :no "
            "ORDER BY r.key",
            s=PROJECT,
            no=False,
        )
    ]


def assign_to_packages(world: World, rng: random.Random, line_keys: list[str], day: date) -> None:
    """Most take-off lines go to the project's CWPs and IWPs, when the awp section made any."""
    packages = [
        str(r["key"])
        for r in world.rows(
            "SELECT key FROM cur_core_record WHERE scope = :s "
            "AND type IN ('awp.CWP', 'awp.IWP') AND voided = :no ORDER BY key",
            s=PROJECT,
            no=False,
        )
    ]
    if not packages:
        print("materials: no CWP or IWP in the project; the take-off lines stay unassigned")
        return
    groups: dict[str, list[str]] = {}
    for key in line_keys:
        if rng.random() < 0.8:
            groups.setdefault(rng.choice(packages), []).append(key)
    with world.on(day):
        for number in sorted(groups):
            world.run(
                handle_assign_mto_lines,
                AssignMtoLines,
                by=STORES,
                mto_lines=groups[number],
                work_package_number=number,
            )


def reserve_some(world: World, rng: random.Random, day: date) -> None:
    """Reservations against take-off lines out of the stock on hand; some are released again."""
    held: dict[tuple[str, str, str], int] = {}
    uoms: dict[str, str] = {}
    with world.on(day):
        for _ in range(RESERVATIONS):
            lines = world.rows(
                "SELECT r.key AS key, l.id AS id, l.project_item_id AS item_id, l.qty AS qty, "
                "l.reserved_qty AS reserved FROM cur_materials_mto_line l "
                "JOIN cur_core_record r ON r.id = l.id WHERE l.scope = :s AND r.voided = :no "
                "ORDER BY r.key",
                s=PROJECT,
                no=False,
            )
            open_lines = [
                r for r in lines if Decimal(str(r["qty"])) - Decimal(str(r["reserved"])) >= 1
            ]
            stock = stock_rows(world)
            picked = None
            for line in rng.sample(open_lines, len(open_lines)):
                options = [
                    s for s in stock if s.item_id == str(line["item_id"]) and s.available >= 1
                ]
                if options:
                    picked = (line, rng.choice(options))
                    break
            if picked is None:
                continue
            line, where = picked
            room = int(Decimal(str(line["qty"])) - Decimal(str(line["reserved"])))
            qty = rng.randint(1, min(room, int(where.available), 10))
            world.run(
                handle_reserve_stock,
                ReserveStock,
                by=STORES,
                movements=[
                    Movement(
                        lot_key=where.lot,
                        qty=str(qty),
                        uom=where.uom,
                        from_location=where.loc,
                        mto_line_id=str(line["id"]),
                    )
                ],
            )
            key = (where.lot, where.loc, str(line["id"]))
            held[key] = held.get(key, 0) + qty
            uoms[where.lot] = where.uom
        for _ in range(UNRESERVATIONS):
            open_holds = sorted(k for k, v in held.items() if v > 0)
            if not open_holds:
                break
            lot, loc, line_id = rng.choice(open_holds)
            qty = rng.randint(1, held[(lot, loc, line_id)])
            world.run(
                handle_unreserve_stock,
                UnreserveStock,
                by=STORES,
                movements=[
                    Movement(
                        lot_key=lot,
                        qty=str(qty),
                        uom=uoms[lot],
                        from_location=loc,
                        mto_line_id=line_id,
                    )
                ],
            )
            held[(lot, loc, line_id)] -= qty


def _spread(first: date, step: int, total: int) -> date:
    """The day of the ``step``-th of ``total`` movements: the days from ``first`` to today."""
    return min(TODAY, first + timedelta(days=(TODAY - first).days * step // total))


def moves(world: World, rng: random.Random, first: date, lot_items: dict[str, Item]) -> None:
    """Transfers, issues (consumables always against a cost code), returns, adjustments with a
    reason, and disposals. Every quantity is drawn from what the stock holds at the moment."""
    codes = {code: world.id_of(code) for code, _ in COST_CODES}
    total = TRANSFERS + ISSUES + RETURNS + ADJUSTMENTS + SCRAPS
    step = 0
    targets = ("L1", "L2", "L3", "WH1", "TC1", "GB1", "GB2", "GB3", "GB4")
    for _ in range(TRANSFERS):
        step += 1
        where = rng.choice([s for s in stock_rows(world) if s.available >= 1])
        to = rng.choice([t for t in targets if t != where.loc])
        with world.on(_spread(first, step, total)):
            world.run(
                handle_transfer_stock,
                TransferStock,
                by=STORES,
                movements=[
                    Movement(
                        lot_key=where.lot,
                        qty=str(rng.randint(1, int(where.available))),
                        uom=where.uom,
                        from_location=where.loc,
                        to_location=to,
                    )
                ],
            )
    issued: dict[str, int] = {}
    for _ in range(ISSUES):
        step += 1
        options = [s for s in stock_rows(world) if s.available >= 1 and s.loc in MOVE_LOCATIONS]
        where = rng.choice(options)
        item = lot_items[where.lot]
        cost_code = None
        if item.consumable or rng.random() < 0.5:
            cost_code = codes[rng.choice(COST_CODES)[0]]
        qty = rng.randint(1, min(int(where.available), 5))
        with world.on(_spread(first, step, total)):
            world.run(
                handle_issue_stock,
                IssueStock,
                by=STORES,
                movements=[
                    Movement(
                        lot_key=where.lot,
                        qty=str(qty),
                        uom=where.uom,
                        from_location=where.loc,
                        cost_code_id=cost_code,
                        person=rng.choice(PERSONS),
                    )
                ],
            )
        issued[where.lot] = issued.get(where.lot, 0) + qty
    for _ in range(RETURNS):
        step += 1
        returnable = sorted(k for k, v in issued.items() if v > 0)
        if not returnable:
            break
        lot = rng.choice(returnable)
        qty = rng.randint(1, min(issued[lot], 3))
        issued[lot] -= qty
        with world.on(_spread(first, step, total)):
            world.run(
                handle_return_stock,
                ReturnStock,
                by=STORES,
                movements=[
                    Movement(
                        lot_key=lot,
                        qty=str(qty),
                        uom=_uom_of(world, lot),
                        to_location="TC1",
                    )
                ],
            )
    for n in range(ADJUSTMENTS):
        step += 1
        with world.on(_spread(first, step, total)):
            if n % 2 == 0:  # a surplus found: into a location, with the reason
                where = rng.choice(stock_rows(world))
                world.run(
                    handle_adjust_stock,
                    AdjustStock,
                    by=STORES,
                    movements=[
                        Movement(
                            lot_key=where.lot,
                            qty=str(rng.randint(1, 3)),
                            uom=where.uom,
                            to_location=rng.choice(MOVE_LOCATIONS),
                            direction="in",
                            reason="Cycle count: surplus found on the shelf",
                        )
                    ],
                )
            else:  # a shortage against the book: out of a location, with the reason
                where = rng.choice([s for s in stock_rows(world) if s.available >= 1])
                world.run(
                    handle_adjust_stock,
                    AdjustStock,
                    by=STORES,
                    movements=[
                        Movement(
                            lot_key=where.lot,
                            qty=str(rng.randint(1, min(int(where.available), 3))),
                            uom=where.uom,
                            from_location=where.loc,
                            direction="out",
                            reason="Cycle count: short against the book",
                        )
                    ],
                )
    for _ in range(SCRAPS):
        step += 1
        where = rng.choice([s for s in stock_rows(world) if s.available >= 1])
        with world.on(_spread(first, step, total)):
            world.run(
                handle_scrap_stock,
                ScrapStock,
                by=STORES,
                movements=[
                    Movement(
                        lot_key=where.lot,
                        qty="1",
                        uom=where.uom,
                        from_location=where.loc,
                        reason="Damaged in handling, tagged nonconforming for disposal",
                    )
                ],
            )


def _uom_of(world: World, lot_key: str) -> str:
    return str(
        world.scalar(
            "SELECT c.uom FROM cur_materials_lot c JOIN cur_core_record r ON r.id = c.id "
            "WHERE r.key = :k AND r.scope = :s",
            k=lot_key,
            s=PROJECT,
        )
    )


def lot_items_of(world: World, items: dict[str, Item]) -> dict[str, Item]:
    """The library item of every lot of the project, by lot key."""
    found = world.rows(
        "SELECT r.key AS lot, p.key AS item FROM cur_materials_lot c "
        "JOIN cur_core_record r ON r.id = c.id JOIN cur_core_record p ON p.id = c.project_item_id "
        "WHERE r.scope = :s",
        s=PROJECT,
    )
    return {str(row["lot"]): items[str(row["item"])] for row in found}


def build(world: World, rng: random.Random) -> None:
    items = load_items()
    by_code = {item.code: item for item in items}
    with world.on(START):
        define_library(world, items)
        adopted = adopt(world, rng, items)
        define_tree(world)
        require_mtr(world)
    with world.on(TODAY):
        cost_codes(world)
    po_lines = record_po_lines(world, rng, adopted)
    lots, last_receipt = deliver(world, rng, po_lines)
    lot_items = lot_items_of(world, by_code)
    assert set(lots) <= set(lot_items), "every accepted lot has a project item"
    takeoff_day = last_receipt + timedelta(days=1)
    line_keys = publish_takeoff(world, rng, adopted, takeoff_day)
    assign_to_packages(world, rng, line_keys, takeoff_day)
    reserve_some(world, rng, takeoff_day)
    moves(world, rng, takeoff_day, lot_items)


register("materials", build, needs=("materials.ItemMaster",))
