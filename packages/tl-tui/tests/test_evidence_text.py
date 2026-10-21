"""What the evidence view shows, as text (P1-I6)."""

from __future__ import annotations

from datetime import date

from fakes import FakeClient
from fakes_correspondence import seed_domains
from tl_tui import evidence_text as et


def trail():  # type: ignore[no-untyped-def]
    client = FakeClient()
    seed_domains(client)
    return client.get_evidence_trail("P123", "P123-EW-0001")


def test_a_row_is_indented_by_depth_and_says_how_it_was_reached() -> None:
    root, rfi = trail().nodes
    assert et.node_cells(root) == (
        "P123-EW-0001",
        "CommercialItem",
        "Draft",
        "-",
        "Early warning: routing change",
    )
    assert et.node_cells(rfi) == (
        "  P123-RFI-0001",
        "TechnicalItem",
        "Answered",
        "derived from (active)",
        "Beam B12 clashes with line 47",
    )
    gone = rfi.model_copy(update={"voided": True, "key": None, "state": None})
    cells = et.node_cells(gone)
    assert cells[0] == "  ID-P123-RFI-0001" and cells[2] == "- VOID"
    assert len(cells) == len(et.EVIDENCE_COLUMNS)


def test_a_line_reads_like_the_one_the_command_line_tool_prints() -> None:
    assert et.node_line(trail().nodes[1], technical=True) == (
        "  P123-RFI-0001 [correspondence.TechnicalItem] Answered Beam B12 clashes with line 47"
        " <- derived from (active, since 2026-10-12) | cost_impact=yes"
    )


def test_the_trail_lists_every_record_and_says_when_a_bound_cut_it_short() -> None:
    found = trail()
    assert len(et.evidence_lines(found)) == 2
    cut = found.model_copy(update={"truncated": True})
    assert et.evidence_lines(cut)[-1] == "the walk was cut short by a bound; ask for less depth"


def test_the_panel_gives_the_link_and_the_facts_of_the_day() -> None:
    root, rfi = trail().nodes
    assert et.node_lines(root) == ["P123-EW-0001  created 2026-10-12  state that day: Draft"]
    lines = et.node_lines(rfi)
    assert lines[0] == "P123-RFI-0001  created 2026-10-12  state that day: Answered"
    assert lines[1] == (
        "reached by derived from (active) since 2026-10-12: escalated from P123-RFI-0001"
    )
    assert lines[2] == "Cost impact: yes"


def test_the_title_names_the_day_of_the_week_and_a_step_never_passes_today() -> None:
    assert et.evidence_title("P123-EW-0001", "2026-10-22") == (
        "Evidence for P123-EW-0001 as of 2026-10-22 (Thursday)"
    )
    today = date(2026, 10, 20)
    assert et.step_day(today, -1, today) == date(2026, 10, 19)
    assert et.step_day(date(2026, 10, 19), 1, today) == today
    assert et.step_day(today, 1, today) == today
    assert et.step_day(date(2026, 3, 1), 1, today) == date(2026, 3, 2)
