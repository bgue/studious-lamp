"""The scaffold register and record text as pure functions (P2-I4B-T07b). Rows come from the
`FakeClient` the T09b2 fake serves (`seed_scaffolds`); `today` is fixed, never the clock."""

from __future__ import annotations

from fakes import FakeClient
from fakes_scaffold import seed_scaffolds
from tl_mod_scaffold import views as scaffold_views
from tl_tui.layout import plain_lines
from tl_tui.scaffold_text import (
    SCAFFOLD_COLUMNS,
    SCAFFOLD_DROP,
    detail_page,
    export_filename,
    register_page,
    scaffold_cells,
    scaffold_summary,
)

PROJECT = "P123"
TODAY = "2026-11-15"  # fixed: the seeded due days are before it (2026-01-01, 2026-10-09)


def seeded() -> tuple[FakeClient, list[scaffold_views.ScaffoldRow]]:
    client = FakeClient()
    keys = seed_scaffolds(client, PROJECT)
    page = client.list_scaffolds(PROJECT)
    assert [row.key for row in page.rows] == keys
    return client, page.rows


def detail_of(client: FakeClient, key: str) -> scaffold_views.ScaffoldDetail:
    return client.get_scaffold(PROJECT, key)


def test_the_columns_and_the_drop_order_are_the_ticket_order() -> None:
    assert SCAFFOLD_COLUMNS == (
        "Number",
        "Subject",
        "State",
        "Tag",
        "Last inspected",
        "Next due",
        "Location",
    )
    assert SCAFFOLD_DROP == ("Location", "Last inspected", "Subject")


def test_a_row_has_seven_cells_and_the_tag_is_its_colour_word() -> None:
    _, rows = seeded()
    in_use = next(row for row in rows if row.state == "In Use")
    assert scaffold_cells(in_use) == (
        in_use.key,
        "Scaffold 4",
        "In Use",
        "green",
        "2026-01-01",
        "2099-12-31",
        "Unit 4",
    )


def test_an_untagged_row_shows_the_dash_for_each_empty_value() -> None:
    _, rows = seeded()
    designed = next(row for row in rows if row.state == "Designed")
    assert scaffold_cells(designed)[3:6] == ("—", "—", "—")


def test_the_summary_counts_the_states_and_the_overdue_with_a_fixed_today() -> None:
    _, rows = seeded()
    assert scaffold_summary(rows, len(rows), today=TODAY) == (
        "5 scaffolds: 1 Designed, 1 Erecting, 1 Inspected, 1 In Use, 1 Modify; 2 overdue"
    )
    # the same rows read on a day before the due days: nothing is overdue
    assert scaffold_summary(rows, len(rows), today="2025-01-01") == (
        "5 scaffolds: 1 Designed, 1 Erecting, 1 Inspected, 1 In Use, 1 Modify"
    )


def test_the_summary_counts_the_total_and_names_one_scaffold_in_the_singular() -> None:
    _, rows = seeded()
    assert scaffold_summary(rows[:1], 1, today=TODAY) == "1 scaffold: 1 Designed"


def test_an_empty_register_reads_zero_scaffolds() -> None:
    cells, summary = register_page([], 0, today=TODAY)
    assert cells == []
    assert summary == "0 scaffolds"


def test_register_page_gives_the_cells_of_each_row_in_order() -> None:
    _, rows = seeded()
    cells, summary = register_page(rows, len(rows), today=TODAY)
    assert [row[0] for row in cells] == [row.key for row in rows]
    assert all(len(row) == len(SCAFFOLD_COLUMNS) for row in cells)
    assert summary.startswith("5 scaffolds: ")


def test_a_detail_without_inspections_has_the_note_and_no_reasons() -> None:
    client, _ = seeded()
    page = detail_page(detail_of(client, "P123-SCF-0001"))
    names = [section.heading for section in page.sections]
    assert "Reasons" not in names
    inspections = next(section for section in page.sections if section.heading == "Inspections")
    assert inspections.items == ()
    assert inspections.note == "No inspections yet"


def test_a_detail_with_inspections_lists_them_oldest_first_in_words() -> None:
    client, _ = seeded()
    page = detail_page(detail_of(client, "P123-SCF-0005"))
    inspections = next(section for section in page.sections if section.heading == "Inspections")
    rows = [item.cells for item in inspections.items]  # type: ignore[union-attr]
    assert rows == [
        ("2026-09-01", "uma", "Pass", "green", "—"),
        ("2026-10-02", "uma", "Fail", "red", "Cracked toe board"),
    ]
    assert inspections.items[0].columns == ("Date", "Inspector", "Result", "Tag", "Note")  # type: ignore[union-attr]


def test_the_reasons_show_when_present_and_only_then() -> None:
    client, _ = seeded()
    page = detail_page(detail_of(client, "P123-SCF-0005"))
    reasons = next(section for section in page.sections if section.heading == "Reasons")
    assert [(item.label, item.value) for item in reasons.items] == [  # type: ignore[union-attr]
        ("Modify reason", "Cracked toe board")
    ]


def test_the_detail_has_the_property_lines_in_order_with_values_and_dashes() -> None:
    client, _ = seeded()
    page = detail_page(detail_of(client, "P123-SCF-0004"))
    labels = [
        (section.heading, [item.label for item in section.items])  # type: ignore[union-attr]
        for section in page.sections[:3]
    ]
    assert labels[0] == (
        "Status",
        ["Tag", "Tagged on", "Last inspected", "Next due"],
    )
    assert labels[1] == ("Where", ["Location", "Elevation", "Gridline"])
    assert labels[2] == ("Use", ["Load class", "Requested from", "Serves"])
    values = {item.label: item.value for section in page.sections[:3] for item in section.items}  # type: ignore[union-attr]
    assert values["Tag"] == "green"
    assert values["Location"] == "Unit 4"
    assert values["Elevation"] == "+12.0"
    assert values["Requested from"] == "—"  # empty: the dash, never a typed one
    assert values["Serves"] == "—"


def test_the_identity_and_the_state_lines_name_the_scaffold_without_its_id() -> None:
    client, rows = seeded()
    page = detail_page(detail_of(client, "P123-SCF-0004"))
    assert page.identity == "P123-SCF-0004 · Scaffold 4"
    assert page.state == "In Use"
    text = "\n".join(plain_lines(page))
    for row in rows:
        assert row.id not in text.split()  # the record id is carried, never printed


def test_the_ids_are_never_printed_in_the_register_text() -> None:
    _, rows = seeded()
    cells, summary = register_page(rows, len(rows), today=TODAY)
    text = "\n".join(" ".join(row) for row in cells) + summary
    for row in rows:
        assert row.id not in text.split()


def test_the_export_file_is_named_for_the_project_and_format() -> None:
    assert export_filename("P123", "csv") == "scaffolds-P123.csv"
    assert export_filename("P123", "jsonl") == "scaffolds-P123.jsonl"
