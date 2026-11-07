"""The materials schema, fixtures and standards edition (S1): code lists, offline classes, DDL,
events, numbering, workflow, file slots."""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import yaml
from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.files.slots import load_file_slots
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import load_numbering
from tl_core.workflow.loader import load_workflow
from tl_mod_engineering import registry
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards
from tl_mod_engineering.names import COMPANY
from tl_schema import generate
from tl_schema.generated.offline_classes import OFFLINE_CLASSES

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schema"
FIXTURES = SCHEMA / "fixtures"
MATERIALS = SCHEMA / "modules" / "materials"
EDITION = FIXTURES / "standards" / "co.acme.materials@1.0.0.yaml"

EXPECTED_OFFLINE = {
    "materials.ItemMaster": "none",
    "materials.ProjectItem": "none",
    "materials.InventoryLocation": "none",
    "materials.POLineRef": "none",
    "materials.MTO": "none",
    "materials.MTOLine": "none",
    "materials.Receipt": "draft_only",
    "materials.StockLot": "draft_only",
}
RECORD_TABLES = [
    "cur_materials_item_master",
    "cur_materials_project_item",
    "cur_materials_location",
    "cur_materials_po_line",
    "cur_materials_receipt",
    "cur_materials_receipt_line",
    "cur_materials_lot",
    "cur_materials_mto",
    "cur_materials_mto_line",
]
PROJECTION_TABLES = ["cur_materials_movement", "cur_materials_stock", "cur_materials_reservation"]
# Event type -> stream type, from the table of the S1 spec.
EVENTS: dict[str, str] = {
    "ItemMaster.Defined": "materials.ItemMaster",
    "ItemMaster.Revised": "materials.ItemMaster",
    "ItemMaster.Retired": "materials.ItemMaster",
    "ProjectItem.Defined": "materials.ProjectItem",
    "InventoryLocation.Defined": "materials.InventoryLocation",
    "InventoryLocation.Revised": "materials.InventoryLocation",
    "InventoryLocation.Retired": "materials.InventoryLocation",
    "POLineRef.Defined": "materials.POLineRef",
    "POLineRef.Updated": "materials.POLineRef",
    "Receipt.Defined": "materials.Receipt",
    "Receipt.Revised": "materials.Receipt",
    "Receipt.Inspected": "materials.Receipt",
    "Receipt.Accepted": "materials.Receipt",
    "Receipt.Rejected": "materials.Receipt",
    "StockLot.Defined": "materials.StockLot",
    "StockLot.Moved": "materials.StockLot",
    "MTO.Defined": "materials.MTO",
    "MTOLine.Defined": "materials.MTOLine",
    "MTOLine.Assigned": "materials.MTOLine",
}
MOVEMENT_KINDS = {
    "receive",
    "issue",
    "transfer",
    "return",
    "adjust",
    "scrap",
    "reserve",
    "unreserve",
}
CODE_LISTS: dict[str, tuple[str, Sequence[str]]] = {
    "ItemCategory": (
        "extensible",
        "pipe fitting flange valve bolting structural plate cable instrument electrical "
        "insulation paint consumable concrete other".split(),
    ),
    "LocationKind": ("closed", "project warehouse laydown toolcrib gang_box".split()),
    "ConditionCode": ("closed", "good damaged wrong_item nonconforming".split()),
    "MovementReason": (
        "extensible",
        "count_correction damaged lost found wrong_item expired other".split(),
    ),
    "StockUom": ("closed", "EA SET BOX ROLL L m kg lb m3".split()),
}


def check_offline() -> None:
    found = {k: v for k, v in OFFLINE_CLASSES.items() if k.startswith("materials.")}
    assert found == EXPECTED_OFFLINE, found
    assert OFFLINE_CLASSES["materials.StockLot"] == "draft_only"


