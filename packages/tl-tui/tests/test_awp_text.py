"""The CWP text and its Details renderer (T05a, D38), on the ``seed_awp`` fake."""

from __future__ import annotations

from decimal import Decimal

from fakes import FakeClient
from fakes_awp import PROJECT, seed_awp
from tl_api.routes.awp import CwpDetailView, TimelineRow
from tl_mod_schedule.resolver import ActivityLink, Resolution
from tl_tui.awp_text import (
    cwp_cells,
    cwp_page,
    cwp_rows,
    cwp_summary,
    group_by_cwa,
    hours_text,
)
from tl_tui.details import details_for
from tl_tui.display import DisplayMode, Labels
from tl_tui.layout import plain_lines

SECTIONS = ("Scope", "Allocation", "References", "Schedule", "Timeline", "Files and links")
WIDTHS = (80, 170)


def need(ok: bool, what: str) -> None:
    assert ok, what


def fixture() -> tuple[FakeClient, list, CwpDetailView]:
    client = FakeClient()
    seed_awp(client)
    rows = client.list_cwps(PROJECT)
    seed = client.get_cwp(PROJECT, rows[0].number)
    detail = CwpDetailView(
        **seed.model_dump(exclude={"link_count", "file_count", "timeline"}),
        link_count=0,
        file_count=0,
        timeline=[],
    )
    return client, rows, detail


def check_cells(rows: list) -> None:
    cells = cwp_cells(rows[0])
    need(len(cells) == 8, f"expected 8 cells, got {len(cells)}")
    need(cells[-1] in ("✓", "—"), f"Allocated cell is {cells[-1]!r}")
    allocated = cwp_cells(rows[0].model_copy(update={"allocated": True}))
    need(allocated[-1] == "✓", "an allocated row must read ✓")
    need(hours_text(Decimal("4200")) == "4 200", "4200 must read 4 200")
    need(hours_text(Decimal("12.50")) == "12.5", "12.50 must read 12.5")
    need(hours_text(None) == "—", "None must read —")


def check_group_by_cwa(client: FakeClient, rows: list) -> None:
    orphan = rows[0].model_copy(update={"cwa": None, "number": "P123-CWP-0009"})
    groups = group_by_cwa([orphan, *reversed(rows)])
    codes = [code for code, _ in groups]
    need(codes == ["A1", "A2", "—"], f"group order is {codes}")
    first = [row.number for row in groups[0][1]]
    need(first == sorted(first), f"rows of a group must keep number order: {first}")


def check_page(detail: CwpDetailView) -> None:
    for width in WIDTHS:
        lines = plain_lines(cwp_page(detail, panel=True), width=width)
        for heading in SECTIONS:
            need(heading in [line.strip() for line in lines], f"no heading {heading!r}")
        need(
            not any(a == "" and b == "" for a, b in zip(lines, lines[1:], strict=False)),
            "two blank lines in a row",
        )
        starts = [i for i, line in enumerate(lines) if line.strip() in SECTIONS]
        need(all(lines[i - 1] == "" for i in starts[1:]), "a heading without a blank line before")
    panel = cwp_page(detail, panel=True)
    need(panel.summary == cwp_summary(detail) and panel.summary != "", "panel has no summary")
    many = [
        ActivityLink(
            link_id=f"L{n}",
            status="active",
            pin=None,
            reason=None,
            ref_key=f"ACT-{n}",
            resolution=Resolution(
                state="current",
                schedule_code="SCH",
                activity_id=f"ACT-{n}",
                snapshot_id=None,
                snapshot_number=None,
                data_date=None,
                activity=None,
            ),
        )
        for n in range(6)
    ]
    busy = detail.model_copy(update={"activities": many})
    schedule_rows = [row for row in cwp_rows(busy) if row.section == "Schedule" and row.cells]
    need(len(schedule_rows) == 6, "the full Details keeps all six activity rows")
    panel_lines = plain_lines(cwp_page(busy, panel=True), width=80)
    shown = [line for line in panel_lines if line.strip().startswith("ACT-")]
    need(len(shown) <= 4, f"panel shows {len(shown)} schedule rows")


def check_details(client: FakeClient, rows: list) -> None:
    number = rows[0].number
    record = {"type": "awp.CWP", "key": number}
    plain = details_for(client, PROJECT, record, Labels(), DisplayMode())
    sections = {row.section for row in plain}
    need(set(SECTIONS) <= sections, f"Details sections are {sorted(sections)}")
    admin_mode = DisplayMode()
    admin_mode.technical = True
    technical = details_for(client, PROJECT, record, Labels(), admin_mode)
    need(any(row.label == "Key" for row in technical), "technical mode shows the key")
    need(not any(row.label == "Key" for row in plain), "plain mode hides the key")


def test_cells() -> None:
    check_cells(fixture()[1])


def test_group_by_cwa() -> None:
    client, rows, _ = fixture()
    check_group_by_cwa(client, rows)


def test_page() -> None:
    check_page(fixture()[2])


def test_details() -> None:
    client, rows, _ = fixture()
    check_details(client, rows)


def test_an_empty_timeline_keeps_its_heading_and_says_so() -> None:
    """D38: the Timeline heading stays and the note reads `No events recorded`."""
    _, _, detail = fixture()
    lines = plain_lines(cwp_page(detail), width=80)
    stripped = [line.strip() for line in lines]
    at = stripped.index("Timeline")
    assert stripped[at + 1] == "No events recorded"
    busy = detail.model_copy(
        update={
            "timeline": [TimelineRow(date="2026-10-09", who="user:sue", event="created", note="")]
        }
    )
    assert "No events recorded" not in plain_lines(cwp_page(busy), width=80)


def test_the_budget_and_the_discipline_are_in_the_summary_and_the_budget_in_scope() -> None:
    _, _, detail = fixture()
    summary = cwp_summary(detail)
    assert "PIP" in summary
    assert "40 h" in summary
    assert "CWA A1" in summary
    scope = [row for row in cwp_rows(detail) if row.section == "Scope"]
    assert ("Budget hours", "40 h") in [(row.label, row.value) for row in scope]
    assert ("Contractor", "—") in [(row.label, row.value) for row in scope]


def test_the_discipline_label_comes_from_the_code_list_when_loaded_else_the_code() -> None:
    client, rows, detail = fixture()
    labels = Labels(code_labels={"discipline": {"PIP": "Piping"}})
    assert cwp_cells(rows[0])[3] == "PIP"
    assert cwp_cells(rows[0], labels)[3] == "Piping"
    assert plain_lines(cwp_page(detail, labels, panel=True), width=170)[2].startswith("Piping")
    assert plain_lines(cwp_page(detail, panel=True), width=170)[2].startswith("PIP")
    other = Labels(code_labels={"discipline": {"CIV": "Civil"}})
    assert cwp_cells(rows[0], other)[3] == "PIP"  # a code the list lacks reads as itself
    del client


def test_the_register_row_has_eight_cells_in_column_order() -> None:
    _, rows, _ = fixture()
    cells = cwp_cells(rows[0])
    assert cells[0] == rows[0].number
    assert cells[2] == "Released for IWP development"
    assert cells[4] == "A1"
    assert cells[5] == "2026-11-01"
    assert cells[6] == "40"
    assert len(cells) == 8
