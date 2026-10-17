"""Compare two snapshots of a schedule: what moved, what eroded, what changed (P1-I4-T06).

``compare(old, new)`` is a pure function of two ``SnapshotData`` (the typed rows of a snapshot read
once): the same rows give the same ``Comparison``, in the same order, byte for byte. Nothing here
reads the clock, the database or a file; ``load`` reads the rows of a stored snapshot.

What it reports, per activity id (the stable key across snapshots, brief 9 M11):

* **added** and **removed**: activities only one snapshot has;
* **date shifts**: for each of the eight dates of an activity that differs, the old and new date
  and the shift in calendar days (positive is later). A date that appears or disappears (an actual
  start recorded) has no shift;
* **float changes**: total float in days (hours divided by the work hours of the activity's own
  calendar in its own snapshot, 8 when the calendar is unknown). A negative ``delta_days`` is
  erosion;
* **logic changes**: relationships added, removed, or changed in type or lag, by (predecessor,
  successor);
* **progress changes**: percent complete, status and remaining duration;
* **duration changes**: original duration;
* **critical changes**: activities that entered or left the critical set (total float zero or less,
  not complete), including activities that are new or gone.

A comparison between any two snapshots of one schedule is possible (the previous one, a baseline).
``Comparison.limited`` cuts every list to a number of rows and says how many there were, so a view
never has to hold 60 000 rows and never cuts silently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from sqlalchemy import Connection

from tl_mod_schedule import registry
from tl_mod_schedule.registry import DEFAULT_DAY_HOURS, ActivityRow, RelationshipRow, SnapshotRow

DATE_FIELDS = (
    "early_start",
    "early_finish",
    "late_start",
    "late_finish",
    "actual_start",
    "actual_finish",
    "target_start",
    "target_finish",
)
#: A float or duration differing by less than this many hours is the same (P6 rounds to 0.01).
EPSILON_HR = 0.005


@dataclass(frozen=True)
class SnapshotData:
    """The typed rows of one snapshot, as the comparison needs them."""

    key: str
    number: int
    data_date: str
    activities: Mapping[str, ActivityRow]
    relationships: Sequence[RelationshipRow]
    day_hours: Mapping[str, float] = field(default_factory=dict[str, float])


def load(conn: Connection, snapshot: SnapshotRow) -> SnapshotData:
    """Read the typed rows of a built snapshot. ``data_date`` is set once a snapshot is built."""
    assert snapshot.data_date is not None
    return SnapshotData(
        key=snapshot.key,
        number=snapshot.number,
        data_date=snapshot.data_date,
        activities={a.activity_id: a for a in registry.activities(conn, snapshot.id)},
        relationships=registry.relationships(conn, snapshot.id),
        day_hours=registry.day_hours(conn, snapshot.id),
    )


# --- the result -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Header:
    key: str
    number: int
    data_date: str


@dataclass(frozen=True)
class Brief:
    """An activity added or removed."""

    activity_id: str
    name: str
    wbs_path: str
    status: str
    early_start: str | None
    early_finish: str | None
    total_float_days: float | None
    critical: bool


@dataclass(frozen=True)
class FieldShift:
    field: str
    old: str | None
    new: str | None
    shift_days: int | None  # calendar days, new minus old; None when a date appeared or went


@dataclass(frozen=True)
class DateShift:
    activity_id: str
    name: str
    shifts: tuple[FieldShift, ...]
    #: The largest shift in days of any date, by size (0 when only appearances or removals).
    largest_days: int
    start_shift_days: int | None  # early start
    finish_shift_days: int | None  # early finish


@dataclass(frozen=True)
class FloatChange:
    activity_id: str
    name: str
    old_days: float | None
    new_days: float | None
    delta_days: float | None
    eroded: bool  # the float is smaller than it was


@dataclass(frozen=True)
class LogicChange:
    kind: str  # added, removed or changed
    pred_activity_id: str
    succ_activity_id: str
    old_type: str | None
    new_type: str | None
    old_lag_hr: float | None
    new_lag_hr: float | None


@dataclass(frozen=True)
class ProgressChange:
    activity_id: str
    name: str
    old_percent: float
    new_percent: float
    delta_percent: float
    old_status: str
    new_status: str
    old_remaining_days: float | None
    new_remaining_days: float | None


@dataclass(frozen=True)
class DurationChange:
    activity_id: str
    name: str
    old_days: float | None
    new_days: float | None


@dataclass(frozen=True)
class CriticalChange:
    activity_id: str
    name: str
    direction: str  # entered or left
    old_float_days: float | None
    new_float_days: float | None


LIST_FIELDS = (
    "added",
    "removed",
    "date_shifts",
    "float_changes",
    "logic_changes",
    "progress_changes",
    "duration_changes",
    "critical_changes",
)


@dataclass(frozen=True)
class Comparison:
    old: Header
    new: Header
    data_date_shift_days: int
    #: The latest early finish in each snapshot (a stand-in for the project finish) and its shift.
    latest_finish_old: str | None
    latest_finish_new: str | None
    finish_shift_days: int | None
    added: tuple[Brief, ...]
    removed: tuple[Brief, ...]
    date_shifts: tuple[DateShift, ...]
    float_changes: tuple[FloatChange, ...]
    logic_changes: tuple[LogicChange, ...]
    progress_changes: tuple[ProgressChange, ...]
    duration_changes: tuple[DurationChange, ...]
    critical_changes: tuple[CriticalChange, ...]
    #: Rows per list before any cut: the same numbers whether or not ``limited`` was applied.
    totals: Mapping[str, int] = field(default_factory=dict[str, int])
    cut: bool = False

    def summary(self) -> dict[str, int]:
        """The counts a screen leads with: rows per list, and how many floats eroded."""
        return dict(self.totals)

    def limited(self, limit: int) -> Comparison:
        """Every list cut to ``limit`` rows; ``totals`` keeps the counts of the whole."""
        cut = any(self.totals[name] > limit for name in LIST_FIELDS)
        changes: dict[str, Any] = {name: getattr(self, name)[:limit] for name in LIST_FIELDS}
        return replace(self, cut=cut, **changes)


# --- the comparison ---------------------------------------------------------------------------


def _day(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def shift_days(old: str, new: str) -> int:
    """Calendar days between the dates of two ISO stamps, new minus old (the time is ignored)."""
    return (_day(new).date() - _day(old).date()).days


def _days(hours: float | None, snapshot: SnapshotData, activity: ActivityRow) -> float | None:
    if hours is None:
        return None
    per_day = snapshot.day_hours.get(activity.calendar_id, DEFAULT_DAY_HOURS) or DEFAULT_DAY_HOURS
    return round(hours / per_day, 2)


def _brief(snapshot: SnapshotData, a: ActivityRow) -> Brief:
    return Brief(
        activity_id=a.activity_id,
        name=a.name,
        wbs_path=a.wbs_path,
        status=a.status,
        early_start=a.early_start,
        early_finish=a.early_finish,
        total_float_days=_days(a.total_float_hr, snapshot, a),
        critical=a.critical,
    )


def _field_shifts(old: ActivityRow, new: ActivityRow) -> tuple[FieldShift, ...]:
    found: list[FieldShift] = []
    for name in DATE_FIELDS:
        before, after = getattr(old, name), getattr(new, name)
        if before == after:
            continue
        days = shift_days(before, after) if before is not None and after is not None else None
        found.append(FieldShift(name, before, after, days))
    return tuple(found)


def _differs(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is not b
    return abs(a - b) > EPSILON_HR


def _by_key(rows: Sequence[RelationshipRow]) -> dict[tuple[str, str], RelationshipRow]:
    return {(r.pred_activity_id, r.succ_activity_id): r for r in rows}


def _logic(old: SnapshotData, new: SnapshotData) -> tuple[LogicChange, ...]:
    before, after = _by_key(old.relationships), _by_key(new.relationships)
    found: list[LogicChange] = []
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        if a is None and b is not None:
            found.append(LogicChange("added", *key, None, b.relationship_type, None, b.lag_hr))
        elif b is None and a is not None:
            found.append(LogicChange("removed", *key, a.relationship_type, None, a.lag_hr, None))
        elif (
            a is not None
            and b is not None
            and (a.relationship_type != b.relationship_type or _differs(a.lag_hr, b.lag_hr))
        ):
            found.append(
                LogicChange(
                    "changed", *key, a.relationship_type, b.relationship_type, a.lag_hr, b.lag_hr
                )
            )
    order = {"removed": 0, "added": 1, "changed": 2}
    return tuple(
        sorted(found, key=lambda c: (order[c.kind], c.pred_activity_id, c.succ_activity_id))
    )


def compare(old: SnapshotData, new: SnapshotData) -> Comparison:
    """What changed from ``old`` to ``new``. Pure; the lists are sorted so the result is stable."""
    ids_old, ids_new = set(old.activities), set(new.activities)
    added = tuple(_brief(new, new.activities[i]) for i in sorted(ids_new - ids_old))
    removed = tuple(_brief(old, old.activities[i]) for i in sorted(ids_old - ids_new))
    shifts: list[DateShift] = []
    floats: list[FloatChange] = []
    progress: list[ProgressChange] = []
    durations: list[DurationChange] = []
    critical: list[CriticalChange] = []
    for activity_id in sorted(ids_old & ids_new):
        a, b = old.activities[activity_id], new.activities[activity_id]
        moved = _field_shifts(a, b)
        if moved:
            by_field = {s.field: s for s in moved}
            sizes = [abs(s.shift_days) for s in moved if s.shift_days is not None]
            shifts.append(
                DateShift(
                    activity_id,
                    b.name,
                    moved,
                    max(sizes, default=0),
                    by_field["early_start"].shift_days if "early_start" in by_field else None,
                    by_field["early_finish"].shift_days if "early_finish" in by_field else None,
                )
            )
        if _differs(a.total_float_hr, b.total_float_hr):
            was, now = _days(a.total_float_hr, old, a), _days(b.total_float_hr, new, b)
            delta = None if was is None or now is None else round(now - was, 2)
            floats.append(
                FloatChange(
                    activity_id,
                    b.name,
                    was,
                    now,
                    delta,
                    eroded=delta is not None and delta < 0,
                )
            )
        if (
            _differs(a.percent_complete, b.percent_complete)
            or a.status != b.status
            or _differs(a.remaining_duration_hr, b.remaining_duration_hr)
        ):
            progress.append(
                ProgressChange(
                    activity_id,
                    b.name,
                    a.percent_complete,
                    b.percent_complete,
                    round(b.percent_complete - a.percent_complete, 2),
                    a.status,
                    b.status,
                    _days(a.remaining_duration_hr, old, a),
                    _days(b.remaining_duration_hr, new, b),
                )
            )
        if _differs(a.original_duration_hr, b.original_duration_hr):
            durations.append(
                DurationChange(
                    activity_id,
                    b.name,
                    _days(a.original_duration_hr, old, a),
                    _days(b.original_duration_hr, new, b),
                )
            )
        if a.critical != b.critical:
            critical.append(
                CriticalChange(
                    activity_id,
                    b.name,
                    "entered" if b.critical else "left",
                    _days(a.total_float_hr, old, a),
                    _days(b.total_float_hr, new, b),
                )
            )
    for item in added:
        if item.critical:
            critical.append(
                CriticalChange(item.activity_id, item.name, "entered", None, item.total_float_days)
            )
    for item in removed:
        if item.critical:
            critical.append(
                CriticalChange(item.activity_id, item.name, "left", item.total_float_days, None)
            )
    # the most moved first; ties by activity id so the order never depends on the input order
    shifts.sort(key=lambda s: (-s.largest_days, s.activity_id))
    floats.sort(key=lambda c: (c.delta_days is None, c.delta_days or 0.0, c.activity_id))
    progress.sort(key=lambda c: (-abs(c.delta_percent), c.activity_id))
    critical.sort(key=lambda c: (0 if c.direction == "entered" else 1, c.activity_id))
    logic = _logic(old, new)
    finish_old = _latest(old)
    finish_new = _latest(new)
    lists: dict[str, int] = {
        "added": len(added),
        "removed": len(removed),
        "date_shifts": len(shifts),
        "float_changes": len(floats),
        "logic_changes": len(logic),
        "progress_changes": len(progress),
        "duration_changes": len(durations),
        "critical_changes": len(critical),
    }
    return Comparison(
        old=Header(old.key, old.number, old.data_date),
        new=Header(new.key, new.number, new.data_date),
        data_date_shift_days=shift_days(old.data_date, new.data_date),
        latest_finish_old=finish_old,
        latest_finish_new=finish_new,
        finish_shift_days=(
            shift_days(finish_old, finish_new)
            if finish_old is not None and finish_new is not None
            else None
        ),
        added=added,
        removed=removed,
        date_shifts=tuple(shifts),
        float_changes=tuple(floats),
        logic_changes=logic,
        progress_changes=tuple(progress),
        duration_changes=tuple(durations),
        critical_changes=tuple(critical),
        totals={**lists, "eroded": sum(1 for c in floats if c.eroded)},
    )


def _latest(snapshot: SnapshotData) -> str | None:
    finishes = [a.early_finish for a in snapshot.activities.values() if a.early_finish is not None]
    return max(finishes) if finishes else None
