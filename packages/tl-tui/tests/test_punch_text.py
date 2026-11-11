"""The punch log and item text (P2-PUNCH-T06): cells, summary and page lines for each state."""

from __future__ import annotations

import re

import pytest
from fakes import FakeClient
from fakes_punch import seed_punch
from tl_mod_quality.views import PunchDetail
from tl_tui.layout import Prop, Section
from tl_tui.punch_text import (
    PUNCH_COLUMNS,
    PUNCH_DROP,
    PUNCH_RIGHT,
    punch_cells,
    punch_page,
    punch_summary,
)

PROJECT = "P123"
HEX32 = re.compile(r"[0-9a-f]{32}")
KEY_OPEN = "P123-PUN-0001"  # Open, category A, overdue, assignee Ferrari
KEY_CLEARED = "P123-PUN-0004"  # Cleared, no assignee
KEY_VERIFIED = "P123-PUN-0005"  # Verified, source-free, due in the future
KEY_VOID = "P123-PUN-0006"  # Void, reason "Raised in error"


@pytest.fixture
def client() -> FakeClient:
    fake = FakeClient()
    seed_punch(fake, PROJECT)
    return fake


def detail_of(client: FakeClient, key: str) -> PunchDetail:
    return client.get_punch_item(PROJECT, key)


def sections(page_sections: tuple[Section, ...]) -> dict[str, Section]:
    return {section.heading: section for section in page_sections}


def props_of(section: Section) -> dict[str, str]:
    return {item.label: item.value for item in section.items if isinstance(item, Prop)}


# --- the list cells ---------------------------------------------------------------------------


def test_columns_and_drop_order_are_the_ticket_names() -> None:
    assert PUNCH_COLUMNS == (
        "Number",
        "Subject",
        "State",
        "Cat",
        "Area",
        "System",
        "Due",
        "Assignee",
    )
    assert PUNCH_DROP == ("Assignee", "System", "Area")
    assert PUNCH_RIGHT == ()


def test_cells_for_each_state(client: FakeClient) -> None:
    rows = {row.key: row for row in client.list_punch_items(PROJECT).rows}
    assert punch_cells(rows[KEY_OPEN]) == (
        KEY_OPEN,
        "Punch item 1",
        "Open",
        "A",
        "L2",
        "HVAC",
        "2026-01-01",
        "Ferrari",
    )
    assert punch_cells(rows[KEY_CLEARED])[2:] == ("Cleared", "B", "L1", "Electrical", "—", "—")
    assert punch_cells(rows[KEY_VERIFIED])[2] == "Verified"
    assert punch_cells(rows[KEY_VOID])[2] == "Void"


def test_no_cell_or_line_carries_a_32_hex_id(client: FakeClient) -> None:
    rows = client.list_punch_items(PROJECT).rows
    for row in rows:
        assert not any(HEX32.search(cell) for cell in punch_cells(row))
        page = punch_page(detail_of(client, row.key))
        text = " ".join(
            [page.identity, page.state, page.summary]
            + [str(item) for section in page.sections for item in section.items]
        )
        assert not HEX32.search(text)
        assert row.id not in text


# --- the summary line -------------------------------------------------------------------------


def test_summary_of_the_whole_list(client: FakeClient) -> None:
    counts = client.get_punch_counts(PROJECT)
    assert punch_summary(counts, sum(counts.values()), 6) == (
        "6 punch items: 3 Open, 1 Cleared, 1 Verified, 1 Void"
    )


def test_summary_with_a_state_filter_and_overdue() -> None:
    counts = {"Open": 3, "Cleared": 1, "Verified": 1, "Void": 1}
    assert punch_summary(counts, 6, 2, state="Open") == "2 of 6 punch items, state Open"
    assert punch_summary(counts, 6, 1, overdue=True) == "1 of 6 punch items, overdue"
    assert (
        punch_summary(counts, 6, 1, state="Open", overdue=True)
        == "1 of 6 punch items, state Open, overdue"
    )


def test_the_overdue_mark_is_only_in_the_filter_text_when_asked() -> None:
    counts = {"Open": 3, "Cleared": 1, "Verified": 1, "Void": 1}
    assert "overdue" not in punch_summary(counts, 6, 6)
    assert "overdue" not in punch_summary(counts, 6, 6, state="Open")
    assert "overdue" in punch_summary(counts, 6, 1, overdue=True)


def test_an_empty_project_says_zero() -> None:
    assert punch_summary({}, 0, 0) == "0 punch items"


def test_a_single_item_is_singular() -> None:
    assert punch_summary({"Open": 1}, 1, 1) == "1 punch item: 1 Open, 0 Cleared, 0 Verified, 0 Void"


# --- the page: identity, state, summary and sections -----------------------------------------


def test_open_item_page_lines(client: FakeClient) -> None:
    page = punch_page(detail_of(client, KEY_OPEN), panel=True)
    assert page.identity == f"{KEY_OPEN} · Punch item 1"
    assert page.state == "Open · category A · due 2026-01-01"
    assert page.summary == "Ferrari · L2 · HVAC"
    assert [s.heading for s in page.sections] == ["Where", "Work", "History"]
    where = props_of(sections(page.sections)["Where"])
    assert where == {"Area": "L2", "System": "HVAC", "Raised from": "—"}


def test_a_list_page_has_no_summary_line(client: FakeClient) -> None:
    assert punch_page(detail_of(client, KEY_OPEN)).summary == ""


def test_cleared_item_shows_who_cleared_and_the_note(client: FakeClient) -> None:
    page = punch_page(detail_of(client, KEY_CLEARED))
    assert page.state == "Cleared · category B"
    work = props_of(sections(page.sections)["Work"])
    assert work["Cleared by"] == "uma · 2026-10-02"
    assert work["Clear note"] == "Tightened"
    assert work["Verified by"] == "—"


def test_verified_item_shows_the_verifier(client: FakeClient) -> None:
    page = punch_page(detail_of(client, KEY_VERIFIED))
    assert page.state == "Verified · category C · due 2099-12-31"
    assert props_of(sections(page.sections)["Work"])["Verified by"] == "rob · 2026-10-05"


def test_void_item_shows_the_void_reason_in_history(client: FakeClient) -> None:
    page = punch_page(detail_of(client, KEY_VOID))
    assert page.state == "Void · category A"
    history = props_of(sections(page.sections)["History"])
    assert history == {"Reopened": "0", "Void reason": "Raised in error"}


def test_a_reopen_reason_shows_only_when_reopened(client: FakeClient) -> None:
    detail = detail_of(client, KEY_OPEN)
    assert "Reopen reason" not in props_of(sections(punch_page(detail).sections)["History"])
    reopened = PunchDetail(
        **{**detail.__dict__, "reopen_count": 2, "last_reopen_reason": "Still leaks"}
    )
    history = props_of(sections(punch_page(reopened).sections)["History"])
    assert history["Reopened"] == "2"
    assert history["Reopen reason"] == "Still leaks"
