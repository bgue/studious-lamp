"""The text of the weekly cycle steps 4 and 5 (P2-I5-T06b): one test per function added to
``tl_tui.weekly_text`` for the commitments and the progress (the step 1 to 3 text is in
``test_weekly_text.py``)."""

from __future__ import annotations

from decimal import Decimal

from tl_api.routes.awp_progress import IwpProgress, ProgressItem
from tl_mod_awp.iwp_counts import IwpCountRow
from tl_mod_awp.iwp_views import IwpRow
from tl_mod_awp.kpis import KpiTile
from tl_mod_awp.week_views import CommitmentRow, WeekDetail
from tl_tui.layout import EMPTY
from tl_tui.weekly_text import (
    commitment_cells,
    commitment_panel,
    commitment_summary,
    plan_line_cells,
    plan_line_key,
    plan_lines,
    plan_panel,
    progress_cells,
    progress_panel,
    progress_summary,
    reason_labels,
)


def _commitment(
    key: str, *, outcome: str | None = None, reason: str | None = None
) -> CommitmentRow:
    return CommitmentRow(
        iwp_id=f"IWP-{key}",
        iwp_key=f"P123-IWP-PIP-{key}",
        iwp_state="Issued",
        foreman="user:uma",
        committed_hours="40.0",
        outcome=outcome,
        miss_reason=reason,
    )


def _plan(
    state: str = "Committed",
    *,
    ppc: str | None = None,
    commitments: tuple[CommitmentRow, ...] = (),
) -> WeekDetail:
    return WeekDetail(
        id="PLAN-2",
        key="P123-WK-2",
        week="2026-W45",
        week_start="2026-11-02",
        state=state,
        ppc=ppc,
        closed_at="2026-11-09" if state == "Closed" else None,
        version=1,
        commitments=list(commitments),
        notes=["Plan notes"],
    )


def test_plan_lines_puts_the_plan_first_and_then_its_commitments() -> None:
    first, second = _commitment("0001"), _commitment("0002")
    lines = plan_lines(_plan(commitments=(first, second)))
    assert [line.commitment for line in lines] == [None, first, second]
    assert all(line.plan.week == "2026-W45" for line in lines)


def test_plan_line_key_is_the_week_or_the_week_and_the_iwp() -> None:
    lines = plan_lines(_plan(commitments=(_commitment("0001"),)))
    assert plan_line_key(lines[0]) == "2026-W45"
    assert plan_line_key(lines[1]) == "2026-W45/IWP-0001"


def test_plan_line_cells_name_the_week_on_the_plan_row_and_are_the_commitment_cells_below() -> None:
    commitment = _commitment("0001")
    lines = plan_lines(_plan(commitments=(commitment,)))
    assert plan_line_cells(lines[0]) == ("Week 2026-W45", "Committed", EMPTY, EMPTY, EMPTY, EMPTY)
    assert plan_line_cells(lines[1]) == commitment_cells(commitment)


def test_commitment_summary_shows_the_ppc_of_a_closed_week_and_a_dash_for_an_open_one() -> None:
    closed = _plan("Closed", ppc="66.7", commitments=(_commitment("0001"), _commitment("0002")))
    assert commitment_summary(closed) == "2026-W45 · Closed · 2 commitments · PPC 66.7%"
    open_week = _plan(commitments=(_commitment("0001"),))
    assert commitment_summary(open_week) == f"2026-W45 · Committed · 1 commitment · PPC {EMPTY}"


def test_plan_panel_gives_the_week_its_state_and_its_notes() -> None:
    text = plan_panel(_plan())
    assert text.splitlines()[0] == "Week 2026-W45, starting 2026-11-02 · Committed"
    assert text.splitlines()[-1] == "Plan notes"


def test_commitment_panel_gives_the_hours_and_the_outcome_with_its_reason() -> None:
    text = commitment_panel(_commitment("0001", outcome="missed", reason="Weather"))
    lines = text.splitlines()
    assert lines[0] == "P123-IWP-PIP-0001 · Issued"
    assert lines[1].startswith("Committed 40 h, foreman ")
    assert lines[2] == "Outcome Missed · reason Weather"


def test_reason_labels_maps_each_humanized_label_to_its_key() -> None:
    assert reason_labels(["Weather", "NoRain"]) == {"Weather": "Weather", "No rain": "NoRain"}


def test_progress_cells_leave_the_earned_percent_out_and_mark_a_missing_count() -> None:
    row = IwpRow(id="IWP-1", number="P123-IWP-PIP-0001", title="Pipe spools", state="In progress")
    count = IwpCountRow(
        number=row.number,
        state_since="2026-10-20",
        ready_ok=9,
        ready_total=9,
        evaluated=True,
        open_blocking=0,
    )
    assert progress_cells(row, count) == (
        "P123-IWP-PIP-0001",
        "Pipe spools",
        "In progress",
        "9/9",
        "0",
    )
    assert progress_cells(row, None) == (
        "P123-IWP-PIP-0001",
        "Pipe spools",
        "In progress",
        EMPTY,
        EMPTY,
    )


def test_progress_panel_lists_the_earned_percent_each_item_and_the_notes() -> None:
    row = IwpRow(id="IWP-1", number="P123-IWP-PIP-0001", title="Pipe spools", state="In progress")
    progress = IwpProgress(
        number=row.number,
        pct=Decimal("42.5"),
        edition="2026",
        items=[
            ProgressItem(key="5.0", pct=Decimal("50"), steps=["Fit", "Weld"], hours=None),
        ],
        notes=["Checked"],
    )
    assert progress_panel(row, progress).splitlines() == [
        "Pipe spools · P123-IWP-PIP-0001",
        "Earned 42.5%",
        "5.0: 50% · steps Fit, Weld",
        "Note: Checked",
    ]
    assert progress_panel(row, None).splitlines() == [
        "Pipe spools · P123-IWP-PIP-0001",
        f"Earned {EMPTY}",
    ]


def test_progress_summary_joins_the_two_kpi_lines_with_a_dot() -> None:
    tiles = [
        KpiTile(
            name="kpi_ppc",
            value=Decimal("80.0"),
            numerator=4,
            denominator=5,
            detail="4 of 5 committed IWPs done",
        ),
        KpiTile(
            name="kpi_constraint_free",
            value=None,
            numerator=0,
            denominator=0,
            detail="no live IWP",
        ),
    ]
    assert progress_summary(tiles) == (
        "PPC 80.0%  4 of 5 IWPs done  ·  Constraint-free —  no live IWP"
    )
