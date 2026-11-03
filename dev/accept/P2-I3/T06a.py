"""Acceptance for P2-I3-T06a: the materials text helpers, stock log, lot panel and movement log.

On the S3 seed ledger.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory and
builds the views through ``tl_mod_materials.views`` on a read-only connection. Prints the lot panel
at widths 80 and 170, the first three stock and movement rows, and ``PASS <check>`` per check. On
the first failure it prints ``FAIL <check>: <detail>`` and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T06a.py
"""

import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tl_adapters.db import as_target, open_uow
from tl_mod_materials import views
from tl_mod_materials.names import MOVEMENT_KINDS
from tl_mod_materials.views import MovementView, StockRowView
from tl_tui import materials_text as mt

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SCOPE = "project:P123"
LOT = "P123-RCPT-0001@1"
MTR = "mtr.pdf"
WIDTHS = (80, 170)
STANDALONE_DASH = re.compile(r"(^|\s)-(\s|$)")


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class Harness:
    conn: object
    stock: list[StockRowView]
    movements: list[MovementView]
    detail: views.LotDetailView
    row: StockRowView


def no_bad_values(cells: tuple[str, ...], where: str) -> None:
    for cell in cells:
        expect("None" not in cell, f"{where}: a cell reads None: {cells!r}")
        expect(cell != "-", f"{where}: a cell is a bare dash: {cells!r}")


def check_panel_within_width(h: Harness) -> None:
    for width in WIDTHS:
        lines = mt.lot_lines(h.detail, h.row, mtr=MTR, width=width)
        print(f"-- lot panel at {width} columns")
        print("\n".join(lines))
        for line in lines:
            expect(len(line) <= width, f"{width} columns: line is {len(line)} wide: {line!r}")
            expect("None" not in line, f"{width} columns: a line reads None: {line!r}")
            expect(
                not STANDALONE_DASH.search(line),
                f"{width} columns: a standalone dash in {line!r}",
            )
        expect(lines[0].startswith(h.detail.heat_no or h.detail.key), "identity line missing")
        expect(
            any(line.startswith(f"Lot {LOT} · receipt ") for line in lines),
            f"{width} columns: no lot line for {LOT!r}",
        )
    print("PASS lot panel lines stay within 80 and 170 columns, no None, no bare dash")


def check_rows_as_cells(h: Harness) -> None:
    columns = mt.stock_columns_for(h.stock)
    print(f"-- first three stock rows, columns {columns}")
    for row in h.stock[:3]:
        cells = mt.stock_cells(row, columns)
        no_bad_values(cells, "stock row")
        print("  " + "  ".join(cells))
    print("-- first three movement rows, columns " + str(mt.movement_columns_for(h.movements)))
    cols = mt.movement_columns_for(h.movements)
    for move in h.movements[:3]:
        cells = mt.movement_cells(move, cols)
        no_bad_values(cells, "movement row")
        print("  " + "  ".join(cells))
    expect(bool(h.stock) and bool(h.movements), "the seed ledger has no stock or no movements")
    print("PASS stock and movement rows have no None and no bare dash")


def check_empty_is_dash(h: Harness) -> None:
    lines = mt.lot_lines(h.detail, h.row, mtr=None, width=80)
    expect(
        any(line.startswith("MTR") and line.endswith("—") for line in lines),
        "an absent MTR does not read —",
    )
    blank = StockRowView(
        lot="X",
        heat_no=None,
        item_code="I",
        item_title="Item",
        location="L",
        location_title="Store",
        on_hand=Decimal("1"),
        reserved=Decimal("0"),
        available=Decimal("1"),
        uom="m",
    )
    expect(mt.stock_cells(blank, ("Lot",))[0] == "X", "stock Lot is not the lot key")
    no_origin = MovementView(
        seq=2,
        recorded_at="2026-10-02T09:00:00",
        kind="receive",
        lot=LOT,
        heat_no=None,
        item_code="PIPE",
        qty=Decimal("0"),
        uom="m",
        direction=None,
        from_location=None,
        to_location=None,
        mto_line_id=None,
        cost_code_id=None,
        person=None,
        reason=None,
        actor="svc:erp",
    )
    cells = mt.movement_cells(no_origin, ("From", "To", "Qty", "By"))
    expect(cells[:2] == ("—", "—"), f"absent locations do not read —: {cells!r}")
    expect(cells[2] == "0", f"zero quantity is not 0: {cells!r}")
    print("PASS an absent value reads — (MTR in the panel, empty From and To in a movement)")


def check_columns_for(h: Harness) -> None:
    one = StockRowView(**{**h.row.model_dump(), "uom": "m"})
    two = StockRowView(**{**h.row.model_dump(), "uom": "kg"})
    expect("UOM" not in mt.stock_columns_for([one, one]), "UOM kept for one UOM")
    expect("UOM" in mt.stock_columns_for([one, two]), "UOM dropped for two UOMs")
    expect(mt.stock_columns_for([one, two])[-1] == "UOM", "UOM is not the last column")
    print("PASS stock_columns_for drops UOM when constant and keeps it for two UOMs")


