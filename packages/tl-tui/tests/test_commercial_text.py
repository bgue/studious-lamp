"""What the Commercial register shows, as text (P1-I6-T07b)."""

from __future__ import annotations

from fakes import FakeClient
from fakes_correspondence import seed_domains
from tl_mod_correspondence.reports_commercial import CurrencyTotal
from tl_tui import commercial_text as ct


def seeded() -> FakeClient:
    client = FakeClient()
    seed_domains(client)
    return client


def test_a_register_row_has_eleven_cells_in_the_order_of_the_columns() -> None:
    register = seeded().list_commercial("P123")
    cells = {line.number: ct.commercial_cells(line) for line in register.lines}
    assert all(len(c) == len(ct.COMMERCIAL_COLUMNS) == 11 for c in cells.values())
    assert ct.COMMERCIAL_COLUMNS[:4] == ("Number", "Subject", "State", "Kind")
    assert cells["P123-EW-0001"] == (
        "P123-EW-0001",
        "Early warning: routing change",
        "Awaiting assessment",
        "early_warning",
        "2026-10-12",
        "2026-10-26",
        "-4",
        "LATE",
        "USD",
        "12500.00",
        "—",
    )
    assert cells["P123-CN-0001"][1:3] == ("Change notice: cable tray", "Agreed")
    assert cells["P123-CN-0001"][6:] == ("10", "met", "USD", "12500.00", "9000.00")


def test_the_bar_is_late_before_anything_else_and_a_missing_bar_is_a_dash() -> None:
    one, two = seeded().list_commercial("P123").lines
    assert [ct.bar_text(x) for x in (one, two)] == ["LATE", "met"]
    running = two.model_copy(update={"time_bar_state": "running"})
    assert ct.bar_text(running) == "running"
    none = two.model_copy(update={"time_bar_state": None, "time_bar_days_left": None})
    assert ct.bar_text(none) == "—" and ct.commercial_cells(none)[6] == "—"
    late = running.model_copy(update={"time_bar_late": True})
    assert ct.bar_text(late) == "LATE"


def test_the_status_has_no_column_and_the_panel_carries_it_with_a_space() -> None:
    line = seeded().list_commercial("P123").lines[0]
    part = line.model_copy(update={"assessment_status": "partially_agreed", "currency": None})
    cells = ct.commercial_cells(part)
    assert len(cells) == 11 and cells[8] == "—"
    assert not any("partially" in cell for cell in cells)
    view = (
        seeded()
        .get_commercial("P123", "P123-CN-0001")
        .model_copy(update={"assessment_status": "partially_agreed"})
    )
    lines = ct.commercial_lines(view)
    assert "Status          Partially agreed" in lines
    assert "Assessed value  9000.00 USD" in lines
    assert "Note            as stated" in lines


def test_the_summary_counts_the_bars_and_shows_each_currency_on_its_own_part() -> None:
    client = seeded()
    register = client.list_commercial("P123")
    assert ct.commercial_summary(register) == ("2 notices | time bars running 0, late 1")
    with_totals = register.model_copy(
        update={
            "totals": [
                CurrencyTotal(currency="EUR", count=1, estimated="100.00", assessed="0.00"),
                CurrencyTotal(currency="USD", count=2, estimated="25000.00", assessed="9000.00"),
            ],
            "time_bars_running": 1,
        }
    )
    assert ct.commercial_summary(with_totals, only_open=True, time_bars_only=True) == (
        "2 notices | time bars running 1, late 1"
        " | EUR: 1 estimated 100.00 assessed 0.00"
        " | USD: 2 estimated 25000.00 assessed 9000.00"
        " | filter: open, time bars"
    )
    one = register.model_copy(update={"lines": register.lines[:1]})
    assert ct.commercial_summary(one).startswith("1 notice | ")
    assert ct.commercial_summary(register, time_bars_only=True).endswith("| filter: time bars")


def test_the_panel_shows_the_figures_the_basis_the_origin_and_the_assessment() -> None:
    client = seeded()
    warning = ct.commercial_lines(client.get_commercial("P123", "P123-EW-0001"))
    assert warning[0] == "P123-EW-0001 · Early warning: routing change"
    assert warning[1] == "Awaiting assessment"
    assert warning[2] == "Early warning · aware 2026-10-12 · 12500.00 USD"
    assert "Clause           CT-1/20.1" in warning
    assert "Issued           2026-10-30" in warning
    assert "Estimated        12500.00 USD" in warning
    assert "Estimated hours  240.0" in warning
    assert "Schedule impact  3 days" in warning
    assert "Cost codes       2.3.1=12500.00" in warning
    assert warning[warning.index("Basis") + 1] == "Clause 20.1"
    assert "Escalated from   P123-RFI-0001" in warning
    assert "Status          —" in warning
    assert not any(x.startswith("Clocks") for x in warning)
    agreed = ct.commercial_lines(client.get_commercial("P123", "P123-CN-0001"))
    assert "Status          Agreed" in agreed
    assert "Assessed on     2026-10-20" in agreed
    assert "Assessed value  9000.00 USD" in agreed
    assert "Note            as stated" in agreed
    assert not any(x.startswith("Escalated") for x in agreed)


def test_an_item_without_figures_shows_dashes_and_the_hours_of_a_cost_code() -> None:
    view = (
        seeded()
        .get_commercial("P123", "P123-EW-0001")
        .model_copy(
            update={
                "currency": None,
                "estimated_value": None,
                "estimated_hours": None,
                "schedule_impact_days": None,
                "entitlement_basis": None,
                "derived_from_number": None,
                "cost_code_impacts": [{"cost_code": "2.3.1", "amount": None, "hours": "40.0"}],
            }
        )
    )
    lines = ct.commercial_lines(view)
    assert "Estimated        —" in lines
    assert "Estimated hours  —" in lines
    assert "Schedule impact  —" in lines
    assert "Cost codes       2.3.1=40.0" in lines
    assert "Basis" not in lines
    assert not any(x.startswith("Escalated") for x in lines)


def test_a_row_with_nothing_stated_shows_a_dash_in_every_empty_cell() -> None:
    line = (
        seeded()
        .list_commercial("P123")
        .lines[0]
        .model_copy(
            update={
                "aware_on": None,
                "time_bar_due": None,
                "time_bar_days_left": None,
                "time_bar_state": None,
                "time_bar_late": False,
                "currency": None,
                "estimated_value": None,
                "assessed_value": None,
                "assessment_status": None,
            }
        )
    )
    cells = ct.commercial_cells(line)
    assert cells[4:] == ("—",) * 7


def test_an_item_with_no_clause_says_so() -> None:
    view = seeded().get_commercial("P123", "P123-CN-0001").model_copy(update={"clause": None})
    assert "Clause           —" in ct.commercial_lines(view)
