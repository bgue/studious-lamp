"""Acceptance for P2-I3-T06h: the storage locations text module and the locations log.

On the S3 seed ledger. Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``)
to a temp directory. Part 1 builds the views through ``tl_mod_materials.views`` on a read-only
connection and checks ``tl_tui.location_text`` at widths 80 and 170. The seed has no leaf that
holds stock: ``L2`` holds the stock and has one child, so the stock panel is checked on ``L2`` and
the leaf check on ``GB1``. Part 2 mounts ``LocationScreen`` on ``TlApp`` over an
``EmbeddedClient`` of the copy, at 80x30 and 170x40, and saves the screenshots to
``.accept/shots/T06h-locations-<w>.svg``. Prints ``PASS <check>`` per check and exits 0; on the
first failure prints ``FAIL <check>: <detail>`` and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T06h.py
"""
# ruff: noqa
# pyright: basic, reportOptionalCall=false, reportArgumentType=false, reportAssignmentType=false
# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false

import asyncio
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
ROOT_CODE = "P123"
PARENT = "WH1"  # a warehouse with children, in the tree under the root
LOADED_STOCK = "L2"  # the seed's stock is here; it has a child, so it is not a leaf
LEAF = "GB1"  # a leaf with no stock
WIDTHS = (80, 170)
STANDALONE_DASH = re.compile(r"(^|\s)-(\s|$)")

sys.path[:0] = [str(ROOT / "packages/tl-tui/tests")]

from helpers import screen_text, settle  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mod_materials import views  # noqa: E402
from tl_mod_materials.views import LocationView, StockRowView  # noqa: E402
from tl_tui import location_text as loc  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.widgets.location_screen import LocationScreen  # noqa: E402
from tl_tui.widgets.stock_screen import StockScreen  # noqa: E402


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class Harness:
    db: Path
    locations: list[LocationView]
    stock: dict[str, list[StockRowView]]  # by location code

    def by_code(self, code: str) -> LocationView:
        return next(row for row in self.locations if row.code == code)


def no_bad_values(cells: tuple[str, ...], where: str) -> None:
    for cell in cells:
        expect("None" not in cell, f"{where}: a cell reads None: {cells!r}")
        expect(cell != "-", f"{where}: a cell is a bare dash: {cells!r}")


def hand_built(**changes: Any) -> LocationView:
    """A location with no stock and no children, as a test builds it."""
    base: dict[str, Any] = {
        "id": "01HANDBUILT",
        "code": "HB1",
        "title": "Hand built",
        "kind": "laydown",
        "parent_code": PARENT,
        "depth": 2,
        "retired": False,
        "lots": 0,
        "lines": 0,
    }
    base.update(changes)
    return LocationView(**base)


def check_seed(h: Harness) -> None:
    expect(len(h.locations) == 9, f"the seed ledger has {len(h.locations)} locations, not nine")
    root = h.locations[0]
    expect(root.code == ROOT_CODE and root.parent_code is None, f"root is {root!r}")
    expect(h.by_code(PARENT).parent_code == ROOT_CODE, f"{PARENT} is not under the root")
    expect(h.by_code("L1").parent_code == PARENT, "L1 is not under WH1")
    expect(bool(h.stock[LOADED_STOCK]), f"{LOADED_STOCK} holds no stock in the seed")
    expect(not h.stock[LEAF], f"{LEAF} holds stock")
    print("PASS seed has nine locations under P123, WH1 and L1, and stock at L2")


def check_panels(h: Harness) -> None:
    for width in WIDTHS:
        for code in (PARENT, LOADED_STOCK):
            row = h.by_code(code)
            lines = loc.location_lines(row, h.locations, h.stock[code], width=width)
            print(f"-- location panel {code} at {width} columns")
            print("\n".join(lines))
            for line in lines:
                expect(len(line) <= width, f"{width} columns: {len(line)} wide: {line!r}")
                expect("None" not in line, f"{width} columns: a line reads None: {line!r}")
                expect(
                    not STANDALONE_DASH.search(line),
                    f"{width} columns: a standalone dash in {line!r}",
                )
            expect(lines[0] == f"{code} · {row.title}", f"identity line is {lines[0]!r}")
    print("PASS location panels stay within 80 and 170 columns, no None, no bare dash")


def check_rows(h: Harness) -> None:
    for width in WIDTHS:
        columns = loc.columns_for(h.locations)
        print(f"-- first rows of the list at {width} columns, columns {columns}")
        for row in h.locations[:3]:
            cells = loc.row_cells(row, columns)
            no_bad_values(cells, "location row")
            print("  " + "  ".join(cells))
    print("PASS location rows have no None and no bare dash")


def check_summaries(h: Harness) -> None:
    l1 = h.by_code("L1")
    summary = loc.location_page(l1, h.locations, h.stock["L1"]).summary
    print(f"-- L1 summary: {summary}")
    expect(f"{ROOT_CODE} › {PARENT}" in summary, f"L1 summary has no parent path: {summary!r}")
    root = loc.location_page(h.locations[0], h.locations, h.stock[ROOT_CODE]).summary
    print(f"-- root summary: {root}")
    expect("under" not in root, f"the root summary names a parent: {root!r}")
    print("PASS L1 summary names P123 › WH1; the root summary has no under")


def check_sections(h: Harness) -> None:
    lines = [
        line.strip()
        for line in loc.location_lines(
            h.by_code(LOADED_STOCK), h.locations, h.stock[LOADED_STOCK], width=170
        )
    ]
    expect("Contents" in lines and "Children" in lines, "Contents or Children missing")
    expect(lines.index("Contents") < lines.index("Children"), "Children before Contents")
    print("PASS sections in order: Contents, Children")


