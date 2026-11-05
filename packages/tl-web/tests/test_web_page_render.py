"""The ``render_page`` macro: a layout ``Page`` becomes the HTML of the web look v2 (spec 1)."""

from __future__ import annotations

from typing import Any

from tl_web import present
from tl_web.app import _templates  # pyright: ignore[reportPrivateUsage]

layout = present.layout

_SRC = '{% from "page.html" import render_page with context %}{{ render_page(page) }}'


def _html(page: Any) -> str:
    return _templates.from_string(_SRC).render(
        page=page,
        tone=present.tone,
        state_tone=present.state_tone,
        page_blocks=present.page_blocks,
    )


def _doc(htmlkit: Any, page: Any) -> Any:
    return htmlkit.parse(_html(page))


PAGE = layout.Page(
    identity="P1-RFI-0001 · Pile clash",
    state="Answered",
    summary="Due 2026-10-23 · 2 files",
    sections=(
        layout.Section("Facts", (layout.Prop("Needed by", "2026-10-23"), layout.Prop("Owner", ""))),
        layout.Section(
            "Files",
            (
                layout.TableRow(("Name", "State"), ("a.pdf", layout.Cell("Overdue", "red"))),
                layout.TableRow(("Name", "State"), ("b.pdf", "plain")),
                "A line of prose",
            ),
        ),
        layout.Section("Links", (), note="No links"),
    ),
)


def test_identity_state_and_summary(htmlkit: Any) -> None:
    doc = _doc(htmlkit, PAGE)
    assert doc.root.find("h2", class_="tl-page-id").text() == "P1-RFI-0001 · Pile clash"
    badge = doc.root.find("span", class_="tl-badge tl-done")
    assert badge is not None and badge.text() == "Answered"
    assert doc.root.find("p", class_="tl-summary").text() == "Due 2026-10-23 · 2 files"


def test_each_state_tone() -> None:
    for state, tone in (
        ("Answered", "done"),
        ("Awaiting answer", "waiting"),
        ("Overdue", "bad"),
        ("Draft", "neutral"),
    ):
        assert f'class="tl-badge tl-{tone}">{state}<' in _html(layout.Page(state=state)), state


def test_sections_props_and_empty_value(htmlkit: Any) -> None:
    doc = _doc(htmlkit, PAGE)
    assert [s.find("h3").text() for s in doc.root.find_all("section", class_="tl-sec")] == [
        "Facts",
        "Files",
        "Links",
    ]
    dl = doc.root.find("dl", class_="tl-props")
    assert [n.text() for n in dl.find_all("dt")] == ["Needed by", "Owner"]
    assert [n.text() for n in dl.find_all("dd")] == ["2026-10-23", "—"]


def test_table_rows_group_and_styled_cell(htmlkit: Any) -> None:
    doc = _doc(htmlkit, PAGE)
    wrap = doc.root.find("div", class_="tl-mini-wrap")
    tables = wrap.find_all("table", class_="tl-mini")
    assert len(tables) == 1
    assert [th.text() for th in tables[0].find_all("th")] == ["Name", "State"]
    assert doc.rows() == [["a.pdf", "Overdue"], ["b.pdf", "plain"]]
    assert tables[0].find("span", class_="tl-badge tl-bad").text() == "Overdue"


def test_line_and_empty_section_note(htmlkit: Any) -> None:
    doc = _doc(htmlkit, PAGE)
    assert doc.root.find("p", class_="tl-line").text() == "A line of prose"
    assert doc.root.find("p", class_="tl-note").text() == "No links"


def test_values_are_escaped() -> None:
    page = layout.Page(
        identity="<script>x</script>",
        sections=(layout.Section("S", (layout.Prop("L", "<script>alert(1)</script>"),)),),
    )
    html = _html(page)
    assert "<script" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