def check_reservations_none(h: Harness) -> None:
    for stock_row in h.stock:
        detail = views.lot_detail(h.conn, SCOPE, stock_row.lot)
        if not detail.reservations:
            lines = mt.lot_lines(detail, stock_row, width=80)
            expect("Reservations" in lines, f"{stock_row.lot}: no Reservations section")
            expect("No reservations" in lines, f"{stock_row.lot}: no 'No reservations' note")
            print(f"PASS a lot with no reservations ({stock_row.lot}) shows No reservations")
            return
    raise Failure("no lot in the seed ledger has no reservations")


def check_qty_text(_: Harness) -> None:
    expect(mt.qty_text(Decimal("1234567.5000")) == "1 234 567.5", "grouping or trailing zeros")
    expect(mt.qty_text(Decimal("0.000")) == "0", "zero is not 0")
    expect(mt.qty_text(Decimal("-1234.250")) == "-1 234.25", "negative quantity")
    decimals = mt.qty_text(Decimal("0.12345")).partition(".")[2]
    expect(len(decimals) <= 3, f"more than three decimals: {mt.qty_text(Decimal('0.12345'))}")
    print("PASS qty_text groups, drops trailing zeros, keeps at most three decimals")


def check_periods(_: Harness) -> None:
    expect(
        mt.period_range("30 days", "2026-11-02") == ("2026-10-04", "2026-11-02"),
        "30 days range",
    )
    expect(mt.period_range("this month", "2026-11-02") == ("2026-11-01", "2026-11-02"), "month")
    expect(mt.period_range("all", "2026-11-02") == (None, None), "all has bounds")
    expect(mt.next_period("this month") == "all", "period does not wrap")
    print("PASS period_range and next_period")


def check_next_kind(_: Harness) -> None:
    kinds = list(mt.KIND_WORDS)
    seen: list[str | None] = [None]
    current: str | None = None
    for _ in range(len(kinds) + 1):
        current = mt.next_kind(current, kinds)
        seen.append(current)
    expect(seen[1] == kinds[0], "first kind after all is not the first kind")
    expect(seen[-1] is None and seen[-2] == kinds[-1], "the cycle does not return to all")
    print("PASS next_kind cycles through the kinds and returns None after the last")


def check_receipt_sign(_: Harness) -> None:
    expect(set(mt.KIND_WORDS) == set(MOVEMENT_KINDS), "KIND_WORDS keys are not the ledger kinds")
    expect("receipt" not in mt.KIND_WORDS, "KIND_WORDS keys receipt, which the ledger never stores")
    receipt = MovementView(
        seq=1,
        recorded_at="2026-10-01T09:00:00",
        kind="receive",
        lot=LOT,
        heat_no=None,
        item_code="PIPE",
        qty=Decimal("12"),
        uom="m",
        direction="in",
        from_location=None,
        to_location="STORE",
        mto_line_id=None,
        cost_code_id=None,
        person=None,
        reason=None,
        actor="user:clerk",
    )
    cells = mt.movement_cells(receipt, mt.MOVEMENT_COLUMNS)
    expect("+12" in cells, f"a receipt in does not show +: {cells!r}")
    expect("Receipt" in cells and "clerk" in cells, f"kind or actor: {cells!r}")
    print("PASS a receipt with direction in shows +12 and the kind Receipt")


def check_textual_free(_: Harness) -> None:
    code = "import tl_tui.materials_text, sys; print('textual' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    expect(out == "False", f"importing tl_tui.materials_text loaded textual: {out!r}")
    print("PASS importing tl_tui.materials_text leaves textual out of sys.modules")


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    ("panel", check_panel_within_width),
    ("rows", check_rows_as_cells),
    ("empty", check_empty_is_dash),
    ("columns", check_columns_for),
    ("reservations", check_reservations_none),
    ("qty", check_qty_text),
    ("periods", check_periods),
    ("kinds", check_next_kind),
    ("receipt", check_receipt_sign),
    ("import", check_textual_free),
]


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, root / ("tl.db" + src.name[len(LEDGER.name) :]))
        with open_uow(as_target(db), readonly=True) as uow:
            conn = uow.conn()
            stock = views.stock(conn, SCOPE)
            movements = views.movements(conn, SCOPE)
            detail = views.lot_detail(conn, SCOPE, LOT)
            row = next((r for r in stock if r.lot == LOT), None)
            if row is None:
                print(f"FAIL seed: lot {LOT} has no stock row")
                return 1
            harness = Harness(conn, stock, movements, detail, row)
            for name, check in CHECKS:
                try:
                    check(harness)
                except Failure as exc:
                    print(f"FAIL {name}: {exc}")
                    return 1
                except Exception as exc:  # an unexpected error is a failed check too
                    print(f"FAIL {name}: {type(exc).__name__}: {exc}")
                    return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
