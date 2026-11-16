"""The permit register and screen text (P2-PTW-T11): cells, summary and page lines per state."""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime

import pytest
from fakes import FakeClient
from fakes_permits import seed_permits
from tl_mod_permits import commands as permit_commands
from tl_mod_permits.iso_views import GasRow
from tl_mod_permits.views import SHOWN_STATES, PermitRow
from tl_tui.layout import plain_lines
from tl_tui.permit_text import (
    ACTIONS,
    PERMIT_COLUMNS,
    PERMIT_DROP,
    PERMIT_RIGHT,
    permit_cells,
    permit_count,
    permit_page,
    permit_summary,
)

PROJECT = "P123"
HEX32 = re.compile(r"[0-9a-f]{32}")
KEY_REQUESTED = "P123-PTW-0001"  # Requested, no area, holder Rob
KEY_APPROVED = "P123-PTW-0002"  # Approved, hot work
KEY_ACTIVE = "P123-PTW-0003"  # Active, confined space, area A1, three gas tests, one precaution
KEY_LAPSED = "P123-PTW-0004"  # Lapsed, area A2, holder Ann
KEY_SUSPENDED = "P123-PTW-0005"  # Suspended, reason "Gas test failed"
KEY_HANDED_BACK = "P123-PTW-0006"  # Handed back
KEY_CLOSED = "P123-PTW-0007"  # Closed, hot work
KEY_REJECTED = "P123-PTW-0008"  # Rejected


@pytest.fixture
def client() -> FakeClient:
    fake = FakeClient()
    seed_permits(fake, PROJECT)
    return fake


def rows_of(client: FakeClient) -> dict[str, PermitRow]:
    return {row.key: row for row in client.list_permits(PROJECT).rows}


def page_of(client: FakeClient, key: str) -> list[str]:
    detail = client.get_permit(PROJECT, key)
    return plain_lines(permit_page(detail, client.list_gas_tests(PROJECT, key)))


def section_items(client: FakeClient, key: str, heading: str) -> list[object]:
    detail = client.get_permit(PROJECT, key)
    page = permit_page(detail, client.list_gas_tests(PROJECT, key))
    section = next(s for s in page.sections if s.heading == heading)
    return list(section.items)


# --- the register cells and summary ------------------------------------------------------------


def test_columns_and_drop_order_are_the_ticket_names() -> None:
    assert PERMIT_COLUMNS == (
        "Number",
        "Subject",
        "State",
        "Type",
        "Area",
        "Holder",
        "Valid until",
        "For",
    )
    assert PERMIT_DROP == ("For", "Holder", "Area")
    assert PERMIT_RIGHT == ()


def test_cells_for_an_active_permit_show_the_type_the_holder_and_the_validity(
    client: FakeClient,
) -> None:
    cells = permit_cells(rows_of(client)[KEY_ACTIVE])
    assert cells == (
        KEY_ACTIVE,
        "Permit 3",
        "Active",
        "Confined space",
        "A1",
        "Rob",
        "2026-12-01 18:00 UTC",
        "—",
    )


def test_a_permit_with_no_validity_shows_a_dash_and_a_stored_holder_stays_as_stored(
    client: FakeClient,
) -> None:
    requested = permit_cells(rows_of(client)[KEY_REQUESTED])
    assert requested[6] == "-"  # Valid until
    assert requested[5] == "Rob"  # Holder, a name as stored


def test_a_holder_that_is_an_actor_reads_by_name() -> None:
    row = PermitRow(
        id="PTW-9",
        key="P123-PTW-0009",
        subject="Permit 9",
        permit_type="general",
        state="Requested",
        area=None,
        holder="user:uma",
        issued_at=None,
        valid_until=None,
        revalidation_count=0,
        closed_by=None,
        for_key=None,
    )
    assert permit_cells(row)[5] == "uma"


def test_summary_counts_each_shown_state_from_the_rows_and_names_the_stops(
    client: FakeClient,
) -> None:
    rows = client.list_permits(PROJECT).rows
    assert permit_summary(rows, 8, 8) == (
        "8 permits: 1 Requested, 1 Approved, 1 Active, 1 Lapsed (STOP), 1 Suspended (STOP), "
        "1 Handed back, 1 Closed, 1 Rejected, 0 Cancelled"
    )


def test_summary_with_a_filter_names_the_filter() -> None:
    assert (
        permit_summary([], 8, 2, state="Active", permit_type="hot_work")
        == "2 of 8 permits, state Active, type hot work"
    )
    assert permit_summary([], 0, 0) == "0 permits"
    assert permit_count(1) == "1 permit"


