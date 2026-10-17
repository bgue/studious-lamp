"""The look-ahead: what the current snapshot says is about to happen (P1-I4-T08, brief 9 M11).

A look-ahead of 3 to 6 weeks lists, from a snapshot's activities, the ones a planner has to talk
about: what is under way, what should have started and has not, and what starts before the window
closes. The readiness of the work packages behind each activity joins in Phase 2 (AWP); until then
the row carries the schedule's own facts only.

``build_look_ahead`` is a pure function of the rows it is given. ``look_ahead`` reads a snapshot's
rows and calls it. Nothing here reads the clock: the window starts at the snapshot's data date.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Connection

from tl_mod_schedule import registry
from tl_mod_schedule.registry import DEFAULT_DAY_HOURS, ActivityRow, SnapshotRow

MIN_WEEKS = 1
MAX_WEEKS = 26
#: Summary rows of the work breakdown and level-of-effort activities have no work of their own.
EXCLUDED_TYPES = ("level_of_effort", "wbs_summary")
PHASES = ("in_progress", "late_start", "starting")


@dataclass(frozen=True)
class LookAheadRow:
    activity_id: str
    name: str
    wbs_path: str
    status: str
    #: ``in_progress`` (started, not finished), ``late_start`` (not started, early start before
    #: the data date) or ``starting`` (not started, early start inside the window).
    phase: str
    early_start: str | None
    early_finish: str | None
    total_float_days: float | None
    critical: bool
    percent_complete: float


@dataclass(frozen=True)
class LookAhead:
    snapshot_key: str
    snapshot_number: int
    data_date: str
    window_start: str  # ISO date, the day of the data date
    window_end: str  # ISO date, ``weeks`` weeks later
    weeks: int
    rows: tuple[LookAheadRow, ...]
    #: Rows per phase, and ``critical`` and ``total``.
    counts: Mapping[str, int]


def _day(stamp: str) -> date:
    return datetime.fromisoformat(stamp).date()


def _days(
    hours: float | None, activity: ActivityRow, day_hours: Mapping[str, float]
) -> float | None:
    if hours is None:
        return None
    per_day = day_hours.get(activity.calendar_id, DEFAULT_DAY_HOURS) or DEFAULT_DAY_HOURS
    return round(hours / per_day, 2)


def build_look_ahead(
    snapshot: SnapshotRow,
    activities: Iterable[ActivityRow],
    day_hours: Mapping[str, float],
    weeks: int = 4,
) -> LookAhead:
    """The look-ahead of ``weeks`` weeks from the data date of ``snapshot``.

    An activity is listed when it is not completed, is not a level-of-effort or WBS summary, and
    its early start is on or before the last day of the window (an activity without an early
    start is not listed). Rows are ordered by early start, then critical first, then activity id.
    Raises ``ValueError`` for a ``weeks`` outside 1 to 26 (or a boolean) and for a snapshot with
    no data date.
    """
    if isinstance(weeks, bool) or not MIN_WEEKS <= weeks <= MAX_WEEKS:
        raise ValueError(f"weeks must be between {MIN_WEEKS} and {MAX_WEEKS}")
    if snapshot.data_date is None:
        raise ValueError(f"snapshot {snapshot.key} has no data date: it has not been built")
    start = _day(snapshot.data_date)
    end = start + timedelta(weeks=weeks)
    rows: list[LookAheadRow] = []
    for a in activities:
        if a.status == "completed" or a.task_type in EXCLUDED_TYPES or a.early_start is None:
            continue
        begins = _day(a.early_start)
        if begins > end:
            continue
        if a.status == "in_progress":
            phase = "in_progress"
        elif begins < start:
            phase = "late_start"
        else:
            phase = "starting"
        rows.append(
            LookAheadRow(
                a.activity_id,
                a.name,
                a.wbs_path,
                a.status,
                phase,
                a.early_start,
                a.early_finish,
                _days(a.total_float_hr, a, day_hours),
                a.critical,
                a.percent_complete,
            )
        )
    rows.sort(key=lambda r: (r.early_start or "", not r.critical, r.activity_id))
    counts = {phase: sum(1 for r in rows if r.phase == phase) for phase in PHASES}
    counts["critical"] = sum(1 for r in rows if r.critical)
    counts["total"] = len(rows)
    return LookAhead(
        snapshot_key=snapshot.key,
        snapshot_number=snapshot.number,
        data_date=snapshot.data_date,
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        weeks=weeks,
        rows=tuple(rows),
        counts=counts,
    )


def look_ahead(conn: Connection, snapshot: SnapshotRow, weeks: int = 4) -> LookAhead:
    """Read the rows of ``snapshot`` and build its look-ahead (see ``build_look_ahead``)."""
    return build_look_ahead(
        snapshot,
        registry.activities(conn, snapshot.id),
        registry.day_hours(conn, snapshot.id),
        weeks,
    )