def check_ddl() -> None:
    ddl = generate.GENERATED_DIR / "ddl"
    for dialect in ("sqlite", "postgres"):
        for table in RECORD_TABLES + PROJECTION_TABLES:
            assert (ddl / dialect / f"{table}.sql").is_file(), f"{dialect}: {table}"
    stock = (ddl / "sqlite" / "cur_materials_stock.sql").read_text(encoding="utf-8")
    for column in ("lot_id", "location_id", "on_hand", "reserved", "available"):
        assert f"\n  {column} " in stock, f"cur_materials_stock has no column {column}"
    movement = (ddl / "sqlite" / "cur_materials_movement.sql").read_text(encoding="utf-8")
    for column in ("seq", "lot_id", "kind", "qty", "uom", "direction", "from_location_id",
                   "to_location_id", "cost_code_id", "mto_line_id", "iwp_id", "requisition_id",
                   "person", "reason", "actor", "recorded_at", "correlation_id"):  # fmt: skip
        assert f"\n  {column} " in movement, f"cur_materials_movement has no column {column}"
    # The SQLite DDL is valid and creates the twelve tables (S2 writes the projectors).
    connection = sqlite3.connect(":memory:")
    try:
        for table in RECORD_TABLES + PROJECTION_TABLES:
            text_ = (ddl / "sqlite" / f"{table}.sql").read_text(encoding="utf-8")
            connection.executescript(text_)
        names = {
            r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()
    missing = [t for t in RECORD_TABLES + PROJECTION_TABLES if t not in names]
    assert not missing, f"not created by the DDL: {missing}"


def check_events() -> None:
    document = yaml.safe_load((MATERIALS / "events.yaml").read_text(encoding="utf-8"))
    by_type: dict[str, dict[str, object]] = {}
    for definition in document["classes"].values():
        annotations = definition.get("annotations") or {}
        if "tl:event_type" in annotations:
            by_type[annotations["tl:event_type"]] = definition
    assert set(by_type) == set(EVENTS), sorted(set(by_type) ^ set(EVENTS))
    for event_type, stream in EVENTS.items():
        description = " ".join(str(by_type[event_type]["description"]).split())
        assert f"Stream type `{stream}`" in description, event_type
    moved = by_type["StockLot.Moved"]["attributes"]
    assert moved["kind"]["range"] == "MovementKind"  # type: ignore[index]
    assert moved["feed_policy"]["equals_string"] == "none"  # type: ignore[index]
    assert moved["feed_policy"]["required"] is True  # type: ignore[index]
    movement = yaml.safe_load((MATERIALS / "movement.yaml").read_text(encoding="utf-8"))
    kinds = set(movement["enums"]["MovementKind"]["permissible_values"])
    assert kinds == MOVEMENT_KINDS, kinds
    index = (generate.GENERATED_DIR / "catalog" / "index.json").read_text(encoding="utf-8")
    for event_type in EVENTS:
        assert f'"event_type": "{event_type}"' in index, event_type


def check_edition() -> None:
    doc = load_standards_file(EDITION)
    assert doc.edition == "co.acme.materials@1.0.0"
    assert set(doc.code_lists) == set(CODE_LISTS)
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        with open_uow(target) as uow:
            first = load_standards(uow, doc, actor="user:seed", source="accept")
        assert first.created == len(CODE_LISTS) + sum(len(v[1]) for v in CODE_LISTS.values())
        assert first.skipped == 0
        with open_uow(target) as uow:
            second = load_standards(uow, doc, actor="user:seed", source="accept")
        assert second.created == 0 and second.skipped == first.created, second
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            events = int(conn.execute(text("SELECT COUNT(*) FROM events")).scalar_one())
            for name, (policy, codes) in CODE_LISTS.items():
                row = registry.find_standards(conn, scope=COMPANY, kind="code_list", code=name)
                assert len(row) == 1 and row[0].value_list_policy == policy, name
                values = registry.code_values(conn, COMPANY, name)
                assert [v.code for v in values] == codes, (name, [v.code for v in values])
            uom = {v.code: v.attributes for v in registry.code_values(conn, COMPANY, "StockUom")}
            assert uom["EA"] == {"ucum": "1", "dimension": "count"}, uom["EA"]
            assert all(set(a) == {"ucum", "dimension"} for a in uom.values())
        with open_uow(target) as uow:
            load_standards(uow, doc, actor="user:seed", source="accept")
        with open_uow(target, readonly=True) as uow:
            after = int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())
        assert after == events, "a third load wrote events"
    standards = (FIXTURES / "standards" / "co.acme.standards@1.0.0.yaml").read_text(
        encoding="utf-8"
    )
    assert "EA" not in {
        v["code"] for v in yaml.safe_load(standards)["code_lists"]["UnitOfMeasure"]["values"]
    }


