"""The text of the weekly cycle screens, as pure functions (P2-I5-T06a; skill ``tui-layout``).

Values come from ``tl_mod_awp.look_ahead_view``, ``tl_mod_awp.week_views``, ``tl_mod_awp.kpis``,
``tl_mod_awp.iwp_views`` and ``tl_mod_awp.iwp_counts`` only: no client call, no I/O, no ``textual``
import. Dates and hours are formatted by ``tl_tui.awp_text`` (``date_text``, ``hours_text``); the
empty mark is ``tl_tui.layout.EMPTY``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from tl_mod_awp.iwp_counts import IwpCountRow
from tl_mod_awp.iwp_views import IwpRow
from tl_mod_awp.kpis import KpiTile
from tl_mod_awp.look_ahead_view import LookAheadItem, LookAheadIwp, LookAheadView
from tl_mod_awp.week_views import CommitmentRow, WeekRow

from tl_tui.awp_text import date_text, hours_text
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import EMPTY

if TYPE_CHECKING:
    from tl_api.routes.constraints import ConstraintRow

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
CONSTRAINT_REVIEW_COLUMNS = ("Key", "Subject", "Phase", "State", "Source", "Owner", "Age")
RELEASE_COLUMNS = ("Number", "Subject", "Foreman", "Sign-offs", "Ready")

#: An IWP is issued to its foreman after two distinct sign-offs (``IssueIwp``).
SIGNOFFS_NEEDED = 2
#: The look-ahead's line when no schedule has a published snapshot.
NO_SCHEDULE = "No published schedule yet."
#: The state word of a check-raised constraint that was cleared (S4b ``waived``).
WAIVED = "waived"
#: The ``source`` of a constraint that a check raised; only these can be waived from the log.
CHECK_SOURCE = "check"
OPEN_STATES = ("Open", "Assigned")


@dataclass(frozen=True)
class LookAheadLine:
    """One log row: an activity with one of its IWPs, or alone (``iwp`` None)."""

    item: LookAheadItem
    iwp: LookAheadIwp | None


def _plural(count: int, word: str, plural: str | None = None) -> str:
    """``1 week``, ``4 weeks``; ``plural`` names the plural when it is not ``word`` + ``s``."""
    if count == 1:
        return f"1 {word}"
    return f"{count} {plural or word + 's'}"


def look_ahead_lines(view: LookAheadView) -> list[LookAheadLine]:
    """One line per IWP of each activity, in the view's order (IWPs by number); an activity with
    no IWP is one line with ``iwp`` None."""
    lines: list[LookAheadLine] = []
    for item in view.items:
        if item.iwps:
            lines.extend(LookAheadLine(item, iwp) for iwp in item.iwps)
        else:
            lines.append(LookAheadLine(item, None))
    return lines


def line_key(line: LookAheadLine) -> str:
    """The row key: ``<activity id>`` alone, or ``<activity id>/<IWP number>``."""
    activity_id = line.item.row.activity_id
    return activity_id if line.iwp is None else f"{activity_id}/{line.iwp.number}"


def look_ahead_cells(line: LookAheadLine) -> tuple[str, ...]:
    """The eight cells in the order of ``LOOK_AHEAD_COLUMNS``; empty values are the empty mark.
    Ready is ``2/3`` (never evaluated: the empty mark); the phase and state are humanized."""
    row = line.item.row
    iwp = line.iwp
    if iwp is None:
        number, state, need_by, ready, blocking = EMPTY, EMPTY, EMPTY, EMPTY, EMPTY
    else:
        number = iwp.number
        state = humanize(iwp.state)
        need_by = date_text(iwp.need_by)
        ready = f"{iwp.checks_ok}/{iwp.checks_total}" if iwp.evaluated else EMPTY
        blocking = str(iwp.open_blocking)
    return (
        row.activity_id,
        humanize(row.phase),
        date_text(row.early_start),
        number,
        state,
        need_by,
        ready,
        blocking,
    )


def look_ahead_summary(view: LookAheadView) -> str:
    """``4 weeks, 2026-11-02 to 2026-11-30 · 3 activities, 2 IWPs · need-by 4 weeks ahead``."""
    activities = len(view.items)
    iwps = sum(len(item.iwps) for item in view.items)
    return (
        f"{_plural(view.weeks, 'week')}, {view.window_start} to {view.window_end}"
        f" · {_plural(activities, 'activity', 'activities')}, {_plural(iwps, 'IWP', 'IWPs')}"
        f" · need-by {_plural(view.lead_weeks, 'week')} ahead"
    )


def look_ahead_panel(line: LookAheadLine) -> str:
    """The highlighted activity in full, and its IWP (when it has one)."""
    row = line.item.row
    head = (
        f"{row.name} · WBS {row.wbs_path} · "
        f"{date_text(row.early_start)} to {date_text(row.early_finish)}"
    )
    iwp = line.iwp
    if iwp is None:
        return f"{head}\nNo IWP is linked to this activity."
    return (
        f"{head}\n{iwp.number}: planned start {date_text(iwp.planned_start)}, "
        f"need by {date_text(iwp.need_by)}, {iwp.open_blocking} open blocking"
    )


def week_cells(row: WeekRow) -> tuple[str, ...]:
    """``2026-W45``, the humanized state, the PPC as ``66.7%`` (the empty mark for none)."""
    return (row.week, humanize(row.state), EMPTY if row.ppc is None else f"{row.ppc}%")


def commitment_cells(row: CommitmentRow) -> tuple[str, ...]:
    """IWP key, humanized state, hours (``hours_text``), foreman as a name, the outcome humanized
    (the empty mark for none) and the miss reason humanized (the empty mark for none)."""
    return (
        row.iwp_key,
        humanize(row.iwp_state),
        hours_text(Decimal(row.committed_hours)),
        actor_label(Labels(), row.foreman),
        humanize(row.outcome) if row.outcome else EMPTY,
        humanize(row.miss_reason) if row.miss_reason else EMPTY,
    )


def kpi_line(tile: KpiTile) -> str:
    """``PPC 80.0%  4 of 5 IWPs done`` and ``Constraint-free 75.0%  3 of 4 IWPs``; with no value
    ``PPC —  no closed week yet`` and ``Constraint-free —  no live IWP``."""
    if tile.name == "kpi_ppc":
        head, tail, none = "PPC", "IWPs done", "no closed week yet"
    else:
        head, tail, none = "Constraint-free", "IWPs", "no live IWP"
    if tile.value is None:
        return f"{head} {EMPTY}  {none}"
    return f"{head} {tile.value}%  {tile.numerator} of {tile.denominator} {tail}"


# --- step 2: the constraint review ---------------------------------------------------------------


def merge_constraints(*reads: Iterable[ConstraintRow]) -> list[ConstraintRow]:
    """The rows of several reads, one per key, by key."""
    by_key: dict[str, ConstraintRow] = {}
    for rows in reads:
        for row in rows:
            by_key[row.key] = row
    return [by_key[key] for key in sorted(by_key)]


def constraint_state(row: ConstraintRow) -> str:
    """The humanized state; a check-raised constraint that was cleared reads ``waived``."""
    return WAIVED if row.waived else humanize(row.state)


def waivable(row: ConstraintRow) -> bool:
    """Only a check-raised constraint that is still Open or Assigned can be waived."""
    return row.source == CHECK_SOURCE and row.state in OPEN_STATES


def constraint_cells(row: ConstraintRow) -> tuple[str, ...]:
    """The seven cells in the order of ``CONSTRAINT_REVIEW_COLUMNS``."""
    return (
        row.key,
        row.subject_key,
        humanize(row.phase),
        constraint_state(row),
        humanize(row.source),
        actor_label(Labels(), row.owner) if row.owner else EMPTY,
        f"{row.age_days} d",
    )


def constraint_panel(row: ConstraintRow) -> str:
    """The constraint's description (the panel of step 2)."""
    return row.description or EMPTY


