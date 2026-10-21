"""What the schedule screens show, as pure functions (P1-I4; ADR-0015).

The schedule and snapshot tables, the detail panel, the comparison, the activity table, an
activity with its neighbours and the float trend are text built from the values the client returns
(``tl_mod_schedule.views``, ``compare`` and ``lookahead``) and nothing else, so the tests check
them without a terminal. None of it decides anything: which snapshot is current, what moved and
what eroded are the module's findings, shown here as they come. Floats in the comparison and the
trend are days of the activity's own calendar; in the activity table and detail they are the hours
P6 writes.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_schedule.compare import Comparison
from tl_mod_schedule.lookahead import LookAhead
from tl_mod_schedule.registry import ActivityRow
from tl_mod_schedule.resolver import OrphanedLink
from tl_mod_schedule.views import (
    ActivityDetail,
    ActivityPage,
    ScheduleDetailView,
    ScheduleView,
    SnapshotView,
    TrendPoint,
)

from tl_tui.display import Labels, actor_label, humanize

SCHEDULE_COLUMNS = ("Code", "Type", "Current", "Data date", "Snapshots", "Title")
SNAPSHOT_COLUMNS = ("No", "State", "Data date", "Activities", "Errors", "Warnings", "File")
ACTIVITY_COLUMNS = ("Id", "Status", "Start", "Finish", "Float", "%", "Critical", "Name")
#: The lists of a comparison, in the order the screen cycles through them: (field, title).
COMPARE_SECTIONS = (
    ("added", "Added"),
    ("removed", "Removed"),
    ("date_shifts", "Date shifts"),
    ("float_changes", "Float"),
    ("logic_changes", "Logic"),
    ("progress_changes", "Progress"),
    ("duration_changes", "Durations"),
    ("critical_changes", "Critical"),
)
MAX_SECTION_LINES = 500
MAX_CELL = 60


def short(value: object, width: int = MAX_CELL) -> str:
    """``-`` for none, one line, cut to ``width`` characters."""
    text = "-" if value is None or value == "" else " ".join(str(value).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def date_only(value: str | None) -> str:
    """The day of an ISO date-time (``2026-10-12T08:00`` is ``2026-10-12``); ``-`` for none."""
    return "-" if not value else value[:10]


def hours(value: float | None) -> str:
    """``-`` for none, else ``40h`` or ``-8.5h``."""
    return "-" if value is None else f"{value:g}h"


def days(value: float | int | None) -> str:
    """``-`` for none, else ``4d`` or ``-1.5d``."""
    return "-" if value is None else f"{value:g}d"


def shift(value: int | None) -> str:
    """A shift in calendar days with its sign: ``+7d``, ``-2d``, ``+0d``; ``-`` for none."""
    return "-" if value is None else f"{value:+d}d"


def snapshot_name(key: str, *, technical: bool) -> str:
    """A snapshot's key as shown: ``MAIN#2`` in technical mode, ``Snapshot 2`` in plain mode."""
    if technical:
        return key
    code, sep, number = key.rpartition("#")
    if sep and code and number.isdigit():
        return f"Snapshot {number}"
    return key


_STATUS_PREFIXES = ("TK_", "TT_", "PCT_", "CS_")


def status_words(code: str | None) -> str:
    """A P6 status code as words: ``TK_Active`` is ``Active``; ``-`` for none."""
    if not code:
        return "-"
    for prefix in _STATUS_PREFIXES:
        if code.startswith(prefix):
            code = code[len(prefix) :]
            break
    return humanize(code) or "-"


def _status(code: str | None, technical: bool) -> str:
    """The raw P6 code in technical mode, its words in plain mode."""
    return f"{code}" if technical else status_words(code)


# --- schedules and snapshots -------------------------------------------------------------------


def schedule_cells(view: ScheduleView) -> tuple[str, ...]:
    """The six cells of a schedule row, in the order of ``SCHEDULE_COLUMNS``."""
    return (
        view.code,
        humanize(view.schedule_type),
        short(view.current_snapshot_number),
        date_only(view.current_data_date),
        str(view.snapshot_count),
        short(view.title),
    )


