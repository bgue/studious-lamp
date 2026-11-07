"""Acceptance for P2-I3-T06g: the For column and the signed receive quantities.

Part 1 is pure: hand-built ``MovementView``s (the sign by direction and by kind, the For cell, the
columns) and a hand-built lot detail whose reservation has a work package, at 80 and 170 columns.
Part 2 mounts ``StockScreen`` and ``MovementLogScreen`` on ``TlApp`` at 80x30 and 170x40 over a copy
of ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``). The seed has no reservation
or issue against a work package, so the screens read through ``WithWorkPackage``: the seed client
with one issue and one reservation against ``WP-101`` added. Prints ``PASS <check>`` for each check
and exits 0; on the first failure prints ``FAIL <check>: <detail>`` and exits 1. Run from any
directory:

    uv run python dev/accept/P2-I3/T06g.py
"""
# ruff: noqa
# pyright: basic, reportOptionalCall=false, reportArgumentType=false, reportAssignmentType=false
# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false

import asyncio
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Coroutine
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
SIZES = ((80, 30), (170, 40))
WORK_PACKAGE = "WP-101"
sys.path[:0] = [str(ROOT / "packages/tl-api/tests"), str(ROOT / "packages/tl-tui/tests")]
os.environ.setdefault("TL_ENV", "dev")  # the harness's dev token file is honoured in dev (as T04b)

from harness import ALICE  # noqa: E402
from helpers import panel_of, screen_text, settle, static_of  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mod_materials.views import (  # noqa: E402
    LotDetailView,
    MovementView,
    ReservationView,
    StockRowView,
)
from tl_tui import materials_text as mt  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.widgets.movement_screen import MovementLogScreen  # noqa: E402
from tl_tui.widgets.stock_screen import StockScreen  # noqa: E402

STANDALONE_DASH = re.compile(r"(?<!\S)-(?!\S)")
Scenario = Callable[[Any, TlApp], Coroutine[Any, Any, None]]


def check(ok: bool, name: str, detail: str = "") -> None:
    """Raise on a failed check (the first failure ends the run); print ``PASS`` otherwise."""
    if not ok:
        raise AssertionError(f"{name}: {detail}")
    print(f"PASS {name}")


def require(ok: bool, name: str, detail: str = "") -> None:
    """Like ``check`` but silent on success: for the per-line checks, which print one summary."""
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def movement(**over: Any) -> MovementView:
    """A hand-built movement; the defaults are a receipt with no direction."""
    base: dict[str, Any] = {
        "seq": 1,
        "recorded_at": "2026-10-01T09:00:00",
        "kind": "receive",
        "lot": "LOT-1",
        "heat_no": "H1",
        "item_code": "PIPE",
        "qty": Decimal("12"),
        "uom": "m",
        "direction": None,
        "from_location": None,
        "to_location": "STORE",
        "mto_line_id": None,
        "cost_code_id": None,
        "person": None,
        "reason": None,
        "actor": "user:clerk",
    }
    base.update(over)
    return MovementView(**base)


def qty_of(view: MovementView) -> str:
    return mt.movement_cells(view, ("Qty",))[0]


def check_signs() -> None:
    cases: list[tuple[str, dict[str, Any], str]] = [
        ("receive", {"kind": "receive", "qty": Decimal("12")}, "+12"),
        ("return", {"kind": "return", "qty": Decimal("3")}, "+3"),
        ("issue", {"kind": "issue", "qty": Decimal("5")}, "-5"),
        ("scrap", {"kind": "scrap", "qty": Decimal("2")}, "-2"),
        ("transfer", {"kind": "transfer", "qty": Decimal("7")}, "7"),
        ("reserve", {"kind": "reserve", "qty": Decimal("4")}, "4"),
        ("unreserve", {"kind": "unreserve", "qty": Decimal("1")}, "1"),
        ("adjust", {"kind": "adjust", "qty": Decimal("6")}, "6"),
        ("issue out", {"kind": "issue", "direction": "out", "qty": Decimal("6")}, "-6"),
        ("receive in", {"kind": "receive", "direction": "in", "qty": Decimal("9")}, "+9"),
        ("zero receive", {"kind": "receive", "qty": Decimal("0")}, "0"),
        ("zero issue", {"kind": "issue", "qty": Decimal("0")}, "0"),
    ]
    for label, over, want in cases:
        got = qty_of(movement(**over))
        check(got == want, f"sign {label}: {want}", f"got {got!r}")
    print("PASS signed quantities follow direction, then kind; zero stays 0")


