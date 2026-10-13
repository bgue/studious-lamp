"""The text of the document screens: rows, detail, re-pin summary, choices (P1-I2)."""

from __future__ import annotations

from fakes import FakeClient
from tl_mod_documents.views import DocumentView
from tl_tui.document_text import (
    COLUMNS,
    current_text,
    detail_lines,
    issued_choices,
    link_line,
    next_choice,
    parse_recipients,
    repin_lines,
    row_cells,
    stale_links,
    summary_line,
)


def docs() -> dict[str, DocumentView]:
    client = FakeClient()
    client.seed_documents("P123")
    return {d: client.get_document("P123", d) for d in ("ISO-1234", "ISO-2000", "ISO-3000")}


def test_a_row_has_one_cell_per_column() -> None:
    found = docs()
    assert len(COLUMNS) == 6
    assert row_cells(found["ISO-1234"]) == (
        "ISO-1234", "Issued", "B(IFC)", "ISO", "PIP", "Isometric, line 47-P-101"
    )  # fmt: skip
    assert row_cells(found["ISO-2000"])[2] == "-" and current_text(found["ISO-2000"]) == "-"


def test_the_detail_lists_revisions_files_and_the_links_with_the_stale_one_marked() -> None:
    lines = detail_lines(docs()["ISO-1234"])
    assert lines[0] == "ISO-1234  Isometric, line 47-P-101"
    assert lines[1] == "state Issued  |  type ISO  |  discipline PIP  |  scheme alpha"
    assert lines[2] == "current B(IFC)"
    assert "revisions:" in lines
    assert "  A  Issued  IFR review 2026-10-01  pdf" in lines
    assert "  B  Issued  IFC construction 2026-10-10  current  pdf" in lines
    assert "links (1 stale):" in lines
    assert "  ! 47-FV-1001 (core.Record) pin A, current B (newer B)" in lines
    assert "    47-FV-1002 (core.Record) floats" in lines


def test_a_document_with_no_revision_says_so() -> None:
    lines = detail_lines(docs()["ISO-2000"])
    assert "no revisions yet" in lines and not any(line.startswith("links") for line in lines)


def test_only_a_stale_pinned_link_can_be_re_pinned() -> None:
    found = docs()["ISO-1234"]
    assert [link.link_id for link in stale_links(found)] == ["LINK-STALE"]
    assert link_line(found.links[1]).strip().endswith("floats")


def test_the_repin_dialog_body_quotes_the_module() -> None:
    client = FakeClient()
    client.seed_documents("P123")
    link = client.get_document("P123", "ISO-1234").links[0]
    diff = client.document_diff("P123", "ISO-1234", "A", "B")
    assert repin_lines(link, diff) == [
        "Re-pin 47-FV-1001 to ISO-1234",
        "from A (IFR) to B (IFC)",
        "",
        "What changed:",
        "  status IFR to IFC",
        "  issued B (IFC, 2026-10-10): For construction",
        "  pdf changed: sheet-A.pdf, 1 KB, 3 pages to sheet-B.pdf, 2 KB, 5 pages",
    ]


def test_a_transmittal_is_offered_the_issued_revisions_newest_first() -> None:
    found = docs()
    assert issued_choices(found["ISO-1234"]) == [
        ("ISO-1234@B IFC", "REV-ISO-1234-B"),
        ("ISO-1234@A IFR", "REV-ISO-1234-A"),
    ]
    assert issued_choices(found["ISO-2000"]) == []


def test_recipients_are_read_from_one_line() -> None:
    assert parse_recipients("Site:Acme:site@acme.test; Ana ;; Bo::bo@x.test") == [
        ("Site", "Acme", "site@acme.test"),
        ("Ana", None, None),
        ("Bo", None, "bo@x.test"),
    ]
    assert parse_recipients("  ") == []


def test_the_filters_cycle_through_the_values_present() -> None:
    assert next_choice(None, ["Issued", "Registered", "Issued"]) == "Issued"
    assert next_choice("Issued", ["Issued", "Registered"]) == "Registered"
    assert next_choice("Registered", ["Issued", "Registered"]) is None
    assert next_choice("Gone", ["Issued"]) is None
    assert next_choice(None, []) is None


def test_the_summary_line_names_each_filter() -> None:
    assert summary_line(3, 3, state=None, doc_type=None, include_void=False, text="") == (
        "3 of 3 documents"
    )
    assert summary_line(1, 3, state="Issued", doc_type="ISO", include_void=True, text=" x ") == (
        '1 of 3 documents  state Issued  type ISO  incl. void  filter "x"'
    )
