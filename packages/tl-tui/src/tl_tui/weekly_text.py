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
from tl_mod_awp.week_views import CommitmentRow, WeekDetail, WeekRow

from tl_tui.awp_text import date_text, hours_text
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import EMPTY
from tl_tui.text import timestamp

if TYPE_CHECKING:
    from tl_api.routes.awp_progress import IwpProgress
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
RELEASE_COLUMNS = ("Number", "Subject", "Foreman", "Ready")
PROGRESS_COLUMNS = ("Number", "Subject", "State", "Ready", "Blocking")
#: The IWP states step 5 lists: the field work and the one before it (Field complete is closed out
#: in roadmap 3c, but its IWPs still show their earned progress).
PROGRESS_STATES = ("Issued", "In progress", "Field complete")
#: The state word of a closed week (``CloseWeek``).
CLOSED_WEEK = "Closed"
#: The line of step 4 when no week is open; ``o`` opens this week.
NO_OPEN_WEEK = "No open week. o opens this week."

#: An IWP is issued to its foreman after two distinct sign-offs (``IssueIwp``). The count is not
#: in any list read: the panel of the highlighted IWP shows it (one ``get_iwp`` for that row).
SIGNOFFS_NEEDED = 2
#: The look-ahead's line when no schedule has a published snapshot.
NO_SCHEDULE = "No published schedule yet."
#: The state word of a check-raised constraint that was cleared (S4b ``waived``).
WAIVED = "waived"
#: The words before a waived constraint's who and why (the panel of step 2, as ``tl awp iwp show``).
WAIVED_BY = "waived by"
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
    """The constraint's description (the panel of step 2). A waived one adds who waived it and
    why, in the words of ``tl awp iwp show``: ``waived by <who>: <reason>``."""
    text = row.description or EMPTY
    if not row.waived:
        return text
    who = actor_label(Labels(), row.cleared_by) if row.cleared_by else EMPTY
    return f"{text}\n{WAIVED_BY} {who}: {row.clear_reason or EMPTY}"


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


def release_cells(row: IwpRow, count: IwpCountRow | None) -> tuple[str, ...]:
    """The four cells in the order of ``RELEASE_COLUMNS``."""
    return (
        row.number,
        row.title or EMPTY,
        actor_label(Labels(), row.foreman) if row.foreman else EMPTY,
        ready_cell(count),
    )


def release_panel(row: IwpRow, signoffs: int | None) -> str:
    """The Ready IWP in full: its subject, planned start and sign-off count (the empty mark when
    the read does not give it)."""
    return (
        f"{row.title or EMPTY} · planned start {date_text(row.planned_start)}\n"
        f"{signoff_cell(signoffs)}"
    )


def release_summary(ready: int) -> str:
    """``3 Ready IWPs``."""
    return _plural(ready, "Ready IWP", "Ready IWPs")


# --- step 4: the commitments ---------------------------------------------------------------------


@dataclass(frozen=True)
class PlanLine:
    """One row of step 4: the week's plan (``commitment`` None), or one of its commitments."""

    plan: WeekDetail
    commitment: CommitmentRow | None


def plan_lines(plan: WeekDetail) -> list[PlanLine]:
    """The plan's row, then one row per commitment, in the plan's order."""
    return [PlanLine(plan, None), *(PlanLine(plan, row) for row in plan.commitments)]


def plan_line_key(line: PlanLine) -> str:
    """``2026-W45`` for the plan, ``2026-W45/<IWP id>`` for one of its commitments."""
    if line.commitment is None:
        return line.plan.week
    return f"{line.plan.week}/{line.commitment.iwp_id}"


def plan_line_cells(line: PlanLine) -> tuple[str, ...]:
    """The six cells in the order of ``COMMITMENT_COLUMNS``: the plan's row names the week and
    its state; the other cells are the empty mark."""
    if line.commitment is None:
        return (
            f"Week {line.plan.week}",
            humanize(line.plan.state),
            EMPTY,
            EMPTY,
            EMPTY,
            EMPTY,
        )
    return commitment_cells(line.commitment)


def commitment_summary(plan: WeekDetail) -> str:
    """``2026-W44 · Closed · 3 commitments · PPC 66.7%``; an open week reads ``PPC —``."""
    ppc = f"PPC {plan.ppc}%" if plan.ppc is not None else f"PPC {EMPTY}"
    count = _plural(len(plan.commitments), "commitment")
    return f"{plan.week} · {humanize(plan.state)} · {count} · {ppc}"


def plan_panel(plan: WeekDetail) -> str:
    """The week in full: its start date, its state, the close time when closed (``2026-11-13
    16:00``, as the other screens show a time), its notes."""
    closed = f" · closed {timestamp(plan.closed_at)}" if plan.closed_at else ""
    head = f"Week {plan.week}, starting {plan.week_start} · {humanize(plan.state)}{closed}"
    return "\n".join([head, *plan.notes])


def commitment_panel(row: CommitmentRow) -> str:
    """The commitment in full: the IWP, the committed hours, the foreman, the outcome and the
    miss reason (when there is one)."""
    head = f"{row.iwp_key} · {humanize(row.iwp_state)}"
    committed = f"Committed {hours_text(Decimal(row.committed_hours))} h"
    foreman = f"foreman {actor_label(Labels(), row.foreman)}"
    outcome = f"Outcome {humanize(row.outcome)}" if row.outcome else "Outcome not yet judged"
    reason = f" · reason {humanize(row.miss_reason)}" if row.miss_reason else ""
    return f"{head}\n{committed}, {foreman}\n{outcome}{reason}"


def reason_labels(keys: Iterable[str]) -> dict[str, str]:
    """The miss reasons as the form offers them: the humanized label, by label, to the code key."""
    return {humanize(key): key for key in keys}


# --- step 5: the progress ------------------------------------------------------------------------


def progress_cells(row: IwpRow, count: IwpCountRow | None) -> tuple[str, ...]:
    """The five cells in the order of ``PROGRESS_COLUMNS``: the number, the subject, the state,
    the readiness checks and the open blocking constraints (the empty mark when the count is
    not given). The earned percent is not a cell: it is one read per IWP, in the panel."""
    blocking = EMPTY if count is None else str(count.open_blocking)
    return (
        row.number,
        row.title or EMPTY,
        humanize(row.state),
        ready_cell(count),
        blocking,
    )


def progress_panel(row: IwpRow, progress: IwpProgress | None) -> str:
    """The IWP in full: its earned percent, one line per scope item (its steps) and the notes.
    The package edition is a technical detail and is not shown (this panel has no technical
    mode). ``progress`` None (the read failed) shows the empty mark for the earned percent."""
    head = f"{row.title or EMPTY} · {row.number}"
    if progress is None:
        return f"{head}\nEarned {EMPTY}"
    lines = [head, f"Earned {progress.pct}%"]
    for item in progress.items:
        steps = ", ".join(item.steps) if item.steps else EMPTY
        lines.append(f"{item.key}: {item.pct}% · steps {steps}")
    lines.extend(f"Note: {note}" for note in progress.notes)
    return "\n".join(lines)


def progress_summary(tiles: Iterable[KpiTile]) -> str:
    """The KPI tiles, one after the other: ``PPC 80.0%  4 of 5 IWPs done  ·  Constraint-free …``."""
    return "  ·  ".join(kpi_line(tile) for tile in tiles)
