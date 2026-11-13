"""P2-I5-T07b: the IWP pack template, rendered from a hand-built ``PackData`` (no ledger)."""

from __future__ import annotations

import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from tl_mod_awp.pack import (
    NO_QUALITY,
    NO_SAFETY,
    NOT_TRACKED,
    Cover,
    Drawing,
    MtoLine,
    PackData,
    ScopeLine,
    Signoff,
    render_html,
)

GOLDEN = Path(__file__).parent / "golden" / "pack.html"
HEADINGS = [
    "Cover",
    "Scope and steps",
    "Drawings",
    "Take-off",
    "Safety",
    "Inspection and test plan",
    "Permits and scaffold tags",
    "Sign-off",
]


def data(*, drawings: bool = True) -> PackData:
    return PackData(
        iwp_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6P1",
        cover=Cover(
            number="P123-IWP-0007",
            title='Pipe rack <A> & "B"',
            state="Issued",
            discipline="PIP",
            foreman="user:uma",
            cwp_number="P123-CWP-0002",
            planned_start="2026-11-16",
            planned_finish="2026-11-27",
            estimated_hours=Decimal("120.5"),
            crew_text="1 foreman, 4 fitters",
        ),
        scope=(
            ScopeLine(
                key="P123-WI-0011",
                type="Item",
                description="Spools 1 to 4",
                qty=Decimal("4"),
                uom="ea",
                pct=Decimal("25.0"),
                steps=("Material received",),
            ),
            ScopeLine(
                key=None,
                type="Tag",
                description="Support tag",
                qty=None,
                uom=None,
                pct=None,
                steps=(),
            ),
        ),
        drawings=((Drawing(key="ISO-1", title="Rack isometric", pin="A"),) if drawings else ()),
        mto=(
            MtoLine(
                line_no=1,
                item_key="P123-ITM-0003",
                qty=Decimal("12"),
                uom="m",
                reserved=Decimal("12"),
                issued=Decimal("0"),
            ),
        ),
        signoffs=(Signoff(who="user:sue", role="Superintendent", day="2026-11-12"),),
        safety=NO_SAFETY,
        quality=NO_QUALITY,
        permits=NOT_TRACKED,
        generated_on=date(2026, 11, 9),
        notes=(),
    )


def no_segno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "segno", None)  # the import fails: no codes, stable bytes


def h2(page: str) -> list[str]:
    return re.findall(r"<h2[^>]*>([^<]*)</h2>", page)


def test_the_page_matches_the_golden_file(monkeypatch: pytest.MonkeyPatch) -> None:
    no_segno(monkeypatch)
    assert render_html(data()).html == GOLDEN.read_text(encoding="utf-8")


def test_each_heading_appears_once_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    no_segno(monkeypatch)
    assert h2(render_html(data()).html) == HEADINGS


def test_the_page_is_self_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    no_segno(monkeypatch)
    page = render_html(data()).html
    for banned in ("<script", "http", "src=", "<link", "@import", "url("):
        assert banned not in page
    assert "@page" in page
    assert "A4" in page


def test_the_signoff_sheet_has_a_recorded_table_and_a_ruled_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_segno(monkeypatch)
    page = render_html(data()).html
    sheet = page[page.index("Sign-off") :]
    assert "Superintendent" in sheet
    ruled = sheet[sheet.rindex("<table") :]
    for column in ("Name", "Role", "Signature", "Date"):
        assert f"<th>{column}</th>" in ruled
    assert ruled.count("<tr") == 7  # the header and six empty rows


def test_the_record_values_stay_escaped(monkeypatch: pytest.MonkeyPatch) -> None:
    no_segno(monkeypatch)
    page = render_html(data()).html
    assert "Pipe rack &lt;A&gt; &amp; &quot;B&quot;" in page
    assert "<A>" not in page


def test_with_segno_the_drawing_has_a_code_and_the_headings_stay() -> None:
    pytest.importorskip("segno")
    got = render_html(data())
    assert got.qr is True
    assert got.html.count("<svg") == 1
    assert h2(got.html) == HEADINGS


def test_without_segno_the_headings_stay_and_there_is_no_svg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_segno(monkeypatch)
    got = render_html(data())
    assert got.qr is False
    assert "<svg" not in got.html
    assert h2(got.html) == HEADINGS


def test_an_empty_drawing_list_still_has_every_heading(monkeypatch: pytest.MonkeyPatch) -> None:
    no_segno(monkeypatch)
    assert h2(render_html(data(drawings=False)).html) == HEADINGS