def check_numbering() -> None:
    patterns = load_numbering(FIXTURES / "numbering" / "patterns.yaml")
    pattern = patterns.find("project:P123", "materials.Receipt")
    assert pattern is not None and pattern.type_code == "RCPT" and pattern.gap_free is True
    assert pattern.template == "{project}-{type}-{seq:4}"
    with tempfile.TemporaryDirectory() as tmp:
        target = as_target(Path(tmp) / "ledger.db")
        create_schema(target)
        keys: list[str] = []
        for _ in range(2):
            with open_uow(target) as uow:
                values = segment_values(pattern, "project:P123")
                keys.append(
                    allocate_key(
                        uow,
                        pattern=pattern,
                        scope="project:P123",
                        values=values,
                        record_id=None,
                        record_type="materials.Receipt",
                        actor="user:seed",
                        source="accept",
                    ).key
                )
    assert keys == ["P123-RCPT-0001", "P123-RCPT-0002"], keys


def check_workflow() -> None:
    definition = load_workflow(FIXTURES / "workflows" / "materials-receipt.yaml")
    assert definition.record_type == "materials.Receipt"
    assert definition.initial_state == "Received"
    assert definition.state_names() == ["Received", "Inspected", "Accepted", "Rejected", "Void"]
    moves = {(s, t.to) for t in definition.transitions for s in t.from_states}
    assert moves == {
        ("Received", "Inspected"),
        ("Inspected", "Accepted"),
        ("Inspected", "Rejected"),
        ("Received", "Rejected"),
        ("Received", "Void"),
        ("Inspected", "Void"),
    }, sorted(moves)
    assert ("Accepted", "Inspected") not in moves
    assert definition.transitions_from("Accepted") == []
    assert not [g for t in definition.transitions for g in t.guards if g.kind == "roles"]


def check_slots() -> None:
    slots = load_file_slots(FIXTURES / "files" / "materials-receipt.yaml")
    assert slots.record_types() == ["materials.Receipt"]
    listed = slots.for_type("materials.Receipt")
    assert [s.name for s in listed] == ["mtr", "certificate", "packing_slip", "photo"]
    mtr = slots.get("materials.Receipt", "mtr")
    assert mtr is not None and mtr.cardinality == "many" and mtr.max_size == 50 * 1024 * 1024
    assert set(mtr.accepted_types) == {"application/pdf", "image/*"}
    photo = slots.get("materials.Receipt", "photo")
    assert photo is not None and photo.capture_hint == "camera"
    assert not [s for s in listed if s.required_in_states]


import inspect  # noqa: E402

import pytest  # noqa: E402

_CHECKS: list[Callable[[], None]] = [
    f
    for n, f in inspect.getmembers(inspect.getmodule(check_offline), inspect.isfunction)
    if n.startswith("check_") and not inspect.signature(f).parameters
]


def test_all_seven_checks_are_collected() -> None:
    assert len(_CHECKS) == 7


@pytest.mark.parametrize("check", _CHECKS, ids=lambda f: f.__name__)
def test_materials_schema(check: Callable[[], None]) -> None:
    check()


def test_code_list_sizes() -> None:
    sizes = {name: len(codes) for name, (_, codes) in CODE_LISTS.items()}
    assert sizes == {
        "StockUom": 9,
        "ItemCategory": 15,
        "LocationKind": 5,
        "ConditionCode": 4,
        "MovementReason": 7,
    }


def test_tl_offline_classes_cover_the_eight_types() -> None:
    assert len(EXPECTED_OFFLINE) == 8
    assert {v for v in EXPECTED_OFFLINE.values()} == {"none", "draft_only"}