def check_for_cell() -> None:
    wp_and_cc = movement(work_package="WP-7", cost_code="CC-2")
    check(mt.movement_cells(wp_and_cc, ("For",)) == ("WP-7",), "For is the work package")
    cc_only = movement(work_package=None, cost_code="CC-2")
    check(mt.movement_cells(cc_only, ("For",)) == ("CC-2",), "For falls back to the cost code")
    neither = movement()
    check(mt.movement_cells(neither, ("For",)) == ("—",), "For with neither is —")


def check_columns() -> None:
    order = mt.MOVEMENT_COLUMNS
    check(
        order == ("Date", "Kind", "Lot", "Item", "Qty", "For", "From", "To", "By"),
        "MOVEMENT_COLUMNS has For after Qty",
        str(order),
    )
    check(mt.MOVEMENT_DROP[-1] == "For", "MOVEMENT_DROP ends with For", str(mt.MOVEMENT_DROP))
    same = [movement(seq=1, work_package="WP-1"), movement(seq=2, work_package="WP-1")]
    check("For" not in mt.movement_columns_for(same), "For dropped when all rows share it")
    empty = [movement(seq=1), movement(seq=2)]
    check("For" not in mt.movement_columns_for(empty), "For dropped when all rows are empty")
    by_wp = [movement(seq=1, work_package="WP-1"), movement(seq=2, work_package="WP-2")]
    check("For" in mt.movement_columns_for(by_wp), "For kept when the rows differ")
    by_cc = [movement(seq=1, cost_code="CC-1"), movement(seq=2, work_package="CC-1")]
    check("For" not in mt.movement_columns_for(by_cc), "For is the same work package or code")


def lot_detail_with(reservations: list[ReservationView]) -> LotDetailView:
    stock = StockRowView(
        lot="LOT-1",
        heat_no="H1",
        item_code="PIPE",
        item_title="Pipe 40 mm",
        location="STORE",
        location_title="Store",
        on_hand=Decimal("20"),
        reserved=Decimal("10"),
        available=Decimal("10"),
        uom="m",
    )
    return LotDetailView(
        id="lot-1",
        key="LOT-1",
        heat_no="H1",
        item_code="PIPE",
        item_title="Pipe 40 mm",
        uom="m",
        issued_net=Decimal("0"),
        receipt="RCPT-1",
        receipt_line=1,
        po_line="PO-1",
        quantities=[stock],
        reservations=reservations,
        movements=[],
    )


def check_lot_reservations() -> None:
    reserved = [
        ReservationView(
            mto_line="MTO-1", location="STORE", qty=Decimal("4"), work_package=WORK_PACKAGE
        ),
        ReservationView(mto_line="MTO-2", location="STORE", qty=Decimal("2"), work_package=None),
    ]
    detail = lot_detail_with(reserved)
    for width in (80, 170):
        lines = mt.lot_lines(detail, width=width)
        for line in lines:
            require(len(line) <= width, f"lot panel {width}: line within width", repr(line))
            require("None" not in line, f"lot panel {width}: no None", repr(line))
            require(
                STANDALONE_DASH.search(line) is None, f"lot panel {width}: no bare dash", repr(line)
            )
        header = next((line for line in lines if "MTO line" in line), "")
        check("For" in header, f"lot panel {width}: Reservations header has For", repr(header))
        first = next((line for line in lines if "MTO-1" in line), "")
        check(WORK_PACKAGE in first, f"lot panel {width}: the work package is shown", repr(first))
        second = next((line for line in lines if "MTO-2" in line), "")
        check("—" in second, f"lot panel {width}: no work package reads —", repr(second))
    print("PASS a reservation shows its work package, or — when none, at 80 and 170 columns")


def check_part_one() -> None:
    check_signs()
    check_for_cell()
    check_columns()
    check_lot_reservations()


class WithWorkPackage(EmbeddedClient):
    """The seed client plus one issue against ``WORK_PACKAGE`` and a reservation for it.

    The seed has neither, so the For column and the reservation For can only show through here.
    """

    def __init__(self, uow_factory: SqliteUowFactory, *, actor: str, first: StockRowView) -> None:
        super().__init__(uow_factory, actor=actor)
        self.first = first

    def list_materials_movements(self, project: str, **kwargs: Any) -> list[MovementView]:
        rows = super().list_materials_movements(project, **kwargs)
        issue = movement(
            seq=999,
            recorded_at="2026-10-30T09:00:00",
            kind="issue",
            lot=self.first.lot,
            heat_no=self.first.heat_no,
            item_code=self.first.item_code,
            qty=Decimal("3"),
            direction="out",
            from_location=self.first.location,
            to_location=None,
            mto_line=None,
            work_package=WORK_PACKAGE,
            actor="user:clerk",
        )
        return [*rows, issue]

    def get_materials_lot(self, project: str, key: str) -> LotDetailView:
        detail = super().get_materials_lot(project, key)
        reserved = ReservationView(
            mto_line="MTO-7",
            location=self.first.location,
            qty=Decimal("4"),
            work_package=WORK_PACKAGE,
        )
        return detail.model_copy(update={"reservations": [reserved]})


