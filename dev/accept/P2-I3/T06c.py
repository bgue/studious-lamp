"""Acceptance for P2-I3-T06c: the item library text module and the item library log.

On the S3 seed ledger. Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to
a temp directory. Part 1 builds the item views through ``tl_mod_materials.views`` and
``views_detail`` on a read-only connection and checks ``tl_tui.item_text`` at widths 80 and 170.
Part 2 mounts ``ItemLibraryScreen`` on ``TlApp`` over an ``EmbeddedClient`` of the copy, company
level at 80x30 and 170x40 and for project P123 at 170x40, and saves the screenshots to
``.accept/shots/T06c-items-<w>.svg`` and ``.accept/shots/T06c-items-P123-170.svg``. Prints
``PASS <check>`` per check and exits 0; on the first failure prints ``FAIL <check>: <detail>`` and
exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T06c.py
"""

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

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
WIDTHS = (80, 170)
SEED_ITEMS = 50
SECTIONS = ("Specification", "Projects")
STANDALONE_DASH = re.compile(r"(^|\s)-(\s|$)")
ITEM_KEYS_IN_CELLS = ("r state", "/ filter")

sys.path[:0] = [str(ROOT / "packages/tl-tui/tests")]

from helpers import screen_text, settle  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mod_materials import views  # noqa: E402
from tl_mod_materials import views_detail as detail_views  # noqa: E402
from tl_mod_materials.views import MaterialItemView  # noqa: E402
from tl_tui import item_text as items  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.widgets.item_library import ItemLibraryScreen  # noqa: E402


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class Harness:
    db: Path
    items: list[MaterialItemView]
    projects: list[detail_views.ItemProjectView]


def no_bad_values(cells: tuple[str, ...], where: str) -> None:
    for cell in cells:
        expect("None" not in cell, f"{where}: a cell reads None: {cells!r}")
        expect(cell != "-", f"{where}: a cell is a bare dash: {cells!r}")


def hand_built(**changes: Any) -> MaterialItemView:
    """An item with no size, rating or material, as a test builds it."""
    base: dict[str, Any] = {
        "id": "01HANDBUILT",
        "code": "PIPE-9",
        "title": "Pipe 9 in",
        "category": "pipe",
        "base_uom": "m",
        "size_text": None,
        "rating_text": None,
        "material_code": None,
        "consumable": False,
        "retired": False,
        "projects": 0,
    }
    base.update(changes)
    return MaterialItemView(**base)


def check_seed_has_items(h: Harness) -> None:
    count = len(h.items)
    expect(count == SEED_ITEMS, f"the seed ledger has {count} items, not {SEED_ITEMS}")
    print(f"PASS seed ledger has {SEED_ITEMS} items")


def check_panel_within_width(h: Harness) -> None:
    first = h.items[0]
    for width in WIDTHS:
        lines = items.item_lines(first, h.projects, width=width)
        print(f"-- item panel at {width} columns")
        print("\n".join(lines))
        for line in lines:
            expect(len(line) <= width, f"{width} columns: line is {len(line)} wide: {line!r}")
            expect("None" not in line, f"{width} columns: a line reads None: {line!r}")
            expect(
                not STANDALONE_DASH.search(line),
                f"{width} columns: a standalone dash in {line!r}",
            )
        expect(
            lines[0] == f"{first.code} · {first.title}",
            f"identity line is {lines[0]!r}",
        )
    print("PASS item panel lines stay within 80 and 170 columns, no None, no bare dash")


def check_rows_as_cells(h: Harness) -> None:
    for width in WIDTHS:
        columns = items.columns_for(h.items)
        print(f"-- first rows of the library at {width} columns, columns {columns}")
        for item in h.items[:3]:
            cells = items.row_cells(item, columns)
            no_bad_values(cells, "item row")
            print("  " + "  ".join(cells))
    print("PASS item rows have no None and no bare dash")


def check_sections_order(h: Harness) -> None:
    lines = [line.strip() for line in items.item_lines(h.items[0], h.projects, width=170)]
    found = [lines.index(name) for name in SECTIONS if name in lines]
    expect(len(found) == len(SECTIONS), f"a section is missing: {SECTIONS!r}")
    expect(found == sorted(found), f"sections are out of order: {found!r}")
    print("PASS sections in order: Specification, Projects")


def check_empty_values_and_note(_: Harness) -> None:
    lines = items.item_lines(hand_built(), [], width=80)
    size = next((x for x in lines if x.startswith("Size")), "")
    expect(size.split() == ["Size", "—"], f"an empty Size does not read —: {size!r}")
    expect("Not used in any project" in lines, "no 'Not used in any project' note")
    expect(not any(STANDALONE_DASH.search(x) for x in lines), "a standalone dash in the panel")
    print("PASS an empty Size reads — and an item with no projects shows the note")


