"""P2-I3-T06e acceptance: the new-receipt text module, the receipt entry screen and the item crumb.

Run from the repo root after ``dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db``:
``uv run python dev/accept/P2-I3/T06e.py``. Exit 0 with one ``PASS <check>`` line per check.
Each screen check works on its own copy of the ledger. The screenshots go to
``.accept/shots/T06e-entry-80.svg`` and ``.accept/shots/T06e-entry-170.svg`` (untracked).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("TL_ENV", "test")  # the dev ledger rule, as the other P2-W0 scripts set it

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
ACTOR = "user:alice"
SIZES = ((80, 30), (170, 40))
PO_KEY = "4471-2"  # a seed PO line for one item; both lines of the receipt carry that item
LOCATION = "L2"
BAD_LOCATION = "ZZ9"
RECEIPT = "P123-RCPT-0002"  # the seed holds P123-RCPT-0001
LONE_DASH = re.compile(r"(?<!\S)-(?!\S)")
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the Textual test helpers

from helpers import screen_text, settle, static_of  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import Input  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mod_materials.handlers.receipts import CreateReceipt  # noqa: E402
from tl_mod_materials.limits import MAX_RECEIPT_LINES  # noqa: E402
from tl_mod_materials.views import LocationView, MaterialItemView, PoLineView  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.receipt_entry_text import (  # noqa: E402
    HEADER_FIELDS,
    KEYS,
    LINE_FIELDS,
    MAX_LINES,
    added_text,
    build_command,
    check_count,
    check_header,
    check_line,
    line_summary,
    location_hints,
    po_line_hints,
    saved_text,
)
from tl_tui.widgets.item_library import ItemLibraryScreen  # noqa: E402
from tl_tui.widgets.receipt_entry import ReceiptEntryScreen  # noqa: E402

Check = Callable[[], None]


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def passed(check: str) -> None:
    print(f"PASS {check}")


def item(code: str, uom: str = "EA", *, retired: bool = False) -> MaterialItemView:
    return MaterialItemView(
        id=f"id-{code}",
        code=code,
        title=f"Item {code}",
        category="fitting",
        base_uom=uom,
        size_text=None,
        rating_text=None,
        material_code=None,
        consumable=False,
        retired=retired,
        projects=1,
    )


def po(qty_ordered: str, qty_received: str, uom: str = "EA") -> PoLineView:
    return PoLineView(
        id="id-po",
        key="4471-9",
        po_number="4471",
        line_no=9,
        item_code="ELB-LR-90-6-SCH40",
        item_title="Elbow long radius 90",
        qty_ordered=Decimal(qty_ordered),
        qty_received=Decimal(qty_received),
        uom=uom,
        promised_date=None,
        supplier_text="Northline Pipe Supply",
    )


def location(code: str, title: str) -> LocationView:
    return LocationView(
        id=f"id-{code}",
        code=code,
        title=title,
        kind="laydown",
        parent_code="WH1",
        depth=2,
        retired=False,
        lots=0,
        lines=0,
    )


def good_header(today: date) -> dict[str, str]:
    return {
        "po_line": PO_KEY,
        "supplier": "Northline Pipe Supply",
        "delivery_ref": "DN-7781",
        "received_on": today.isoformat(),
        "location": LOCATION,
    }


def good_line(code: str, qty: str, heat: str = "", condition: str = "good") -> dict[str, str]:
    return {"item": code, "qty": qty, "heat": heat, "condition": condition}


# --- part 1: the text module (no ledger) -------------------------------------------------------


def check_header_messages() -> None:
    today = date.today()
    locations = [LOCATION]
    expect(check_header(good_header(today), locations, today) == [], "a good header has an error")
    bad = check_header(dict(good_header(today), location=BAD_LOCATION), locations, today)
    expect(bad == [("location", "Pick a location of this project.")], f"location: {bad}")
    for value in ("10/02/2026", "2026-13-01", "2026-02-30", ""):
        errors = check_header(dict(good_header(today), received_on=value), locations, today)
        expect(
            errors == [("received_on", "Received on must be a date, YYYY-MM-DD.")],
            f"received_on {value!r}: {errors}",
        )
    later = (today + timedelta(days=1)).isoformat()
    errors = check_header(dict(good_header(today), received_on=later), locations, today)
    expect(len(errors) == 1 and errors[0][0] == "received_on", f"a future date: {errors}")
    passed(
        "header messages: Pick a location and Received on must be a date fire on bad values only"
    )


def check_line_messages() -> None:
    items = {"ELB-LR-90-6-SCH40": item("ELB-LR-90-6-SCH40")}
    expect(check_line(good_line("ELB-LR-90-6-SCH40", "2"), items) == [], "a good line has an error")
    missing = check_line(good_line("NOPE-1", "2"), items)
    expect(
        missing == [("item", "Item NOPE-1 is not in this project's library.")],
        f"item: {missing}",
    )
    expect(
        check_line(good_line("", "2"), items) == [("item", "Pick an item of this project.")],
        "a blank item has no message",
    )
    for value in ("0", "-2", "1.2345", "", "x"):
        errors = check_line(good_line("ELB-LR-90-6-SCH40", value), items)
        expect(
            errors == [("qty", "Quantity must be a positive number.")],
            f"qty {value!r}: {errors}",
        )
    for value in ("12.5", "1.234", "7"):
        expect(check_line(good_line("ELB-LR-90-6-SCH40", value), items) == [], f"qty {value}")
    expect(check_line(good_line("ELB-LR-90-6-SCH40", "1", condition=""), items) == [], "blank good")
    odd = check_line(good_line("ELB-LR-90-6-SCH40", "1", condition="broken"), items)
    expect(odd and odd[0][0] == "condition", f"condition: {odd}")
    expect(
        check_count(0) == [("lines", "Add at least one line.")],
        f"count 0: {check_count(0)}",
    )
    expect(
        check_count(MAX_RECEIPT_LINES + 1) == [("lines", "A receipt holds at most 50 lines.")],
        "51 lines has no message",
    )
    expect(check_count(1) == [] and check_count(MAX_LINES) == [], "1 or 50 lines has a message")
    expect(MAX_LINES == MAX_RECEIPT_LINES == 50, f"MAX_LINES is {MAX_LINES}")
    passed("line messages: item, quantity and line count fire on bad values only")


def check_build_two_lines() -> None:
    today = date.today()
    header = good_header(today)
    lines = [
        good_line("ELB-LR-90-6-SCH40", "2"),
        good_line("ELB-LR-90-6-SCH40", "3.5", heat="H-7781"),
    ]
    cmd = build_command(header, lines, actor=ACTOR, project=PROJECT)
    expect(isinstance(cmd, CreateReceipt), type(cmd).__name__)
    CreateReceipt.model_validate(cmd.model_dump())
    expect(cmd.scope == f"project:{PROJECT}" and cmd.source == "tui", "scope or source")
    expect(len(cmd.lines) == 2, f"{len(cmd.lines)} lines")
    expect(cmd.lines[1].heat_no == "H-7781" and cmd.lines[0].heat_no is None, "heat numbers")
    expect(cmd.lines[0].condition == "good" and cmd.lines[0].uom is None, "condition or uom")
    passed("build_command of two lines gives a CreateReceipt that validates")


def check_no_none_or_dash() -> None:
    texts = [label for _, label in HEADER_FIELDS] + [label for _, label in LINE_FIELDS]
    texts += [KEYS, saved_text(RECEIPT), added_text("ELB-LR-90-6-SCH40")]
    texts += po_line_hints([po("8", "0"), po("4", "9")])
    texts += location_hints([location(LOCATION, "Laydown 2"), location("L1", "")], "")
    texts += [line_summary({}, None), line_summary({"item": "X", "qty": "2", "heat": ""}, "EA")]
    texts += [text for pair in check_header({}, [], date.today()) for text in pair]
    texts += [text for pair in check_line({}, {}) for text in pair]
    for text in texts:
        expect("None" not in text, f"a text reads None: {text!r}")
        expect(not LONE_DASH.search(text), f"a text has a bare dash: {text!r}")
    passed("no text reads None or a bare dash, blank values included")


def check_hints() -> None:
    hints = po_line_hints([po("8", "0"), po("4", "9")])
    expect(hints[0] == "4471-9  ELB-LR-90-6-SCH40 Elbow long radius 90  8 EA open", hints[0])
    expect(hints[1].endswith("0 EA open"), f"over-received line: {hints[1]!r}")
    many = po_line_hints([po("1", "0") for _ in range(9)])
    expect(len(many) == 5, f"{len(many)} PO hints")
    picked = location_hints([location("L1", "Laydown 1"), location(LOCATION, "Laydown 2")], "lay")
    expect(picked == ["L1  Laydown 1", f"{LOCATION}  Laydown 2"], f"location hints {picked}")
    passed("hint lines: PO line open quantity, at most five; location by code or title")


def check_textual_free() -> None:
    code = (
        "import sys, tl_tui.receipt_entry_text\n"
        "print(any(name == 'textual' or name.startswith('textual.') for name in sys.modules))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=ROOT
    )
    expect(done.stdout.strip() == "False", done.stdout + done.stderr)
    passed("import tl_tui.receipt_entry_text leaves textual out of sys.modules")


# --- part 2: the screen over a copy of the seed ---------------------------------------------


def copy_ledger(tmp: Path) -> Path:
    """A copy of the seed ledger (and its WAL sidecars) in ``tmp``; the path of the copy."""
    for src in LEDGER.parent.glob(LEDGER.name + "*"):
        shutil.copy(src, tmp / ("tl.db" + src.name[len(LEDGER.name) :]))
    return tmp / "tl.db"


async def type_into(pilot: Pilot[None], text: str) -> None:
    await pilot.press(*text)
    await settle(pilot)


def screen_check(size: tuple[int, int]) -> None:
    width, height = size
    with tempfile.TemporaryDirectory() as tmp:
        db = copy_ledger(Path(tmp))
        client = EmbeddedClient(SqliteUowFactory(db), actor=ACTOR)
        app = TlApp(client, scope=f"project:{PROJECT}", actor=ACTOR)
        po_line = next(p for p in client.list_materials_po_lines(PROJECT) if p.key == PO_KEY)
        library = {i.code: i for i in client.list_materials_items(project=PROJECT)}
        expect(po_line.item_code in library, f"{po_line.item_code} is not in the library")
        SHOTS.mkdir(parents=True, exist_ok=True)

        async def scenario() -> None:
            async with app.run_test(size=size) as pilot:
                await settle(pilot)
                app.push_screen(ReceiptEntryScreen(client, PROJECT, ACTOR))
                await settle(pilot)
                screen = app.screen
                expect(isinstance(screen, ReceiptEntryScreen), type(screen).__name__)
                assert isinstance(screen, ReceiptEntryScreen)
                await type_into(pilot, PO_KEY)
                expect(PO_KEY in screen_text(app), "the PO line hint is not on the screen")
                supplier = screen.query_one("#h-supplier", Input).value
                expect(supplier == po_line.supplier_text, f"supplier is {supplier!r}")
                screen.query_one("#h-location", Input).focus()
                await type_into(pilot, BAD_LOCATION)
                screen.query_one("#l-item", Input).focus()
                for qty in ("2", "3.5", "1"):
                    await type_into(pilot, po_line.item_code)
                    await pilot.press("enter")  # to Qty
                    await type_into(pilot, qty)
                    await pilot.press("enter", "enter", "enter")  # Heat, Condition, add the line
                    await settle(pilot)
                expect(len(screen.lines) == 3, f"{len(screen.lines)} lines after three adds")
                screen.query_one("#entry-lines").focus()
                expect(
                    "[Del] Remove line" in screen_text(app), "the keys row lacks [Del] Remove line"
                )
                await pilot.press("delete")  # removes the highlighted (first) line
                await settle(pilot)
                expect(len(screen.lines) == 2, f"{len(screen.lines)} lines after Delete")
                expect(screen.lines[0]["qty"] == "3.5", f"the first line is {screen.lines[0]}")
                await pilot.press("ctrl+s")
                await settle(pilot)
                expect(
                    isinstance(app.screen, ReceiptEntryScreen), "the form closed on a bad location"
                )
                expect(
                    "Pick a location of this project." in screen_text(app),
                    "no location message under the field",
                )
                expect("! Not saved" in static_of(screen, "#entry-status"), "no refusal status")
                expect(len(client.list_materials_receipts(PROJECT)) == 1, "a receipt was booked")
                screen.query_one("#h-location", Input).value = LOCATION
                await settle(pilot)
                expect("Pick a location" not in screen_text(app), "the message stayed after a fix")
                svg = app.export_screenshot(title="New receipt")
                (SHOTS / f"T06e-entry-{width}.svg").write_text(svg, encoding="utf-8")
                await pilot.press("ctrl+s")
                await settle(pilot)
                status = static_of(screen, "#entry-status")
                expect(
                    status == saved_text(RECEIPT),
                    f"status is {status!r}, want {saved_text(RECEIPT)!r}",
                )
                expect(
                    " ".join(screen_text(app).split()).count(saved_text(RECEIPT)) == 1,
                    "the saved sentence is not on the screen in full",
                )
                booked = [r for r in client.list_materials_receipts(PROJECT) if r.number == RECEIPT]
                expect(len(booked) == 1, f"{RECEIPT} is not listed")
                expect(booked[0].state == "Received" and booked[0].lines == 2, repr(booked[0]))
                detail = client.get_materials_receipt(PROJECT, RECEIPT)
                expect(len(detail.line_rows) == 2, f"{len(detail.line_rows)} lines booked")
                expect(screen.lines == [], "the lines were not cleared after the save")
                await pilot.press("escape")
                await settle(pilot)
                expect(not isinstance(app.screen, ReceiptEntryScreen), "Esc did not close")

        asyncio.run(scenario())
    passed(f"entry screen at {width}x{height}: PO hint, bad location, add, Delete, save, Esc")


def check_item_crumb() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = EmbeddedClient(SqliteUowFactory(copy_ledger(Path(tmp))), actor=ACTOR)
        app = TlApp(client, scope="company", actor=ACTOR)

        async def scenario() -> None:
            async with app.run_test(size=(170, 40)) as pilot:
                await settle(pilot)
                app.push_screen(ItemLibraryScreen(client))
                await settle(pilot)
                expect("Company › Items" in screen_text(app), "the crumb is not Company › Items")

        asyncio.run(scenario())
    passed("the company item library crumb reads Company › Items")


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    checks: list[Check] = [
        check_header_messages,
        check_line_messages,
        check_build_two_lines,
        check_no_none_or_dash,
        check_hints,
        check_textual_free,
    ]
    try:
        for check in checks:
            check()
        for size in SIZES:
            screen_check(size)
        check_item_crumb()
    except Failure as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
