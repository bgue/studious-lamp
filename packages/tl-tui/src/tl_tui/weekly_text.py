"""The text of the weekly cycle screens, as pure functions (P2-I5-T06a; skill ``tui-layout``).

STUB: the bodies raise ``NotImplementedError``; T06a writes them and removes this note. Values come
from ``tl_mod_awp.look_ahead_view``, ``tl_mod_awp.week_views`` and ``tl_mod_awp.kpis`` only: no
client call, no I/O, no ``textual`` import. Dates and hours are formatted by ``tl_tui.awp_text``
(``date_text``, ``hours_text``); the empty mark is ``tl_tui.layout.EMPTY``.
"""

from __future__ import annotations

from dataclasses import dataclass

from tl_mod_awp.kpis import KpiTile
from tl_mod_awp.look_ahead_view import LookAheadItem, LookAheadIwp, LookAheadView
from tl_mod_awp.week_views import CommitmentRow, WeekRow

LOOK_AHEAD_COLUMNS = (
    "Activity",
    "Phase",
    "Start",
    "IWP",
    "State",
    "Need by",
    "Ready",
    "Blocking",
)
WEEK_COLUMNS = ("Week", "State", "PPC")
COMMITMENT_COLUMNS = ("IWP", "State", "Hours", "Foreman", "Outcome", "Reason")


@dataclass(frozen=True)
class LookAheadLine:
    """One log row: an activity with one of its IWPs, or alone (``iwp`` None)."""

    item: LookAheadItem
    iwp: LookAheadIwp | None


def look_ahead_lines(view: LookAheadView) -> list[LookAheadLine]:
    """One line per IWP of each activity, in the view's order (IWPs by number); an activity with
    no IWP is one line with ``iwp`` None."""
    raise NotImplementedError


def line_key(line: LookAheadLine) -> str:
    """The row key: ``<activity id>`` alone, or ``<activity id>/<IWP number>``."""
    raise NotImplementedError


def look_ahead_cells(line: LookAheadLine) -> tuple[str, ...]:
    """The eight cells in the order of ``LOOK_AHEAD_COLUMNS``; empty values are the empty mark.
    Ready is ``2/3`` (never evaluated: the empty mark); the phase and state are humanized."""
    raise NotImplementedError


def look_ahead_summary(view: LookAheadView) -> str:
    """``4 weeks, 2026-11-02 to 2026-11-30 · 3 activities, 2 IWPs · need-by 4 weeks ahead``."""
    raise NotImplementedError


def week_cells(row: WeekRow) -> tuple[str, ...]:
    """``2026-W45``, the humanized state, the PPC as ``66.7%`` (the empty mark for none)."""
    raise NotImplementedError


def commitment_cells(row: CommitmentRow) -> tuple[str, ...]:
    """IWP key, humanized state, hours (``hours_text``), foreman as a name, the outcome humanized
    (the empty mark for none) and the miss reason humanized (the empty mark for none)."""
    raise NotImplementedError


def kpi_line(tile: KpiTile) -> str:
    """``PPC 80.0%  4 of 5 IWPs done`` and ``Constraint-free 75.0%  3 of 4 IWPs``; with no value
    ``PPC —  no closed week yet`` and ``Constraint-free —  no live IWP``."""
    raise NotImplementedError
