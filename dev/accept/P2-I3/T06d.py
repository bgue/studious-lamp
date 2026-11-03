"""Acceptance for P2-I3-T06d: the MTO lines text module and the MTO lines log.

On the S3 seed ledger. Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to
a temp directory. Part 1 builds the views through ``tl_mod_materials.views`` and ``views_detail`` on
a read-only connection and checks ``tl_tui.mto_text`` at widths 80 and 170. Part 2 mounts
``MtoLinesScreen`` on ``TlApp`` over an ``EmbeddedClient`` of the copy, at 80x30 and 170x40, and
saves the screenshots to ``.accept/shots/T06d-mto-<w>.svg``. Prints ``PASS <check>`` per check and
exits 0; on the first failure prints ``FAIL <check>: <detail>`` and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T06d.py
"""

import asyncio
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DOCUMENT_MTO = "ISO-1234@A/MTO"
WORK_PACKAGE = "P123-CWP-PIP-0001"
WIDTHS = (80, 170)
SECTIONS = ("Source", "Coverage", "Reservations", "Open receipts")
STANDALONE_DASH = re.compile(r"(^|\s)-(\s|$)")

sys.path[:0] = [str(ROOT / "packages/tl-tui/tests")]

from helpers import screen_text, settle  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mod_materials import views  # noqa: E402
from tl_mod_materials import views_detail as detail_views  # noqa: E402
from tl_mod_materials.views import MtoLineView  # noqa: E402
from tl_tui import materials_text as mt  # noqa: E402
from tl_tui import mto_text as mto  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.widgets.mto_screen import MtoLinesScreen  # noqa: E402


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class Harness:
    db: Path
    lines: list[MtoLineView]
    detail: detail_views.MtoLineDetailView


def no_bad_values(cells: tuple[str, ...], where: str) -> None:
    for cell in cells:
        expect("None" not in cell, f"{where}: a cell reads None: {cells!r}")
        expect(cell != "-", f"{where}: a cell is a bare dash: {cells!r}")


def hand_built(**changes: Any) -> detail_views.MtoLineDetailView:
    """A line with no reservations and no receipts, as a test builds it."""
    base: dict[str, Any] = {
        "id": "01HANDBUILT",
        "key": "ISO-9999@B/MTO/001",
        "mto": "ISO-9999@B/MTO",
        "line_no": 1,
        "item_code": "PIPE",
        "item_title": "Pipe 2 in",
        "uom": "m",
        "required": Decimal("5"),
        "reserved": Decimal("5"),
        "issued": Decimal("0"),
        "short": Decimal("0"),
        "work_package": None,
        "work_package_id": None,
        "need_by": None,
        "reservations": [],
        "open_receipts": [],
    }
    base.update(changes)
    return detail_views.MtoLineDetailView(**base)


def check_seed_has_lines(h: Harness) -> None:
    expect(len(h.lines) == 3, f"the seed ledger has {len(h.lines)} MTO lines, not three")
    expect(
        all(line.work_package == WORK_PACKAGE for line in h.lines),
        "a seed line is not in the work package",
    )
    print(f"PASS seed ledger has three MTO lines in {WORK_PACKAGE}")


def check_panel_within_width(h: Harness) -> None:
    for width in WIDTHS:
        lines = mto.mto_lines(h.detail, width=width)
        print(f"-- MTO line panel at {width} columns")
        print("\n".join(lines))
        for line in lines:
            expect(len(line) <= width, f"{width} columns: line is {len(line)} wide: {line!r}")
            expect("None" not in line, f"{width} columns: a line reads None: {line!r}")
            expect(
                not STANDALONE_DASH.search(line),
                f"{width} columns: a standalone dash in {line!r}",
            )
        expect(
            lines[0] == f"{h.detail.key} · {h.detail.item_title}",
            f"identity line is {lines[0]!r}",
        )
    print("PASS MTO line panel lines stay within 80 and 170 columns, no None, no bare dash")


def check_rows_as_cells(h: Harness) -> None:
    for width in WIDTHS:
        columns = mto.columns_for(h.lines)
        print(f"-- first rows of the log at {width} columns, columns {columns}")
        for line in h.lines[:3]:
            cells = mto.row_cells(line, columns)
            no_bad_values(cells, "MTO row")
            print("  " + "  ".join(cells))
    expect(bool(h.lines), "the seed ledger has no MTO lines")
    print("PASS MTO rows have no None and no bare dash")


def check_sections_order(h: Harness) -> None:
    lines = [line.strip() for line in mto.mto_lines(h.detail, width=170)]
    found = [lines.index(name) for name in SECTIONS if name in lines]
    expect(len(found) == len(SECTIONS), f"a section is missing: {SECTIONS!r}")
    expect(found == sorted(found), f"sections are out of order: {found!r}")
    print("PASS sections in order: Source, Coverage, Reservations, Open receipts")


def check_source_parsed(h: Harness) -> None:
    lines = [line.strip() for line in mto.mto_lines(h.detail, width=170)]
    document = next((x for x in lines if x.startswith("Document")), "")
    revision = next((x for x in lines if x.startswith("Revision")), "")
    expect(document.split() == ["Document", "ISO-1234"], f"document not parsed: {document!r}")
    expect(revision.split() == ["Revision", "A"], f"revision not parsed: {revision!r}")
    print("PASS Document ISO-1234 and Revision A parsed from the line key")