def check_empty_notes(h: Harness) -> None:
    leaf = loc.location_lines(h.by_code(LEAF), h.locations, h.stock[LEAF], width=80)
    expect("No child locations" in leaf, "no 'No child locations' on a leaf")
    expect("No stock here" in leaf, "no 'No stock here' on a leaf with no stock")
    empty = loc.location_lines(hand_built(), h.locations, [], width=80)
    expect("No stock here" in empty, "no 'No stock here' on a hand-built empty location")
    expect("No child locations" in empty, "no 'No child locations' on a childless location")
    print("PASS a leaf shows No child locations; an empty location shows No stock here")


def check_indent(h: Harness) -> None:
    child = loc.row_cells(h.by_code("L1"), ("Number", "Subject"))
    parent = loc.row_cells(h.by_code(PARENT), ("Number", "Subject"))
    expect(child[1].startswith("    Laydown"), f"L1 subject not indented two levels: {child!r}")
    expect(parent[1].startswith("  Main"), f"WH1 subject not indented one level: {parent!r}")
    print("PASS a child is indented in Subject, two spaces per depth")


def check_kind_and_retired(_: Harness) -> None:
    cells = loc.row_cells(hand_built(kind="warehouse", retired=True), ("Kind", "Subject"))
    expect(cells[0] == "Warehouse", f"kind does not humanize: {cells!r}")
    expect(cells[1].endswith("(retired)"), f"a retired location has no (retired): {cells!r}")
    page = loc.location_page(hand_built(retired=True), [], [])
    expect(page.state == "Retired", f"state is {page.state!r} for a retired location")
    print("PASS Kind reads Warehouse; a retired location reads (retired) and state Retired")


def check_textual_free(_: Harness) -> None:
    code = "import tl_tui.location_text, sys; print('textual' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    expect(out == "False", f"importing tl_tui.location_text loaded textual: {out!r}")
    print("PASS importing tl_tui.location_text leaves textual out of sys.modules")


# --- part 2: the screen -----------------------------------------------------------


async def run_screen(db: Path, width: int, height: int) -> tuple[dict[str, bool], int]:
    """Mount the screen on the app at ``width`` x ``height`` and walk its keys; returns the steps
    that held and the number of locations the project lists."""
    client = EmbeddedClient(SqliteUowFactory(db), actor="user:dev")
    app = TlApp(client, scope=SCOPE, actor="user:dev")
    total = len(client.list_materials_locations(PROJECT))
    steps: dict[str, bool] = {}
    async with app.run_test(size=(width, height)) as pilot:
        await settle(pilot)
        app.push_screen(LocationScreen(client, PROJECT))
        await settle(pilot)
        steps["pushed"] = isinstance(app.screen, LocationScreen)
        text = screen_text(app)
        steps["code"] = PARENT in text
        steps["keys"] = "s stock here" in text
        steps["all"] = f"Showing {total} of {total} locations" in text
        await pilot.press("down")
        await settle(pilot)
        steps["panel"] = "Contents" in screen_text(app)
        SHOTS.mkdir(parents=True, exist_ok=True)
        svg = app.export_screenshot(title="Locations")
        (SHOTS / f"T06h-locations-{width}.svg").write_text(svg, encoding="utf-8")
        await pilot.press("s")
        await settle(pilot)
        steps["stock"] = isinstance(app.screen, StockScreen)
        steps["stock_here"] = steps["stock"] and app.screen.location == PARENT
        await pilot.press("escape")
        await settle(pilot)
        steps["returned"] = isinstance(app.screen, LocationScreen)
        await pilot.press("escape")
        await settle(pilot)
        steps["closed"] = not isinstance(app.screen, LocationScreen)
    return steps, total


SCREEN_NAMES = {
    "pushed": "the screen mounts on TlApp",
    "code": "the list shows the warehouse code",
    "keys": "the keys row shows s stock here",
    "all": "the summary reads Showing N of N locations",
    "panel": "down shows the panel with Contents",
    "stock": "s opens a StockScreen on top",
    "stock_here": "the StockScreen is for the highlighted location",
    "returned": "Esc returns to the locations",
    "closed": "Esc closes the screen",
}


def screen_checks(db: Path) -> None:
    for width, height in ((80, 30), (170, 40)):
        steps, _ = asyncio.run(run_screen(db, width, height))
        for step, label in SCREEN_NAMES.items():
            expect(steps.get(step, False), f"{width}x{height}: {label} failed")
        print(f"PASS LocationScreen at {width}x{height}: {', '.join(SCREEN_NAMES.values())}")
        print(f"PASS screenshot saved to {SHOTS / f'T06h-locations-{width}.svg'}")


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    ("seed", check_seed),
    ("panel", check_panels),
    ("rows", check_rows),
    ("summary", check_summaries),
    ("sections", check_sections),
    ("empty", check_empty_notes),
    ("indent", check_indent),
    ("kind", check_kind_and_retired),
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
            locations = views.locations_tree(conn, SCOPE)
            if not locations:
                print("FAIL seed: the seed ledger has no locations")
                return 1
            stock = {row.code: views.stock(conn, SCOPE, location=row.code) for row in locations}
        harness = Harness(db, locations, stock)
        for name, check in CHECKS:
            try:
                check(harness)
            except Failure as exc:
                print(f"FAIL {name}: {exc}")
                return 1
            except Exception as exc:  # an unexpected error is a failed check too
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
                return 1
        try:
            screen_checks(db)
        except Failure as exc:
            print(f"FAIL screen: {exc}")
            return 1
        except Exception as exc:  # an unexpected error is a failed check too
            print(f"FAIL screen: {type(exc).__name__}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