def review_summary(blocking: int) -> str:
    """``2 blocking constraints open or assigned``."""
    return f"{_plural(blocking, 'blocking constraint')} open or assigned"


# --- step 3: the release -------------------------------------------------------------------------


def signoff_cell(count: int | None) -> str:
    """``signoffs 1 of 2``; the empty mark stands for a count the read does not give."""
    return f"signoffs {EMPTY if count is None else count} of {SIGNOFFS_NEEDED}"


def ready_cell(count: IwpCountRow | None) -> str:
    """``ok/total`` of the readiness checks; the empty mark when never evaluated."""
    if count is None or not count.evaluated:
        return EMPTY
    return f"{count.ready_ok}/{count.ready_total}"


def release_cells(
    row: IwpRow, count: IwpCountRow | None, signoffs: int | None = None
) -> tuple[str, ...]:
    """The five cells in the order of ``RELEASE_COLUMNS``."""
    return (
        row.number,
        row.title or EMPTY,
        actor_label(Labels(), row.foreman) if row.foreman else EMPTY,
        signoff_cell(signoffs),
        ready_cell(count),
    )


def release_panel(row: IwpRow) -> str:
    """The Ready IWP in full: its subject and planned start."""
    return f"{row.title or EMPTY} · planned start {date_text(row.planned_start)}"


def release_summary(ready: int) -> str:
    """``3 Ready IWPs``."""
    return _plural(ready, "Ready IWP", "Ready IWPs")