def check_state(h: Harness) -> None:
    short = next((line for line in h.lines if line.short > 0), None)
    expect(short is not None, "the seed ledger has no short MTO line")
    detail = detail_for(h.db, short.key)
    page = mto.mto_page(detail)
    expect(
        page.state == f"Short {mt.qty_text(detail.short)} {detail.uom}",
        f"state {page.state!r} for short {detail.short} {detail.uom}",
    )
    covered = hand_built(short=Decimal("0"))
    expect(mto.mto_page(covered).state == "Covered", "a line with short 0 is not Covered")
    print(f"PASS state reads {page.state!r} for a short line and Covered for short 0")


def check_empty_sections(_: Harness) -> None:
    lines = mto.mto_lines(hand_built(), width=80)
    expect("No reservations" in lines, "no 'No reservations' note")
    expect("No open receipts" in lines, "no 'No open receipts' note")
    expect(any("—" in x for x in lines), "an empty value does not read —")
    expect(not any(STANDALONE_DASH.search(x) for x in lines), "a standalone dash in the panel")
    print("PASS a line with no reservations and no receipts shows both notes")


def check_columns_for(h: Harness) -> None:
    same = [h.lines[0], h.lines[0]]
    expect("For" not in mto.columns_for(same), "For kept for one work package")
    other = hand_built(work_package="P123-CWP-OTHER")
    row_none = MtoLineView(**{**h.lines[0].model_dump(), "work_package": None})
    expect("For" in mto.columns_for([h.lines[0], other]), "For dropped for two work packages")
    expect(
        mto.row_cells(row_none, ("Number", "For"))[1] == "—",
        "a missing work package does not read —",
    )
    expect("Need by" not in mto.columns_for(h.lines), "Need by kept when constant")
    print("PASS columns_for drops For when constant and Need by when constant")


def check_textual_free(_: Harness) -> None:
    code = "import tl_tui.mto_text, sys; print('textual' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    expect(out == "False", f"importing tl_tui.mto_text loaded textual: {out!r}")
    print("PASS importing tl_tui.mto_text leaves textual out of sys.modules")


def detail_for(db: Path, key: str) -> detail_views.MtoLineDetailView:
    with open_uow(as_target(db), readonly=True) as uow:
        return detail_views.mto_line_detail(uow.conn(), SCOPE, key)


def check_no_none_in_hand_built(_: Harness) -> None:
    cells = mto.row_cells(
        MtoLineView(**{**hand_built().model_dump(), "work_package": None}),
        mto.MTO_COLUMNS,
    )
    no_bad_values(cells, "hand-built row")
    expect(cells[2] == "—" and cells[7] == "—", f"empty For or Need by: {cells!r}")
    print("PASS a hand-built row with no work package and no need-by reads —")


# --- part 2: the screen -----------------------------------------------------------


async def run_screen(db: Path, width: int, height: int) -> tuple[dict[str, bool], int]:
    """Mount the screen on the app at ``width`` x ``height`` and walk its keys; returns the steps
    that held and the number of lines the project lists."""
    client = EmbeddedClient(SqliteUowFactory(db), actor="user:dev")
    app = TlApp(client, scope=SCOPE, actor="user:dev")
    listed = client.list_materials_mto_lines(PROJECT)
    total = len(listed)
    keys = [line.key for line in listed]
    steps: dict[str, bool] = {}
    async with app.run_test(size=(width, height)) as pilot:
        await settle(pilot)
        app.push_screen(MtoLinesScreen(client, PROJECT))
        await settle(pilot)
        steps["pushed"] = isinstance(app.screen, MtoLinesScreen)
        text = screen_text(app)
        steps["key"] = any(key in text for key in keys)
        steps["all"] = f"Showing {total} of {total} lines" in text
        await pilot.press("down")
        await settle(pilot)
        steps["panel"] = "Coverage" in screen_text(app)
        await pilot.press("2")
        await settle(pilot)
        steps["short"] = "lines · short only" in screen_text(app)
        await pilot.press("1")
        await settle(pilot)
        steps["restored"] = "lines · short only" not in screen_text(app)
        SHOTS.mkdir(parents=True, exist_ok=True)
        svg = app.export_screenshot(title="MTO lines")
        (SHOTS / f"T06d-mto-{width}.svg").write_text(svg, encoding="utf-8")
        await pilot.press("escape")
        await settle(pilot)
        steps["closed"] = not isinstance(app.screen, MtoLinesScreen)
    return steps, total


SCREEN_NAMES = {
    "pushed": "the screen mounts on TlApp",
    "key": "the table shows an MTO line key",
    "all": "the summary reads Showing N of N lines",
    "panel": "down shows the panel with Coverage",
    "short": "2 changes the summary to short only",
    "restored": "1 restores the summary",
    "closed": "Esc closes the screen",
}


def screen_checks(db: Path) -> None:
    for width, height in ((80, 30), (170, 40)):
        steps, _ = asyncio.run(run_screen(db, width, height))
        for step, label in SCREEN_NAMES.items():
            expect(steps.get(step, False), f"{width}x{height}: {label} failed")
        print(f"PASS MtoLinesScreen at {width}x{height}: {', '.join(SCREEN_NAMES.values())}")
        print(f"PASS screenshot saved to {SHOTS / f'T06d-mto-{width}.svg'}")


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    ("seed", check_seed_has_lines),
    ("panel", check_panel_within_width),
    ("rows", check_rows_as_cells),
    ("sections", check_sections_order),
    ("source", check_source_parsed),
    ("state", check_state),
    ("empty", check_empty_sections),
    ("columns", check_columns_for),
    ("hand", check_no_none_in_hand_built),
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
            lines = views.mto_lines(conn, SCOPE, work_package=WORK_PACKAGE)
            if not lines:
                print("FAIL seed: the seed ledger has no MTO lines")
                return 1
            detail = detail_views.mto_line_detail(conn, SCOPE, lines[0].key)
        harness = Harness(db, lines, detail)
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
