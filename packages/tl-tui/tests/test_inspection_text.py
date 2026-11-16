"""The inspection log and screen text (P2-INSP-T10): cells, summary and page lines per state."""

from __future__ import annotations

import re

import pytest
from fakes import FakeClient
from fakes_insp import seed_inspections
from tl_mod_quality import insp_views
from tl_tui.inspection_text import (
    INSPECTION_COLUMNS,
    INSPECTION_DROP,
    INSPECTION_RIGHT,
    inspection_cells,
    inspection_page,
    inspection_summary,
)
from tl_tui.layout import Prop, Section, plain_lines

PROJECT = "P123"
HEX32 = re.compile(r"[0-9a-f]{32}")
KEY_PLANNED = "P123-INS-0001"  # Planned, hold, area L1
KEY_SCHEDULED = "P123-INS-0002"  # Scheduled, hold, inspector M. Okafor
KEY_DONE = "P123-INS-0003"  # Done, witness, Reject, one punch item, one failed answer
KEY_VERIFIED = "P123-INS-0004"  # Verified, review, Pass
KEY_CANCELLED = "P123-INS-0005"  # Cancelled, surveillance, reason "Area closed"


@pytest.fixture
def client() -> FakeClient:
    fake = FakeClient()
    seed_inspections(fake, PROJECT)
    return fake


def rows_of(client: FakeClient) -> dict[str, insp_views.InspectionRow]:
    return {row.key: row for row in client.list_inspections(PROJECT).rows}


def detail_of(client: FakeClient, key: str) -> insp_views.InspectionDetail:
    return client.get_inspection(PROJECT, key)


def sections(page_sections: tuple[Section, ...]) -> dict[str, Section]:
    return {section.heading: section for section in page_sections}


def props_of(section: Section) -> dict[str, str]:
    return {item.label: item.value for item in section.items if isinstance(item, Prop)}


# --- the list cells and summary ----------------------------------------------------------------


def test_columns_and_drop_order_are_the_ticket_names() -> None:
    assert INSPECTION_COLUMNS == (
        "Number",
        "Title",
        "State",
        "Point",
        "Result",
        "Scheduled",
        "Inspector",
        "Area",
    )
    assert INSPECTION_DROP == ("Inspector", "Area", "Scheduled")
    assert INSPECTION_RIGHT == ()


def test_cells_for_each_state(client: FakeClient) -> None:
    rows = rows_of(client)
    assert inspection_cells(rows[KEY_PLANNED]) == (
        KEY_PLANNED,
        "Inspection 1",
        "Planned",
        "hold",
        "-",
        "—",
        "—",
        "L1",
    )
    assert inspection_cells(rows[KEY_SCHEDULED])[2:] == (
        "Scheduled",
        "hold",
        "-",
        "2026-12-01",
        "M. Okafor",
        "L2",
    )
    assert inspection_cells(rows[KEY_DONE])[2:5] == ("Done", "witness", "Reject")
    assert inspection_cells(rows[KEY_VERIFIED])[2:5] == ("Verified", "review", "Pass")
    assert inspection_cells(rows[KEY_CANCELLED])[2:5] == ("Cancelled", "surveillance", "-")


def test_summary_counts_the_rows_held_and_names_a_filter(client: FakeClient) -> None:
    rows = client.list_inspections(PROJECT).rows
    assert (
        inspection_summary(rows, 6, 6)
        == "6 inspections: 2 Planned, 1 Scheduled, 1 Done, 1 Verified, 1 Cancelled"
    )
    assert inspection_summary(rows, 0, 0) == "0 inspections"
    assert (
        inspection_summary(rows, 6, 2, state="Planned", point="hold")
        == "2 of 6 inspections, state Planned, point hold"
    )
    counts = {"Planned": 2, "Scheduled": 1, "Done": 1, "Verified": 1, "Cancelled": 1}
    assert inspection_summary(counts, 6, 6).startswith("6 inspections: 2 Planned")


# --- the screen's page -------------------------------------------------------------------------


def test_each_state_has_an_identity_and_a_state_line(client: FakeClient) -> None:
    expected = {
        KEY_PLANNED: "Planned · hold point",
        KEY_SCHEDULED: "Scheduled · hold point",
        KEY_DONE: "Done · witness point · Reject",
        KEY_VERIFIED: "Verified · review point · Pass",
        KEY_CANCELLED: "Cancelled · surveillance point",
    }
    for key, state in expected.items():
        page = inspection_page(detail_of(client, key))
        assert page.identity == f"{key} · {detail_of(client, key).row.title}"
        assert page.state == state


def test_the_result_section_lists_the_failed_question_by_text_and_note(client: FakeClient) -> None:
    page = inspection_page(detail_of(client, KEY_DONE))
    result = sections(page.sections)["Result"]
    assert props_of(result)["Gauge fitted?"] == "Gauge missing"
    text = "\n".join(plain_lines(page))
    assert "Gauge fitted?" in text and "q1" not in text


def test_a_passing_inspection_has_no_failed_line(client: FakeClient) -> None:
    result = sections(inspection_page(detail_of(client, KEY_VERIFIED)).sections)["Result"]
    assert "Gauge fitted?" not in props_of(result)


def test_the_punch_keys_appear_in_their_section(client: FakeClient) -> None:
    page = inspection_page(detail_of(client, KEY_DONE))
    punch = sections(page.sections)["Punch"]
    assert [item for item in punch.items if isinstance(item, str)] == ["P123-PUN-0001"]
    none = sections(inspection_page(detail_of(client, KEY_PLANNED)).sections)["Punch"]
    assert none.note == "No punch items"


def test_no_inspection_page_line_carries_a_record_id(client: FakeClient) -> None:
    for key in (KEY_PLANNED, KEY_SCHEDULED, KEY_DONE, KEY_VERIFIED, KEY_CANCELLED):
        page = inspection_page(detail_of(client, key), technical=False, panel=False)
        for line in plain_lines(page):
            assert not HEX32.search(line)
        for row in client.list_inspections(PROJECT).rows:
            assert all(not HEX32.search(cell) for cell in inspection_cells(row))


def test_the_plan_and_history_lines_are_the_pinned_facts(client: FakeClient) -> None:
    plan = sections(inspection_page(detail_of(client, KEY_SCHEDULED)).sections)["Plan"]
    assert props_of(plan)["Checklist"] == "P123-CHK-0002, version 1"
    assert props_of(plan)["Inspector"] == "M. Okafor"
    history = sections(inspection_page(detail_of(client, KEY_CANCELLED)).sections)["History"]
    assert props_of(history)["Cancel reason"] == "Area closed"
    assert props_of(history)["Reinspection of"] == "—"
