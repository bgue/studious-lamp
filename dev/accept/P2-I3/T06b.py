"""P2-I3-T06b acceptance: the receipt text module and the receipts log screen.

Run from the repo root after ``dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db``:
``uv run python dev/accept/P2-I3/T06b.py``. Exit 0 with one ``PASS <check>`` line per check.
The screenshots go to ``.accept/shots/T06b-receipts-<width>.svg`` (untracked).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("TL_ENV", "test")  # the dev ledger rule, as the other P2-W0 scripts set it

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
SHOTS = ROOT / ".accept" / "shots"
PROJECT = "P123"
RECEIPT = "P123-RCPT-0001"
ACTOR = "user:alice"
SIZES = ((80, 30), (170, 40))
HEADINGS = ("Lines", "Delivery", "Inspection", "Files")
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the Textual test helpers

from helpers import panel_of, screen_text, settle  # noqa: E402
from rich.cells import cell_len  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_mod_materials.limits import MAX_VIEW_ROWS  # noqa: E402
from tl_mod_materials.views import (  # noqa: E402
    ReceiptDetailView,
    ReceiptFileView,
    ReceiptLineView,
    ReceiptView,
)
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.layout import WAITING_STYLE, Note, Page, Section, page_lines  # noqa: E402
from tl_tui.receipt_text import (  # noqa: E402
    KEYS,
    RECEIPT_COLUMNS,
    RECEIPT_DROP,
    RIGHT,
    columns_for,
    receipt_lines,
    receipt_page,
    row_cells,
)
from tl_tui.widgets.receipt_log import ReceiptLogScreen  # noqa: E402

Check = Callable[[], None]
LONE_DASH = re.compile(r"(?<!\S)-(?!\S)")


def passed(check: str) -> None:
    print(f"PASS {check}")


def view(number: str, location: str, state: str = "Received", mtr: str = "n/a") -> ReceiptView:
    return ReceiptView(
        id=f"id-{number}",
        number=number,
        title=f"Receipt {number}",
        state=state,
        received_on="2026-10-01",
        location=location,
        supplier_text="Meridian Steel",
        delivery_ref=None,
        po_line=None,
        lines=2,
        mtr=mtr,  # type: ignore[arg-type]
        mtr_required=False,
    )


def detail(
    state: str = "Received",
    *,
    mtr: str = "n/a",
    mtr_required: bool = False,
    rejection_reason: str | None = None,
    files: Sequence[ReceiptFileView] = (),
    line_rows: Sequence[ReceiptLineView] = (),
) -> ReceiptDetailView:
    return ReceiptDetailView(
        id="id-hand",
        number="P123-RCPT-9001",
        title="Hand built",
        state=state,
        received_on="2026-10-01",
        location="WH-1",
        supplier_text="Meridian Steel",
        delivery_ref=None,
        po_line=None,
        lines=len(line_rows),
        mtr=mtr,  # type: ignore[arg-type]
        mtr_required=mtr_required,
        created_at="2026-10-01T08:00:00",
        inspected_by=None,
        inspected_on=None,
        decided_by=None,
        decided_on=None,
        rejection_reason=rejection_reason,
        received_by=None,
        line_rows=list(line_rows),
        files=list(files),
    )


def line(line_no: int, uom: str, heat: str | None = None) -> ReceiptLineView:
    return ReceiptLineView(
        line_no=line_no,
        item_code="FLG-150",
        item_title="Weld neck flange 150 mm",
        qty=Decimal("12.000"),
        uom=uom,
        heat_no=heat,
        condition="good",
        serials_text=None,
        lot=None,
    )


def check_seed_panel(db: Path) -> None:
    client = EmbeddedClient(SqliteUowFactory(db), actor=ACTOR)
    rows = client.list_materials_receipts(PROJECT, limit=MAX_VIEW_ROWS)
    numbers = [row.number for row in rows]
    assert RECEIPT in numbers, f"{RECEIPT} is not in {numbers}"
    found = client.get_materials_receipt(PROJECT, RECEIPT)
    assert found.mtr == "present", f"MTR is {found.mtr!r}, the seed attaches one"
    for width in (80, 170):
        lines = receipt_lines(found, width=width)
        print(f"-- panel at {width} columns")
        print("\n".join(lines))
        assert not any("None" in text for text in lines), "a line shows None"
        assert not any(LONE_DASH.search(text) for text in lines), "a line has a bare dash"
        too_wide = [text for text in lines if cell_len(text) > width]
        assert not too_wide, f"lines wider than {width}: {too_wide[:2]}"
        positions = [lines.index(heading) for heading in HEADINGS]
        assert positions == sorted(positions), f"sections out of order: {positions}"
        assert any(text.startswith("Received by") for text in lines), "no Received by"
        assert not any("user:" in text for text in lines), "an actor shows its prefix"
        assert "H-7781" in "\n".join(lines), "the heat H-7781 is not in the panel"
        rows_text = [row_cells(v, columns_for(rows), None) for v in rows[:3]]
        print(f"-- first log rows at {width} columns")
        for cells in rows_text:
            print(" | ".join(cells))
    passed("seed receipt panel at 80 and 170: no None, no bare dash, every line in width")
    passed("seed panel sections in order Lines, Delivery, Inspection, Files; Received by present")


def check_columns_for() -> None:
    same = [view("P1-R1", "WH-1"), view("P1-R2", "WH-1")]
    other = [view("P1-R1", "WH-1"), view("P1-R2", "WH-2")]
    dropped = columns_for(same)
    assert "Location" not in dropped, dropped
    assert {"Number", "Subject", "State"} <= set(dropped), dropped
    assert "Location" in columns_for(other), columns_for(other)
    assert columns_for(same[:1]) == RECEIPT_COLUMNS, "one row keeps every column"
    assert RECEIPT_DROP == ("Lines", "Location", "MTR", "Received"), RECEIPT_DROP
    assert RIGHT == frozenset({"Lines"}), RIGHT
    assert KEYS == "o open only  m missing MTR  / filter  F5 reload  Esc close", KEYS
    passed("columns_for drops Location at one location, keeps it at two locations")


def check_rejection() -> None:
    rejected = receipt_lines(detail("Rejected", rejection_reason="Heat certificate missing"))
    assert any(text.startswith("Rejection reason") for text in rejected), rejected
    assert any("Heat certificate missing" in text for text in rejected), rejected
    unrejected = receipt_lines(detail("Accepted", rejection_reason=None))
    assert not any(text.startswith("Rejection reason") for text in unrejected), unrejected
    passed("a Rejected receipt shows Rejection reason; an accepted one does not")


def check_empty_and_mtr() -> None:
    lines = receipt_lines(detail())
    assert any(text.startswith("Inspected by") and text.endswith("—") for text in lines), lines
    assert "Receiving inspection  n/a until quality inspections exist" in lines, lines
    assert "No files" in receipt_lines(detail()), "no files reads No files"
    missing = receipt_lines(detail(mtr="missing", mtr_required=True))
    assert "MTR required to accept" in missing, missing
    assert not any(text.startswith("mtr") for text in missing), "a file row for a missing MTR"
    assert missing.index("Files") < missing.index("MTR required to accept"), missing
    photo_only = [
        ReceiptFileView(
            file_id="F-3", slot="photo", filename="p.jpg", status="available", uploaded_at="x"
        )
    ]
    with_photo = receipt_lines(detail(mtr="missing", mtr_required=True, files=photo_only))
    slot_head = next(i for i, text in enumerate(with_photo) if text.startswith("Slot"))
    assert with_photo.index("MTR required to accept") < slot_head, with_photo
    assert not any(text.startswith("mtr") for text in with_photo), "a file row for a missing MTR"
    files = [
        ReceiptFileView(
            file_id="F-2", slot="photo", filename="pallet.jpg", status="available", uploaded_at="x"
        ),
        ReceiptFileView(
            file_id="F-1", slot="mtr", filename="mtr-7781.pdf", status="available", uploaded_at="x"
        ),
    ]
    with_files = receipt_lines(detail(mtr="present", mtr_required=True, files=files))
    mtr_row = next(i for i, text in enumerate(with_files) if text.startswith("mtr"))
    photo_row = next(i for i, text in enumerate(with_files) if text.startswith("photo"))
    assert mtr_row < photo_row, "the MTR slot is not first"
    assert not any("required to accept" in text for text in with_files), with_files
    passed("empty values read —; Receiving inspection is last; No files when no file exists")
    passed("missing MTR is a plain line before the Files table, never a file row")
    passed("Files table lists the MTR slot first and drops the missing-MTR line once it is there")


def files_section(page: Page) -> Section:
    return next(section for section in page.sections if section.heading == "Files")


def styled_segments(page: Page, text: str) -> list[tuple[str, str]]:
    """Every rendered segment that reads ``text``, with its style."""
    return [seg for line in page_lines(page) for seg in line if seg[0] == text]


def check_mtr_note() -> None:
    missing = receipt_page(detail(mtr="missing", mtr_required=True))
    first = files_section(missing).items[0]
    assert isinstance(first, Note), f"the first Files item is {first!r}, not a Note"
    assert first.style == WAITING_STYLE == "yellow", first
    assert styled_segments(missing, "MTR required to accept") == [
        ("MTR required to accept", WAITING_STYLE)
    ], "the MTR line is not in the waiting style"
    passed("missing MTR is a Note in the waiting style, first in the Files section")
    files = [
        ReceiptFileView(
            file_id="F-1", slot="mtr", filename="mtr-7781.pdf", status="available", uploaded_at="x"
        )
    ]
    attached = receipt_page(detail(mtr="present", mtr_required=True, files=files))
    assert not any(isinstance(item, Note) for item in files_section(attached).items), "a Note"
    empty = receipt_page(detail())
    assert files_section(empty).note == "No files", files_section(empty)
    assert files_section(empty).items == (), "the No files section has items"
    assert styled_segments(empty, "No files") == [("No files", "")], "No files is styled"
    passed("an MTR attached or not required has no Note; No files stays plain")


def check_lines_table() -> None:
    same_uom = receipt_lines(detail(line_rows=[line(1, "EA"), line(2, "EA", "H-1")]))
    assert "UOM" not in same_uom[same_uom.index("Lines") + 1], same_uom
    mixed = receipt_lines(detail(line_rows=[line(1, "EA"), line(2, "M")]))
    assert "UOM" in mixed[mixed.index("Lines") + 1], mixed
    passed("Lines table drops UOM when every line has the same one")


def check_import_leaves_textual() -> None:
    code = (
        "import sys, tl_tui.receipt_text\n"
        "print(any(name == 'textual' or name.startswith('textual.') for name in sys.modules))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=ROOT
    )
    assert done.stdout.strip() == "False", done.stdout + done.stderr
    passed("import tl_tui.receipt_text leaves textual out of sys.modules")


def screen_check(db: Path, size: tuple[int, int]) -> None:
    width, height = size
    client = EmbeddedClient(SqliteUowFactory(db), actor=ACTOR)
    app = TlApp(client, scope=f"project:{PROJECT}", actor=ACTOR)
    SHOTS.mkdir(parents=True, exist_ok=True)

    async def scenario() -> None:
        async with app.run_test(size=size) as pilot:
            await settle(pilot)
            app.push_screen(ReceiptLogScreen(client, PROJECT))
            await settle(pilot)
            screen = app.screen
            assert isinstance(screen, ReceiptLogScreen), type(screen).__name__
            assert RECEIPT in screen_text(app), "the receipt is not on the screen"
            assert "Showing" in screen_text(app), "no summary line"
            shown = screen.shown
            first = shown[0].number
            assert first in panel_of(screen), "the panel does not show the highlighted receipt"
            # the seed holds one receipt in P123: down and up then leave the panel on it
            target = shown[1].number if len(shown) >= 2 else first
            await pilot.press("down")
            await settle(pilot)
            assert target in panel_of(screen), "down did not show the panel of the next receipt"
            await pilot.press("up")
            await settle(pilot)
            assert first in panel_of(screen), "up did not show the panel back"
            await pilot.press("o")
            await settle(pilot)
            assert "receipts · open only" in screen_text(app), "o did not change the summary"
            await pilot.press("o")
            await settle(pilot)
            assert "receipts · open only" not in screen_text(app), "o did not clear"
            await pilot.press("m")
            await settle(pilot)
            assert "receipts · missing MTR" in screen_text(app), "m did not change the summary"
            await pilot.press("m")
            await settle(pilot)
            svg = app.export_screenshot(title="Receipts")
            (SHOTS / f"T06b-receipts-{width}.svg").write_text(svg, encoding="utf-8")
            await pilot.press("escape")
            await settle(pilot)
            assert not isinstance(app.screen, ReceiptLogScreen), "Esc did not close the screen"

    asyncio.run(scenario())
    passed(f"receipts screen at {width}x{height}: listed, panel follows down/up, o and m, Esc")


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    checks: list[Check] = [check_columns_for, check_rejection, check_empty_and_mtr]
    checks += [check_mtr_note, check_lines_table, check_import_leaves_textual]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "tl.db"
            for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
                shutil.copy(src, Path(tmp) / ("tl.db" + src.name[len(LEDGER.name) :]))
            check_seed_panel(db)
            for check in checks:
                check()
            for size in SIZES:
                screen_check(db, size)
    except AssertionError as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