def check_consumable(h: Harness) -> None:
    for item in (hand_built(consumable=True), hand_built(consumable=False), h.items[0]):
        lines = [x.strip() for x in items.item_lines(item, [], width=80)]
        consumable = next((x for x in lines if x.startswith("Consumable")), "")
        expect(
            consumable.split()[-1] in ("Yes", "No"),
            f"Consumable does not read Yes or No: {consumable!r}",
        )
    print("PASS Consumable reads Yes or No")


def check_columns_for(h: Harness) -> None:
    active = [hand_built(), hand_built(code="PIPE-10")]
    expect("State" not in items.columns_for(active), "State kept when no item is retired")
    expect(
        items.columns_for(active)[:2] == ("Number", "Subject"),
        f"Number and Subject do not lead: {items.columns_for(active)!r}",
    )
    mixed = [hand_built(), hand_built(code="PIPE-10", retired=True)]
    expect("State" in items.columns_for(mixed), "State dropped with a retired item")
    if not any(item.retired for item in h.items):
        expect("State" not in items.columns_for(h.items), "State kept for an all-active seed")
    print("PASS columns_for drops State when no item is retired and keeps it when one is")


def check_next_state(_: Harness) -> None:
    cycle = [None]
    for _ in range(3):
        cycle.append(items.next_state(cycle[-1]))
    expect(
        cycle == [None, "Active", "Retired", None],
        f"next_state cycles {cycle!r}, not None, Active, Retired, None",
    )
    print("PASS next_state cycles None, Active, Retired, None")


def check_textual_free(_: Harness) -> None:
    code = "import tl_tui.item_text, sys; print('textual' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    expect(out == "False", f"importing tl_tui.item_text loaded textual: {out!r}")
    print("PASS importing tl_tui.item_text leaves textual out of sys.modules")


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    ("seed", check_seed_has_items),
    ("panel", check_panel_within_width),
    ("rows", check_rows_as_cells),
    ("sections", check_sections_order),
    ("empty", check_empty_values_and_note),
    ("consumable", check_consumable),
    ("columns", check_columns_for),
    ("state", check_next_state),
    ("import", check_textual_free),
]


# --- part 2: the screen -----------------------------------------------------------


async def run_screen(
    db: Path, width: int, height: int, project: str | None, shot: str
) -> dict[str, bool]:
    """Mount the screen on the app at ``width`` x ``height`` and walk its keys; returns the steps
    that held. Saves the screenshot named ``shot`` after the panel shows."""
    client = EmbeddedClient(SqliteUowFactory(db), actor="user:dev")
    app = TlApp(client, scope=SCOPE, actor="user:dev")
    listed = client.list_materials_items(project=project)
    codes = [item.code for item in listed]
    total = len(listed)
    steps: dict[str, bool] = {}
    async with app.run_test(size=(width, height)) as pilot:
        await settle(pilot)
        app.push_screen(ItemLibraryScreen(client, project))
        await settle(pilot)
        steps["pushed"] = isinstance(app.screen, ItemLibraryScreen)
        text = screen_text(app)
        steps["code"] = any(code in text for code in codes[:5])
        steps["keys"] = all(cell in text for cell in ITEM_KEYS_IN_CELLS)
        steps["all"] = f"Showing {total} of {total} items" in text
        await pilot.press("down")
        await settle(pilot)
        steps["panel"] = "Specification" in screen_text(app)
        SHOTS.mkdir(parents=True, exist_ok=True)
        svg = app.export_screenshot(title="Items")
        (SHOTS / shot).write_text(svg, encoding="utf-8")
        await pilot.press("r")
        await settle(pilot)
        steps["active"] = "· Active" in screen_text(app)
        await pilot.press("escape")
        await settle(pilot)
        steps["closed"] = not isinstance(app.screen, ItemLibraryScreen)
    return steps


SCREEN_NAMES = {
    "pushed": "the screen mounts on TlApp",
    "code": "the table shows an item code",
    "keys": "the keys row shows r state and / filter",
    "all": "the summary reads Showing N of N items",
    "panel": "down shows the panel with Specification",
    "active": "r changes the summary to name Active",
    "closed": "Esc closes the screen",
}


def screen_checks(db: Path) -> None:
    runs = [
        (80, 30, None, "T06c-items-80.svg"),
        (170, 40, None, "T06c-items-170.svg"),
        (170, 40, PROJECT, "T06c-items-P123-170.svg"),
    ]
    for width, height, project, shot in runs:
        where = f"{width}x{height}{' project ' + project if project else ''}"
        steps = asyncio.run(run_screen(db, width, height, project, shot))
        for step, label in SCREEN_NAMES.items():
            expect(steps.get(step, False), f"{where}: {label} failed")
        print(f"PASS ItemLibraryScreen at {where}: {', '.join(SCREEN_NAMES.values())}")
        print(f"PASS screenshot saved to {SHOTS / shot}")


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
            listed = views.items(conn)
            if not listed:
                print("FAIL seed: the seed ledger has no items")
                return 1
            projects = detail_views.item_projects(conn, listed[0].code)
        harness = Harness(db, listed, projects)
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
