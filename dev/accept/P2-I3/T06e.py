"""P2-I3-T06e acceptance: the new-receipt text module, the receipt entry screen and the item crumb.

Run from the repo root after ``dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db``:
``uv run python dev/accept/P2-I3/T06e.py``. Exit 0 with one ``PASS <check>`` line per check.
Each screen check works on its own copy of the ledger. The screenshots go to
``.accept/shots/T06e-entry-80.svg`` and ``.accept/shots/T06e-entry-170.svg`` (untracked).

P2-I3-T06j adds the optional MTR file: the text checks, a fake-client save with and without a
file, and one real-ledger save then attach (``list_record_files`` shows slot ``mtr``). The form
with the MTR field is saved to ``.accept/shots/T06j-80.svg`` and ``.accept/shots/T06j-170.svg``.
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
from typing import Any

os.environ.setdefault("TL_ENV", "test")  # the dev ledger rule, as the other P2-W0 scripts set it

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
ACTOR = "user:alice"
SIZES = ((80, 30), (170, 40))
KEYS_TEXT = "Ctrl+S save  Enter add line  Del remove line  Esc close"  # the keys row, pinned
PO_KEY = "4471-2"  # a seed PO line for one item; both lines of the receipt carry that item
ITEM_CODE = "ELB-LR-90-6-SCH40"  # the item of the fake library and of the seed's PO line
LOCATION = "L2"
BAD_LOCATION = "ZZ9"
RECEIPT = "P123-RCPT-0002"  # the seed holds P123-RCPT-0001
LONE_DASH = re.compile(r"(?<!\S)-(?!\S)")
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the Textual test helpers

from fakes import FakeClient  # noqa: E402
from helpers import screen_text, settle, static_of  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import DataTable, Input  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_core.auth import accounts  # noqa: E402
from tl_core.services.commands import Command, CommandResult  # noqa: E402
from tl_mod_materials.handlers.receipts import CreateReceipt  # noqa: E402
from tl_mod_materials.limits import MAX_RECEIPT_LINES  # noqa: E402
from tl_mod_materials.views import LocationView, MaterialItemView, PoLineView  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.client import ClientInterface  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.receipt_entry_text import (  # noqa: E402
    HEADER_FIELDS,
    KEYS,
    LINE_FIELDS,
    MAX_LINES,
    MTR_FIELD,
    added_text,
    build_command,
    check_count,
    check_header,
    check_line,
    check_mtr_path,
    line_summary,
    location_hints,
    po_line_hints,
    saved_attached_text,
    saved_not_attached_text,
    saved_text,
)
from tl_tui.widgets.item_library import ItemLibraryScreen  # noqa: E402
from tl_tui.widgets.receipt_entry import ReceiptEntryScreen  # noqa: E402

Check = Callable[[], None]
MTR_NAME = "mtr-cert.pdf"
MTR_RECORD = "RCPT-REC-1"  # the record id the fake gives the booked receipt (its stream id)
MTR_BYTES = b"%PDF-1.4\nmill test report\n%%EOF\n"


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
                    KEYS == KEYS_TEXT and static_of(screen, "#entry-keys") == KEYS_TEXT,
                    f"the keys row is {static_of(screen, '#entry-keys')!r}",
                )
                expect(
                    "Del&#160;remove&#160;line" in app.export_screenshot(title="New receipt"),
                    "the SVG keys row lacks Del remove line",
                )
                passed("the keys row reads Ctrl+S save  Enter add line  Del remove line  Esc close")
                table = screen.query_one("#entry-lines", DataTable)
                await pilot.press("down")  # to line 2, the 3.5 line
                await settle(pilot)
                await pilot.press("delete")  # removes line 2; the old line 3 moves up under it
                await settle(pilot)
                expect(len(screen.lines) == 2 and table.row_count == 2, "not two rows after Delete")
                expect(table.cursor_row == 1, f"the cursor is on row {table.cursor_row}, not 1")
                expect(screen.lines[1]["qty"] == "1", f"row 1 is {screen.lines[1]}, not line 3")
                passed("Delete on line 2 of 3: two rows, the cursor stays on row 1 (old line 3)")
                # a third line, then Delete on the last of three rows: the cursor must stay on
                # row 1 (a reset to row 0 after clear() would pass a two-row check)
                screen.query_one("#l-item", Input).focus()
                await type_into(pilot, po_line.item_code)
                await pilot.press("enter")  # to Qty
                await type_into(pilot, "2")
                await pilot.press("enter", "enter", "enter")
                await settle(pilot)
                expect(len(screen.lines) == 3, f"{len(screen.lines)} lines after the third add")
                screen.query_one("#entry-lines").focus()
                await pilot.press("down")  # to row 2, the new last row
                await settle(pilot)
                expect(table.cursor_row == 2, f"the cursor is on row {table.cursor_row}, not 2")
                await pilot.press("delete")  # the last row goes; the cursor moves up to row 1
                await settle(pilot)
                expect(len(screen.lines) == 2 and table.row_count == 2, "not two rows after Delete")
                expect(table.cursor_row == 1, f"the cursor is on row {table.cursor_row}, not 1")
                passed("Delete on the last row of three: the cursor is on the new last row (row 1)")
                await pilot.press("up")  # row 0: its line goes, leaving one line for the re-add
                await settle(pilot)
                await pilot.press("delete")
                await settle(pilot)
                expect(len(screen.lines) == 1, f"{len(screen.lines)} lines after the row-0 Delete")
                # the line count goes back to two, so the save below books two lines
                screen.query_one("#l-item", Input).focus()
                await type_into(pilot, po_line.item_code)
                await pilot.press("enter")  # to Qty
                await type_into(pilot, "3.5")
                await pilot.press("enter", "enter", "enter")
                await settle(pilot)
                expect(len(screen.lines) == 2, f"{len(screen.lines)} lines after the re-add")
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


# --- part 3: the optional MTR file (P2-I3-T06j) ---------------------------------------------


class ReceiptFake(FakeClient):
    """Books the receipt under ``MTR_RECORD``, a record the fake knows, so an attach works. With
    ``known=False`` the receipt answers as ``MAT-1``, which the fake does not hold, so an attach
    raises ``RecordNotFoundError``."""

    def __init__(self, *, known: bool = True) -> None:
        super().__init__()
        self.known = known
        self.put_materials(PROJECT, locations=[location(LOCATION, "Laydown 2")])
        self.put_material_items([item(ITEM_CODE)])

    def materials_command(self, name: str, cmd: Command) -> CommandResult:
        super().materials_command(name, cmd)
        stream = MTR_RECORD if self.known else "MAT-1"
        if self.known:
            self.set_actions(MTR_RECORD)  # makes the record known to the fake's attach
        return CommandResult(stream_id=stream, key=RECEIPT, version=1, events=[])


class LedgerClient(EmbeddedClient):
    """The embedded client, remembering the stream id of the last command (the receipt's id)."""

    last_stream_id: str | None = None

    def materials_command(self, name: str, cmd: Command) -> CommandResult:
        result = super().materials_command(name, cmd)
        self.last_stream_id = result.stream_id
        return result


def write_mtr(folder: Path) -> Path:
    path = folder / MTR_NAME
    path.write_bytes(MTR_BYTES)
    return path


def fill_and_save(
    client: ClientInterface, mtr: str, size: tuple[int, int], *, shot: bool = True
) -> dict[str, Any]:
    """Fill the header and one line on the form, type ``mtr`` into the MTR field, press Ctrl+S.
    Returns the status line, the lines left on the form and the field error under the MTR."""
    width, height = size
    app = TlApp(client, scope=f"project:{PROJECT}", actor=ACTOR)
    seen: dict[str, Any] = {}

    async def scenario() -> None:
        async with app.run_test(size=size) as pilot:
            await settle(pilot)
            app.push_screen(ReceiptEntryScreen(client, PROJECT, ACTOR))
            await settle(pilot)
            screen = app.screen
            assert isinstance(screen, ReceiptEntryScreen)
            screen.query_one("#h-supplier", Input).value = "Northline Pipe Supply"
            screen.query_one("#h-delivery_ref", Input).value = "DN-7781"
            screen.query_one("#h-location", Input).value = LOCATION
            screen.query_one("#l-item", Input).value = ITEM_CODE
            screen.query_one("#l-qty", Input).value = "2"
            screen.action_add_line()
            screen.query_one("#h-mtr", Input).value = mtr
            await settle(pilot)
            if shot:
                SHOTS.mkdir(parents=True, exist_ok=True)
                svg = app.export_screenshot(title="New receipt")
                (SHOTS / f"T06j-{width}.svg").write_text(svg, encoding="utf-8")
            await pilot.press("ctrl+s")
            await settle(pilot)
            seen["status"] = static_of(screen, "#entry-status")
            seen["lines"] = list(screen.lines)
            seen["error"] = static_of(screen, "#err-mtr")
            seen["screen"] = screen

    asyncio.run(scenario())
    return seen


def check_mtr_text() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        here = Path(tmp)
        real = write_mtr(here)
        expect(check_mtr_path("") is None and check_mtr_path("   ") is None, "blank has a message")
        expect(check_mtr_path(str(real)) is None, "a readable file has a message")
        gone = str(here / "nope.pdf")
        expect(check_mtr_path(gone) == f"No such file: {gone}", f"missing: {check_mtr_path(gone)}")
        expect(check_mtr_path(str(here)) == f"No such file: {here}", "a directory is a file")
    expect(
        saved_attached_text(RECEIPT, MTR_NAME) == f"Saved {RECEIPT}. MTR {MTR_NAME} attached.",
        "saved_attached_text",
    )
    expect(
        saved_not_attached_text(RECEIPT, "the file was rejected")
        == f"Saved {RECEIPT}. MTR not attached: the file was rejected. "
        "Attach the MTR on the receipt (tl file put, slot mtr).",
        "saved_not_attached_text",
    )
    expect(MTR_FIELD == ("mtr", "MTR file"), f"MTR_FIELD is {MTR_FIELD}")
    passed("MTR path: blank and readable file pass, a missing path or a directory is refused")


def check_mtr_fake_saves() -> None:
    for size in SIZES:
        with tempfile.TemporaryDirectory() as tmp:
            real = write_mtr(Path(tmp))
            client = ReceiptFake()
            seen = fill_and_save(client, str(real), size)
            expect(
                client.attached_files == [(MTR_RECORD, MTR_NAME, "mtr")], str(client.attached_files)
            )
            expect(seen["status"] == saved_attached_text(RECEIPT, MTR_NAME), f"{seen['status']!r}")
            expect(seen["lines"] == [], "the lines were not cleared after the save")
            expect(len(client.materials_commands) == 1, "the receipt was not booked once")
    passed("good save with a file: attached in slot mtr, status Saved <n>. MTR <name> attached.")

    client = ReceiptFake()
    seen = fill_and_save(client, "", (170, 40), shot=False)
    expect(client.attached_files == [], f"a blank path attached {client.attached_files}")
    expect(seen["status"] == saved_text(RECEIPT), f"{seen['status']!r}")
    expect(seen["lines"] == [], "the lines were not cleared after a save without a file")
    passed("good save with no path: nothing attached, status keeps saved_text")

    client = ReceiptFake()
    with tempfile.TemporaryDirectory() as tmp:
        gone = str(Path(tmp) / "nope.pdf")
        seen = fill_and_save(client, gone, (170, 40), shot=False)
    expect(seen["error"] == f"No such file: {gone}", f"the field error is {seen['error']!r}")
    expect(client.materials_commands == [], "a receipt was booked with a missing file")
    expect(client.attached_files == [], "a file was attached with a missing path")
    expect(len(seen["lines"]) == 1, "the lines were cleared on a refused save")
    passed("missing path: No such file on the form, no receipt booked, lines kept")

    client = ReceiptFake(known=False)
    with tempfile.TemporaryDirectory() as tmp:
        seen = fill_and_save(client, str(write_mtr(Path(tmp))), (170, 40), shot=False)
    status = str(seen["status"])
    expect(len(client.materials_commands) == 1, "the receipt was not booked")
    expect(status.startswith(f"Saved {RECEIPT}. MTR not attached: "), f"status is {status!r}")
    expect(seen["lines"] == [], "the lines were not cleared after the save")
    passed("attach raises RecordNotFoundError: receipt stays saved, status names MTR not attached")


def check_mtr_real_ledger() -> None:
    previous = os.environ.get("TL_ENV")
    os.environ["TL_ENV"] = "dev"  # the harness's dev token file is honoured in dev (as S6.py)
    api_tests = str(ROOT / "packages" / "tl-api" / "tests")
    sys.path.insert(0, api_tests)
    try:
        from harness import ALICE, Harness  # noqa: PLC0415 (the API test harness, as S6 builds it)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = as_target(copy_ledger(root))
            api_root = root / "api"
            api_root.mkdir()
            harness = Harness.build(api_root, target=target)
            try:
                with open_uow(target) as uow:
                    accounts.create_account(
                        uow,
                        username="alice",
                        display_name="Alice",
                        kind="person",
                        roles=["user"],
                        password=None,
                        by="user:seed",
                    )
                client = LedgerClient(harness.backend, actor=ALICE, object_store=harness.store)
                seen = fill_and_save(client, str(write_mtr(root)), (170, 40), shot=False)
                status = str(seen["status"])
                expect(status == saved_attached_text(RECEIPT, MTR_NAME), f"status is {status!r}")
                record_id = client.last_stream_id
                expect(record_id is not None, "the save gave no stream id")
                files = client.list_record_files(str(record_id))
                expect(
                    [(f.slot, f.filename) for f in files] == [("mtr", MTR_NAME)],
                    f"files on the receipt: {[(f.slot, f.filename) for f in files]}",
                )
                expect(ITEM_CODE in {i.code for i in client.list_materials_items()}, "the item")
            finally:
                harness.close()
    finally:
        sys.path.remove(api_tests)
        if previous is None:
            os.environ.pop("TL_ENV", None)
        else:
            os.environ["TL_ENV"] = previous
    passed("real ledger (EmbeddedClient): save then attach, list_record_files shows slot mtr")


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
        check_mtr_text()
        check_mtr_fake_saves()
        check_mtr_real_ledger()
    except Failure as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