def snapshot_cells(view: SnapshotView) -> tuple[str, ...]:
    """The seven cells of a snapshot row, in the order of ``SNAPSHOT_COLUMNS``.

    The number of the current snapshot ends with ``*`` and its state says ``current`` too, so
    that nothing rides on colour.
    """
    return (
        f"{view.number}{'*' if view.is_current else ''}",
        f"{view.state} (current)" if view.is_current else view.state,
        date_only(view.data_date),
        short(view.activity_count),
        short(view.error_count),
        short(view.warning_count),
        short(view.source_name),
    )


def _who(labels: Labels, actor: str | None) -> str:
    """A person by name, a service by its label, ``-`` for none; never an actor id."""
    return short(None if not actor else actor_label(labels, actor))


def schedule_detail_lines(
    detail: ScheduleDetailView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The facts of a schedule, and a warning while its links are still being checked.

    The same lines in both modes: ``technical`` is accepted so that every detail function takes
    the same arguments.
    """
    labels = Labels() if labels is None else labels
    lines = [
        f"{detail.code}  {detail.title}",
        f"type {humanize(detail.schedule_type)}  |  owner {_who(labels, detail.owner)}  |  "
        f"P6 project {short(detail.p6_project)}",
        f"current snapshot {short(detail.current_snapshot_number)}  |  "
        f"data date {date_only(detail.current_data_date)}  |  {detail.snapshot_count} snapshots",
    ]
    if detail.links_being_checked:
        lines.append(
            "! links to activities are being checked: one to an activity that left the "
            "schedule may still read as current"
        )
    return lines


def snapshot_page_line(first: int, shown: int, total: int) -> str | None:
    """Where the page of snapshots is in all of them, or ``None`` when one page holds them all."""
    if shown >= total and first == 0:
        return None
    last = first + shown
    return (
        f"snapshots {first + 1 if shown else 0} to {last} of {total}  "
        f"({'n next page  ' if last < total else ''}{'b previous page' if first else ''})"
    ).replace("  )", ")")


def snapshot_detail_lines(
    view: SnapshotView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The facts of a snapshot: counts, the file, who asked, and why it failed if it did.

    Plain mode names it ``Snapshot 2``; technical mode shows its key ``MAIN#2`` and the command
    the worker runs.
    """
    labels = Labels() if labels is None else labels
    name = view.key if technical else f"Snapshot {view.number}"
    lines = [
        f"{name}  {view.state}{' (current)' if view.is_current else ''}  |  "
        f"data date {short(view.data_date)}  |  P6 {short(view.p6_version)}",
        f"activities {short(view.activity_count)}  relationships {short(view.relationship_count)}"
        f"  WBS {short(view.wbs_count)}  calendars {short(view.calendar_count)}  "
        f"codes {short(view.code_count)}  user fields {short(view.udf_count)}",
        f"errors {short(view.error_count)}  warnings {short(view.warning_count)}  |  "
        f"file {short(view.source_name)}  |  requested by {_who(labels, view.requested_by)}",
    ]
    if view.previous_number is not None:
        lines.append(f"compares with snapshot {view.previous_number}")
    if view.state in ("Uploaded", "Processing"):
        lines.append(
            "waiting for the worker (`tl xer worker`)" if technical else "waiting to be processed"
        )
    if view.last_error:
        lines.append(f"last error: {short(view.last_error, 200)}")
    return lines


def schedules_summary(shown: int, total: int, *, text: str) -> str:
    """The status line under the schedule table."""
    parts = [f"{shown} of {total} schedules"]
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return "  ".join(parts)


def look_ahead_lines(answer: LookAhead, *, technical: bool = True) -> list[str]:
    """The look-ahead: the window, the counts, then one line per activity."""
    counts = answer.counts
    key = snapshot_name(answer.snapshot_key, technical=technical)
    lines = [
        f"look-ahead {key}: {answer.window_start} to {answer.window_end} ({answer.weeks} weeks)",
        f"in progress {counts.get('in_progress', 0)}  late start {counts.get('late_start', 0)}  "
        f"starting {counts.get('starting', 0)}  critical {counts.get('critical', 0)}  "
        f"total {counts.get('total', 0)}",
    ]
    for r in answer.rows:
        lines.append(
            f"  {r.activity_id}  {r.phase}  {date_only(r.early_start)} to "
            f"{date_only(r.early_finish)}  float {days(r.total_float_days)}  "
            f"{r.percent_complete:g}%{'  CRITICAL' if r.critical else ''}  {short(r.name)}"
        )
    return lines


def orphan_lines(links: Sequence[OrphanedLink], *, technical: bool = True) -> list[str]:
    """The links the last publication flagged because their activity left the schedule.

    Plain mode drops the record and link ids; technical mode keeps them.
    """
    if not links:
        return ["no orphaned links: every activity that is linked to is in the current snapshot"]
    lines = [f"orphaned links: {len(links)}"]
    if technical:
        lines.extend(
            f"  {o.activity_id}  last seen in snapshot {short(o.last_seen_number)}  "
            f"record {o.from_id}  link {o.link_id}"
            for o in links
        )
    else:
        lines.extend(
            f"  {o.activity_id}  last seen in snapshot {short(o.last_seen_number)}" for o in links
        )
    return lines


# --- comparison --------------------------------------------------------------------------------


def compare_header_lines(c: Comparison, *, technical: bool = True) -> list[str]:
    """What the comparison is of, the shift of the data date and of the project finish."""
    new = snapshot_name(c.new.key, technical=technical)
    old = snapshot_name(c.old.key, technical=technical)
    return [
        f"{new} ({date_only(c.new.data_date)}) against {old} ({date_only(c.old.data_date)})",
        f"data date {shift(c.data_date_shift_days)}  |  latest finish "
        f"{date_only(c.latest_finish_old)} to {date_only(c.latest_finish_new)} "
        f"({shift(c.finish_shift_days)})",
    ]


def compare_tabs(c: Comparison) -> list[str]:
    """One label per section: the title and the full count, ``Float 8``."""
    return [f"{title} {c.totals.get(name, 0)}" for name, title in COMPARE_SECTIONS]


def compare_section_lines(
    c: Comparison, name: str, limit: int = MAX_SECTION_LINES, *, technical: bool = True
) -> list[str]:
    """The rows of one list of the comparison, and a line saying how many were cut.

    Progress rows show P6 status words in plain mode and the raw codes in technical mode.
    """
    rows: Sequence[str]
    if name == "added":
        rows = [f"+ {r.activity_id}  {short(r.name)}  ({short(r.wbs_path)})" for r in c.added]
    elif name == "removed":
        rows = [f"- {r.activity_id}  {short(r.name)}  ({short(r.wbs_path)})" for r in c.removed]
    elif name == "date_shifts":
        rows = [
            f"~ {r.activity_id}  start {shift(r.start_shift_days)}  "
            f"finish {shift(r.finish_shift_days)}  largest {r.largest_days}d  {short(r.name)}"
            for r in c.date_shifts
        ]
    elif name == "float_changes":
        rows = [
            f"~ {r.activity_id}  float {days(r.old_days)} to {days(r.new_days)}  "
            f"{'ERODED' if r.eroded else 'improved'}  {short(r.name)}"
            for r in c.float_changes
        ]
    elif name == "logic_changes":
        rows = [
            f"{r.kind:<7} {r.pred_activity_id} -> {r.succ_activity_id}  "
            f"{short(r.old_type)} to {short(r.new_type)}"
            for r in c.logic_changes
        ]
    elif name == "progress_changes":
        rows = [
            f"~ {r.activity_id}  {r.old_percent:g}% to {r.new_percent:g}%  "
            f"{_status(r.old_status, technical)} to {_status(r.new_status, technical)}  "
            f"{short(r.name)}"
            for r in c.progress_changes
        ]
    elif name == "duration_changes":
        rows = [
            f"~ {r.activity_id}  duration {days(r.old_days)} to {days(r.new_days)}  {short(r.name)}"
            for r in c.duration_changes
        ]
    elif name == "critical_changes":
        rows = [
            f"{'!' if r.direction == 'entered' else ' '} {r.activity_id}  {r.direction} the "
            f"critical set  float {days(r.old_float_days)} to {days(r.new_float_days)}  "
            f"{short(r.name)}"
            for r in c.critical_changes
        ]
    else:
        return []
    lines = list(rows[:limit])
    hidden = c.totals.get(name, len(rows)) - len(lines)
    if hidden > 0:
        lines.append(f"... {hidden} more not shown")
    if not lines:
        lines.append("none")
    return lines


# --- activities --------------------------------------------------------------------------------


def activity_cells(a: ActivityRow, *, technical: bool = True) -> tuple[str, ...]:
    """The eight cells of an activity row, in the order of ``ACTIVITY_COLUMNS``."""
    return (
        a.activity_id,
        _status(a.status, technical),
        date_only(a.early_start),
        date_only(a.early_finish),
        hours(a.total_float_hr),
        f"{a.percent_complete:g}",
        "critical" if a.critical else "",
        short(a.name),
    )


def page_line(page: ActivityPage, *, critical: bool, text: str, technical: bool = True) -> str:
    """The status line under the activity table."""
    first = page.offset + 1 if page.rows else 0
    name = snapshot_name(page.snapshot_key, technical=technical)
    parts = [
        f"{name}  data date {date_only(page.data_date)}",
        f"{first}-{page.offset + len(page.rows)} of {page.total} activities",
    ]
    if critical:
        parts.append("critical only")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return "  |  ".join(parts)


def activity_detail_lines(detail: ActivityDetail, *, technical: bool = True) -> list[str]:
    """One activity: its dates, float and the relationships that name it."""
    a = detail.activity
    name = snapshot_name(detail.snapshot_key, technical=technical)
    task_type = _status(a.task_type, technical)
    lines = [
        f"{a.activity_id}  {short(a.name, 80)}  |  {name}",
        f"{task_type}  {_status(a.status, technical)}  {a.percent_complete:g}% "
        f"({short(a.percent_type)})  |  "
        f"WBS {short(a.wbs_path, 80)}",
        f"early {date_only(a.early_start)} to {date_only(a.early_finish)}  |  "
        f"late {date_only(a.late_start)} to {date_only(a.late_finish)}  |  "
        f"actual {date_only(a.actual_start)} to {date_only(a.actual_finish)}",
        f"float total {hours(a.total_float_hr)}  free {hours(a.free_float_hr)}"
        f"{'  CRITICAL' if a.critical else ''}"
        + (
            f"  |  constraint {a.constraint_type} {date_only(a.constraint_date)}"
            if a.constraint_type
            else ""
        ),
        f"predecessors {len(detail.predecessors)}",
    ]
    lines.extend(
        f"  {r.pred_activity_id}  {r.relationship_type}  lag {hours(r.lag_hr)}"
        for r in detail.predecessors
    )
    lines.append(f"successors {len(detail.successors)}")
    lines.extend(
        f"  {r.succ_activity_id}  {r.relationship_type}  lag {hours(r.lag_hr)}"
        for r in detail.successors
    )
    return lines


def trend_lines(points: Sequence[TrendPoint]) -> list[str]:
    """The float trend: one line per published snapshot, oldest first."""
    lines = ["float trend:"]
    lines.extend(
        f"  #{p.snapshot_number}  {date_only(p.data_date)}  {p.state}  "
        f"float {days(p.total_float_days)}  {date_only(p.early_start)} to "
        f"{date_only(p.early_finish)}  {p.percent_complete:g}%{'  CRITICAL' if p.critical else ''}"
        for p in points
    )
    return lines
