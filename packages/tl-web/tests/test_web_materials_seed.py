"""The materials seed of the M4 twin tests (P2-WEB1-T17): ``seed_materials`` on the tl-tui materials
fake, loaded by path as ``test_web_wbs_log.py`` loads ``fakes_awp.py``.

The world has one story: every lot of the stock has a lot detail, every receipt number a receipt
detail, every take-off key a detail, every location parent is a location, and the item projects of
PIPE-6S agree with its stock. PO lines are not seeded, so that list stays empty.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
PROJECT = "P123"


def _load(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake() -> Any:
    fakes = _load("tl_web_tests_fakes_materials", "packages/tl-tui/tests/fakes_materials.py")
    seed = _load(
        "tl_web_tests_fakes_materials_seed", "packages/tl-tui/tests/fakes_materials_seed.py"
    )

    class SeededFake(fakes.FakeMaterialsSupport):
        pass

    client = SeededFake()
    client._init_materials()
    seed.seed_materials(client, PROJECT)
    return client


def test_every_list_read_returns_its_rows(fake: Any) -> None:
    assert fake.list_materials_stock(PROJECT)
    assert fake.list_materials_movements(PROJECT)
    assert fake.list_materials_receipts(PROJECT)
    assert fake.list_materials_locations(PROJECT)
    assert fake.list_materials_mto_lines(PROJECT)
    assert fake.list_materials_items()


def test_po_lines_are_the_one_pinned_empty_list(fake: Any) -> None:
    assert fake.list_materials_po_lines(PROJECT) == []


def test_item_projects_per_code(fake: Any) -> None:
    pipe = fake.list_materials_item_projects("PIPE-6S")
    assert [row.project for row in pipe] == [PROJECT, "P456"]
    assert len(fake.list_materials_item_projects("BOLT-M20")) == 1
    assert len(fake.list_materials_item_projects("WELD-E7018")) == 1
    assert fake.list_materials_item_projects("VLV-GATE-4") == []


def test_every_stock_lot_has_a_lot_detail(fake: Any) -> None:
    for row in fake.list_materials_stock(PROJECT):
        detail = fake.get_materials_lot(PROJECT, row.lot)
        assert detail.key == row.lot


def test_lot_details_quote_the_stock_rows(fake: Any) -> None:
    stock = fake.list_materials_stock(PROJECT)
    for lot in {row.lot for row in stock}:
        detail = fake.get_materials_lot(PROJECT, lot)
        assert detail.quantities == [row for row in stock if row.lot == lot]


def test_every_receipt_number_has_a_detail(fake: Any) -> None:
    for receipt in fake.list_materials_receipts(PROJECT):
        assert fake.get_materials_receipt(PROJECT, receipt.number).number == receipt.number


def test_every_mto_key_has_a_detail(fake: Any) -> None:
    for line in fake.list_materials_mto_lines(PROJECT):
        assert fake.get_materials_mto_line(PROJECT, line.key).key == line.key


def test_every_parent_code_is_a_location(fake: Any) -> None:
    codes = {loc.code for loc in fake.list_materials_locations(PROJECT)}
    parents = {loc.parent_code for loc in fake.list_materials_locations(PROJECT)} - {None}
    assert parents <= codes


def test_movement_seq_is_unique_and_one_to_six(fake: Any) -> None:
    seqs = [m.seq for m in fake.list_materials_movements(PROJECT)]
    assert len(seqs) == len(set(seqs)) == 6
    assert sorted(seqs) == [1, 2, 3, 4, 5, 6]


def test_movements_cover_kinds_directions_and_keys(fake: Any) -> None:
    moves = fake.list_materials_movements(PROJECT)
    assert {m.kind for m in moves} == {
        "receive",
        "reserve",
        "transfer",
        "issue",
        "return",
        "adjust",
    }
    assert {m.direction for m in moves} == {"in", "out", None}
    assert sum(1 for m in moves if m.work_package) >= 2
    assert sum(1 for m in moves if m.cost_code) >= 1
    assert sum(1 for m in moves if not m.work_package and not m.cost_code) >= 1
    assert all(m.recorded_at[:7] in {"2026-10", "2026-11"} for m in moves)


def test_receipts_have_the_three_states_and_the_slash_lot(fake: Any) -> None:
    receipts = fake.list_materials_receipts(PROJECT)
    assert {r.state for r in receipts} == {"Received", "Inspected", "Accepted"}
    assert [r.number for r in fake.list_materials_receipts(PROJECT, missing_mtr=True)] == [
        "RCV-0003"
    ]
    assert [r.number for r in fake.list_materials_receipts(PROJECT, open_only=True)] == [
        "RCV-0002",
        "RCV-0003",
    ]
    lots = {
        line.lot
        for number in ("RCV-0001", "RCV-0002", "RCV-0003")
        for line in fake.get_materials_receipt(PROJECT, number).line_rows
    }
    assert "BL/26-07" in lots


def test_the_stock_has_one_reserved_row_and_no_lot_heat_on_the_slash_lot(fake: Any) -> None:
    stock = fake.list_materials_stock(PROJECT)
    assert len(stock) == 4
    assert len({row.lot for row in stock}) == 3
    assert sum(1 for row in stock if row.reserved > 0) == 1
    assert {row.lot for row in stock if row.heat_no is None} == {"BL/26-07"}
    assert all(row.on_hand == row.reserved + row.available for row in stock)


def test_item_projects_agree_with_the_stock(fake: Any) -> None:
    stock = fake.list_materials_stock(PROJECT)
    for code in ("PIPE-6S", "BOLT-M20", "WELD-E7018"):
        rows = [r for r in stock if r.item_code == code]
        mine = next(p for p in fake.list_materials_item_projects(code) if p.project == PROJECT)
        assert mine.on_hand == sum(r.on_hand for r in rows)
        assert mine.reserved == sum(r.reserved for r in rows)
        assert mine.available == sum(r.available for r in rows)


def test_locations_form_the_tree_and_the_stock_counts(fake: Any) -> None:
    by_code = {loc.code: loc for loc in fake.list_materials_locations(PROJECT)}
    assert by_code["WH-A-1"].parent_code == "WH-A"
    assert by_code["WH-A-1"].depth == 2
    assert by_code["WH-A"].parent_code == "WH"
    stock = fake.list_materials_stock(PROJECT)
    for code, loc in by_code.items():
        here = [r for r in stock if r.location == code]
        assert loc.lots == len({r.lot for r in here})
        assert loc.lines == len(here)


def test_quantities_have_three_decimals(fake: Any) -> None:
    for row in fake.list_materials_stock(PROJECT):
        assert row.on_hand.as_tuple().exponent == -3
        assert row.reserved.as_tuple().exponent == -3
        assert row.available.as_tuple().exponent == -3