def run_at(size: tuple[int, int], client: Any, scenario: Scenario) -> None:
    """Run ``scenario(pilot, app)`` on a ``TlApp`` headless at ``size``."""

    async def main() -> None:
        app = TlApp(client, scope=f"project:{PROJECT}", actor=ALICE, is_admin=False)
        async with app.run_test(size=size) as pilot:
            await settle(pilot)
            await scenario(pilot, app)

    asyncio.run(main())


def save_shot(app: TlApp, title: str, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    (SHOTS / name).write_text(app.export_screenshot(title=title))


def header_row(text: str, *words: str) -> str:
    """The first screen line that holds every word (the table header)."""
    return next((line for line in text.splitlines() if all(w in line for w in words)), "")


def stock_at(size: tuple[int, int], client: WithWorkPackage) -> None:
    w = size[0]

    async def scenario(pilot: Any, app: TlApp) -> None:
        app.push_screen(StockScreen(client, PROJECT))
        await settle(pilot)
        screen = app.screen
        check(isinstance(screen, StockScreen), f"stock {w}: top screen", type(screen).__name__)
        await pilot.press("down")
        await settle(pilot)
        panel = panel_of(screen)
        check("Reservations" in panel, f"stock {w}: panel has Reservations", panel[:200])
        check("For" in panel, f"stock {w}: the reservation table has For", panel[:400])
        check(WORK_PACKAGE in panel, f"stock {w}: the panel shows the work package", panel[:400])
        check(STANDALONE_DASH.search(panel) is None, f"stock {w}: no bare dash", panel[:400])
        save_shot(app, "Stock", f"T06g-stock-{w}.svg")
        print(f"PASS stock {w}: screenshot saved")
        await pilot.press("escape")
        await settle(pilot)
        check(not isinstance(app.screen, StockScreen), f"stock {w}: Esc closes", "")

    run_at(size, client, scenario)


def movements_at(size: tuple[int, int], client: WithWorkPackage) -> None:
    w = size[0]

    async def scenario(pilot: Any, app: TlApp) -> None:
        app.push_screen(MovementLogScreen(client, PROJECT))
        await settle(pilot)
        screen = app.screen
        check(isinstance(screen, MovementLogScreen), f"movements {w}: top screen", "")
        text = screen_text(app)
        check("+12" in text, f"movements {w}: a receipt shows +12", "no +12 on the screen")
        status = static_of(screen, "#log-status")
        check("Showing 3 of 3 movements" in status, f"movements {w}: three rows", status)
        if w == 170:
            header = header_row(text, "Date", "Kind", "For")
            check(bool(header), f"movements {w}: the header has For", "")
            check(WORK_PACKAGE in text, f"movements {w}: the For cell shows the work package", "")
        panel = panel_of(screen)
        check("Qty" in panel, f"movements {w}: panel has Qty", panel[:200])
        save_shot(app, "Movements", f"T06g-movements-{w}.svg")
        print(f"PASS movements {w}: screenshot saved")
        await pilot.press("escape")
        await settle(pilot)
        check(not isinstance(app.screen, MovementLogScreen), f"movements {w}: Esc closes", "")

    run_at(size, client, scenario)


def part_two() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, Path(tmp) / ("tl.db" + src.name[len(LEDGER.name) :]))
        base = EmbeddedClient(SqliteUowFactory(db), actor=ALICE)
        rows = base.list_materials_stock(PROJECT, limit=1000)
        if not rows:
            print("FAIL seed: the seed ledger has no stock rows for P123")
            return 1
        client = WithWorkPackage(SqliteUowFactory(db), actor=ALICE, first=rows[0])
        for size in SIZES:
            stock_at(size, client)
            movements_at(size, client)
    return 0


def main() -> int:
    try:
        check_part_one()
        return part_two()
    except AssertionError as exc:
        print(f"FAIL {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
