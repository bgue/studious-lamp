"""P2-I5-T06a: the text of the weekly cycle screens (pure functions)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from tl_mod_awp.kpis import KpiTile
from tl_mod_awp.look_ahead_view import LookAheadItem, LookAheadIwp, LookAheadView
from tl_mod_awp.week_views import CommitmentRow, WeekRow
from tl_mod_schedule.lookahead import LookAheadRow
from tl_tui.layout import EMPTY
from tl_tui.weekly_text import (
    COMMITMENT_COLUMNS,
    LOOK_AHEAD_COLUMNS,
    WEEK_COLUMNS,
    commitment_cells,
    constraint_panel,
    kpi_line,
    line_key,
    look_ahead_cells,
    look_ahead_lines,
    look_ahead_summary,
    week_cells,
)


def activity(activity_id: str, phase: str = "starting", start: str | None = "2026-11-09") -> Any:
    return LookAheadRow(
        activity_id=activity_id,
        name=f"Work {activity_id}",
        wbs_path="1.1",
        status="not_started",
        phase=phase,
        early_start=start,
        early_finish="2026-11-20",
        total_float_days=3.0,
        critical=False,
        percent_complete=0.0,
    )


def iwp(
    number: str, *, evaluated: bool = True, ok: int = 2, total: int = 3, blocking: int = 1
) -> LookAheadIwp:
    return LookAheadIwp(
        id=f"id-{number}",
        number=number,
        state="Ready",
        planned_start="2026-12-01",
        need_by="2026-11-03" if evaluated else None,
        evaluated=evaluated,
        ready=evaluated and ok == total,
        checks_ok=ok if evaluated else 0,
        checks_total=total if evaluated else 0,
        open_blocking=blocking,
    )


def view() -> LookAheadView:
    return LookAheadView(
        snapshot_key="P123-MAIN-1",
        data_date="2026-11-02",
        window_start="2026-11-02",
        window_end="2026-11-30",
        weeks=4,
        lead_weeks=4,
        counts={"total": 3},
        items=(
            LookAheadItem(
                activity("A1230", "in_progress", None),
                (iwp("P123-IWP-0001"), iwp("P123-IWP-0002", evaluated=False)),
            ),
            LookAheadItem(activity("A1140"), ()),
        ),
    )


def test_a_line_per_iwp_and_one_for_an_activity_without() -> None:
    lines = look_ahead_lines(view())
    assert [line_key(x) for x in lines] == [
        "A1230/P123-IWP-0001",
        "A1230/P123-IWP-0002",
        "A1140",
    ]
    assert lines[2].iwp is None


def test_the_cells_follow_the_columns_and_use_the_empty_mark() -> None:
    first, second, bare = (look_ahead_cells(x) for x in look_ahead_lines(view()))
    assert len(LOOK_AHEAD_COLUMNS) == len(first) == len(second) == len(bare) == 8
    assert first == (
        "A1230",
        "In progress",
        EMPTY,
        "P123-IWP-0001",
        "Ready",
        "2026-11-03",
        "2/3",
        "1",
    )
    assert second[5:] == (EMPTY, EMPTY, "1")  # never evaluated: no need-by date, no Ready figure
    assert bare == ("A1140", "Starting", "2026-11-09", EMPTY, EMPTY, EMPTY, EMPTY, EMPTY)


def test_the_summary_names_the_window_and_the_counts() -> None:
    assert look_ahead_summary(view()) == (
        "4 weeks, 2026-11-02 to 2026-11-30 · 2 activities, 2 IWPs · need-by 4 weeks ahead"
    )


def test_week_and_commitment_cells() -> None:
    closed = WeekRow(
        id="w1",
        key="P123-WK-2026W45",
        week="2026-W45",
        week_start="2026-11-02",
        state="Closed",
        ppc="66.7",
    )
    draft = WeekRow(
        id="w2", key="P123-WK-2026W46", week="2026-W46", week_start="2026-11-09", state="Draft"
    )
    assert len(WEEK_COLUMNS) == 3
    assert week_cells(closed) == ("2026-W45", "Closed", "66.7%")
    assert week_cells(draft) == ("2026-W46", "Draft", EMPTY)
    missed = CommitmentRow(
        iwp_id="i1",
        iwp_key="P123-IWP-0003",
        iwp_state="Issued",
        foreman="user:uma",
        committed_hours="12.5",
        outcome="missed",
        miss_reason="Weather",
    )
    open_ = missed.model_copy(
        update={"outcome": None, "miss_reason": None, "committed_hours": "1200.0"}
    )
    assert len(COMMITMENT_COLUMNS) == 6
    assert commitment_cells(missed) == (
        "P123-IWP-0003",
        "Issued",
        "12.5",
        "uma",
        "Missed",
        "Weather",
    )
    assert commitment_cells(open_)[2:] == ("1 200", "uma", EMPTY, EMPTY)


def test_kpi_lines() -> None:
    ppc = KpiTile(name="kpi_ppc", value=Decimal("80.0"), numerator=4, denominator=5, detail="")
    free = KpiTile(
        name="kpi_constraint_free", value=Decimal("75.0"), numerator=3, denominator=4, detail=""
    )
    assert kpi_line(ppc) == "PPC 80.0%  4 of 5 IWPs done"
    assert kpi_line(free) == "Constraint-free 75.0%  3 of 4 IWPs"
    none_ppc = ppc.model_copy(update={"value": None, "numerator": 0, "denominator": 0})
    none_free = free.model_copy(update={"value": None, "numerator": 0, "denominator": 0})
    assert kpi_line(none_ppc) == f"PPC {EMPTY}  no closed week yet"
    assert kpi_line(none_free) == f"Constraint-free {EMPTY}  no live IWP"


def test_a_waived_constraint_panel_names_who_waived_it_and_why() -> None:
    # P2-I5-T17 (attempt 2): the same words as `tl awp iwp show` (waived by <who>: <reason>).
    waived = SimpleNamespace(
        description="readiness check materials_reserved is blocked",
        waived=True,
        cleared_by="user:mokafor",
        clear_reason="Materials coordinator confirmed the reservation by phone",
    )
    assert constraint_panel(waived) == (  # type: ignore[arg-type]
        "readiness check materials_reserved is blocked\n"
        "waived by mokafor: Materials coordinator confirmed the reservation by phone"
    )
    open_row = SimpleNamespace(description="Crane booked", waived=False)
    assert constraint_panel(open_row) == "Crane booked"  # type: ignore[arg-type]
    no_text = SimpleNamespace(description=None, waived=False)
    assert constraint_panel(no_text) == EMPTY  # type: ignore[arg-type]