# --- the page: identity, state line, sections --------------------------------------------------


def test_each_state_has_its_identity_and_state_line(client: FakeClient) -> None:
    expected = {
        KEY_REQUESTED: ("Permit 1", "Requested · general"),
        KEY_APPROVED: ("Permit 2", "Approved · hot work"),
        KEY_ACTIVE: ("Permit 3", "Active · confined space · until 18:00 UTC"),
        KEY_LAPSED: ("Permit 4", "Lapsed · STOP, revalidate"),
        KEY_SUSPENDED: ("Permit 5", "Suspended · STOP"),
        KEY_HANDED_BACK: ("Permit 6", "Handed back · general"),
        KEY_CLOSED: ("Permit 7", "Closed · hot work"),
        KEY_REJECTED: ("Permit 8", "Rejected · general"),
    }
    for key, (subject, state) in expected.items():
        lines = page_of(client, key)
        assert lines[0] == f"{key} · {subject}"
        assert state in lines, f"{key} state line"


def test_lapsed_and_suspended_pages_say_stop_in_the_state_line(client: FakeClient) -> None:
    assert "STOP" in page_of(client, KEY_LAPSED)[1]
    assert "STOP" in page_of(client, KEY_SUSPENDED)[1]
    assert "STOP" not in page_of(client, KEY_ACTIVE)[1]


def test_no_page_line_carries_a_32_hex_id(client: FakeClient) -> None:
    for key in rows_of(client):
        for line in page_of(client, key):
            assert HEX32.search(line) is None, line


def test_the_sections_are_in_order_with_the_gas_tests_before_the_history(
    client: FakeClient,
) -> None:
    detail = client.get_permit(PROJECT, KEY_ACTIVE)
    page = permit_page(detail, client.list_gas_tests(PROJECT, KEY_ACTIVE))
    assert [s.heading for s in page.sections] == [
        "Where",
        "Work",
        "Approvals",
        "Gas tests",
        "History",
    ]


def test_the_gas_tests_are_newest_first_and_show_no_readings(client: FakeClient) -> None:
    gas = section_items(client, KEY_ACTIVE, "Gas tests")
    assert gas == ["Pass 08:20 UTC by uma", "Pass 07:40 UTC by uma", "Fail 07:10 UTC by uma"]
    text = "\n".join(str(item) for item in gas)
    for reading in ("35", "20.9", "MX6", "ppm", "%"):
        assert reading not in text


def test_a_permit_with_no_gas_test_says_none_taken(client: FakeClient) -> None:
    detail = client.get_permit(PROJECT, KEY_REQUESTED)
    page = permit_page(detail, [])
    gas = next(section for section in page.sections if section.heading == "Gas tests")
    assert gas.items == ()
    assert gas.note == "none taken"
    assert "none taken" in plain_lines(page)


def test_at_most_five_gas_tests_show_on_the_page() -> None:
    gas = [
        GasRow(
            key=f"P123-GAS-{n:04d}",
            taken_at=datetime(2026, 12, 1, 6, n, tzinfo=UTC),
            result="pass",
            tester="user:uma",
            instrument_text=None,
            o2_pct=None,
            lel_pct=None,
            h2s_ppm=None,
            co_ppm=None,
            note=None,
        )
        for n in range(1, 8)
    ]
    detail = FakeClient()  # any permit detail will do: the page reads only its row
    seed_permits(detail, PROJECT)
    page = permit_page(detail.get_permit(PROJECT, KEY_ACTIVE), gas)
    items = next(s for s in page.sections if s.heading == "Gas tests").items
    assert len(items) == 5
    assert items[0] == "Pass 06:07 UTC by uma"


def test_the_approvals_show_the_ticked_precautions_and_the_history_the_reasons(
    client: FakeClient,
) -> None:
    assert any("1 ticked" in line for line in page_of(client, KEY_ACTIVE))
    lines = page_of(client, KEY_SUSPENDED)
    assert any("Suspend reason" in line and "Gas test failed" in line for line in lines)


def test_the_state_table_equals_the_states_in_the_command_docstrings() -> None:
    def docstring_states(name: str) -> set[str]:
        doc = inspect.getdoc(getattr(permit_commands, name)) or ""
        head = doc.split(" to ")[0]  # the from-states come before the first " to "
        return {state for state in SHOWN_STATES if state in head}

    assert set(ACTIONS) == {
        "ApprovePermit",
        "RejectPermit",
        "SuspendPermit",
        "ResumePermit",
        "RevalidatePermit",
        "HandBackPermit",
        "ClosePermit",
    }
    for name, states in ACTIONS.items():
        assert set(states) == docstring_states(name), name
