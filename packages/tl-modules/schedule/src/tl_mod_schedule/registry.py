"""Reads of the schedule module: schedules, snapshots, activity references and the typed rows.

Rows are frozen dataclasses joined with ``cur_core_record`` (the title, the workflow state). Nothing
here writes, and nothing here checks a role: the entry points do (reads need ``document.read``).
The typed rows of a snapshot (``ActivityRow``, ``RelationshipRow``) are what the comparison, the
look-ahead and the resolver work on.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_xer.typed import ACTIVITY_COLUMNS, RELATIONSHIP_COLUMNS

from tl_mod_schedule.names import (
    ACTIVITY_REF_TABLE,
    ACTIVITY_TABLE,
    BUILT_STATES,
    CALENDAR_TABLE,
    PUBLISHED,
    RELATIONSHIP_TABLE,
    SCHEDULE_TABLE,
    SNAPSHOT_TABLE,
    SUPERSEDED,
    UPLOADED,
)

DEFAULT_DAY_HOURS = 8.0


def _opt(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


@dataclass(frozen=True)
class ScheduleRow:
    id: str
    scope: str
    code: str
    title: str
    schedule_type: str
    owner: str | None
    p6_project: str | None
    current_snapshot_id: str | None
    current_snapshot_number: int | None
    current_data_date: str | None


@dataclass(frozen=True)
class SnapshotRow:
    id: str
    scope: str
    key: str
    state: str  # the workflow state; a snapshot that never moved is Uploaded
    schedule_id: str
    schedule_code: str
    number: int
    p6_project_option: str | None
    source_file_id: str | None
    source_name: str | None
    source_sha256: str | None
    source_size: int | None
    requested_by: str | None
    attempts: int
    last_error: str | None
    data_date: str | None
    p6_version: str | None
    p6_project: str | None
    activity_count: int | None
    relationship_count: int | None
    wbs_count: int | None
    calendar_count: int | None
    code_count: int | None
    udf_count: int | None
    error_count: int | None
    warning_count: int | None
    report_file_id: str | None
    raw_file_id: str | None
    typed_sha256: str | None
    raw_sha256: str | None
    built_at: str | None
    published_at: str | None

    @property
    def built(self) -> bool:
        return self.state in BUILT_STATES

    @property
    def queued(self) -> bool:
        return self.source_file_id is not None


@dataclass(frozen=True)
class ActivityRefRow:
    id: str
    scope: str
    key: str
    schedule_id: str
    schedule_code: str
    activity_id: str
    first_snapshot_id: str
    first_snapshot_number: int
    present: bool
    last_seen_snapshot_id: str | None
    last_seen_number: int | None


@dataclass(frozen=True)
class ActivityRow:
    """One activity of a snapshot (``sched_activity``). Durations and floats are hours."""

    snapshot_id: str
    activity_id: str
    task_id: str
    name: str
    wbs_id: str
    wbs_path: str
    task_type: str
    status: str
    calendar_id: str
    original_duration_hr: float | None
    remaining_duration_hr: float | None
    early_start: str | None
    early_finish: str | None
    late_start: str | None
    late_finish: str | None
    actual_start: str | None
    actual_finish: str | None
    target_start: str | None
    target_finish: str | None
    total_float_hr: float | None
    free_float_hr: float | None
    percent_complete: float
    percent_type: str | None
    constraint_type: str | None
    constraint_date: str | None
    critical: bool
    longest_path: bool
    seq: int


@dataclass(frozen=True)
class RelationshipRow:
    snapshot_id: str
    pred_activity_id: str
    succ_activity_id: str
    relationship_type: str
    lag_hr: float
    seq: int


_SCHEDULE_SQL = (
    "SELECT t.id, t.scope, t.code, t.schedule_type, t.owner, t.p6_project, t.current_snapshot_id, "
    f"t.current_snapshot_number, t.current_data_date, r.title FROM {SCHEDULE_TABLE} t "
    "JOIN cur_core_record r ON r.id = t.id"
)
_SNAPSHOT_COLUMNS = (
    "id scope schedule_id schedule_code number p6_project_option source_file_id source_name "
    "source_sha256 source_size requested_by attempts last_error data_date p6_version p6_project "
    "activity_count relationship_count wbs_count calendar_count code_count udf_count error_count "
    "warning_count report_file_id raw_file_id typed_sha256 raw_sha256 built_at published_at"
).split()
_SNAPSHOT_SQL = (
    "SELECT "
    + ", ".join(f"t.{c}" for c in _SNAPSHOT_COLUMNS)
    + f", r.key, r.status FROM {SNAPSHOT_TABLE} t JOIN cur_core_record r ON r.id = t.id"
)
_REF_SQL = (
    "SELECT t.id, t.scope, t.schedule_id, t.schedule_code, t.activity_id, t.first_snapshot_id, "
    "t.first_snapshot_number, t.present, t.last_seen_snapshot_id, t.last_seen_number, r.key "
    f"FROM {ACTIVITY_REF_TABLE} t JOIN cur_core_record r ON r.id = t.id"
)


def _schedule(r: Any) -> ScheduleRow:
    return ScheduleRow(
        id=str(r.id),
        scope=str(r.scope),
        code=str(r.code),
        title=str(r.title),
        schedule_type=str(r.schedule_type),
        owner=_opt(r.owner),
        p6_project=_opt(r.p6_project),
        current_snapshot_id=_opt(r.current_snapshot_id),
        current_snapshot_number=_opt_int(r.current_snapshot_number),
        current_data_date=_opt(r.current_data_date),
    )


def _snapshot(r: Any) -> SnapshotRow:
    return SnapshotRow(
        id=str(r.id),
        scope=str(r.scope),
        key=str(r.key),
        state=str(r.status) if r.status else UPLOADED,
        schedule_id=str(r.schedule_id),
        schedule_code=str(r.schedule_code),
        number=int(r.number),
        p6_project_option=_opt(r.p6_project_option),
        source_file_id=_opt(r.source_file_id),
        source_name=_opt(r.source_name),
        source_sha256=_opt(r.source_sha256),
        source_size=_opt_int(r.source_size),
        requested_by=_opt(r.requested_by),
        attempts=int(r.attempts),
        last_error=_opt(r.last_error),
        data_date=_opt(r.data_date),
        p6_version=_opt(r.p6_version),
        p6_project=_opt(r.p6_project),
        activity_count=_opt_int(r.activity_count),
        relationship_count=_opt_int(r.relationship_count),
        wbs_count=_opt_int(r.wbs_count),
        calendar_count=_opt_int(r.calendar_count),
        code_count=_opt_int(r.code_count),
        udf_count=_opt_int(r.udf_count),
        error_count=_opt_int(r.error_count),
        warning_count=_opt_int(r.warning_count),
        report_file_id=_opt(r.report_file_id),
        raw_file_id=_opt(r.raw_file_id),
        typed_sha256=_opt(r.typed_sha256),
        raw_sha256=_opt(r.raw_sha256),
        built_at=_opt(r.built_at),
        published_at=_opt(r.published_at),
    )


def _ref(r: Any) -> ActivityRefRow:
    return ActivityRefRow(
        id=str(r.id),
        scope=str(r.scope),
        key=str(r.key),
        schedule_id=str(r.schedule_id),
        schedule_code=str(r.schedule_code),
        activity_id=str(r.activity_id),
        first_snapshot_id=str(r.first_snapshot_id),
        first_snapshot_number=int(r.first_snapshot_number),
        present=bool(r.present),
        last_seen_snapshot_id=_opt(r.last_seen_snapshot_id),
        last_seen_number=_opt_int(r.last_seen_number),
    )


# --- schedules -------------------------------------------------------------------------------


def get_schedule(conn: Connection, schedule_id: str) -> ScheduleRow | None:
    found = conn.execute(text(_SCHEDULE_SQL + " WHERE t.id = :id"), {"id": schedule_id}).first()
    return None if found is None else _schedule(found)


def find_schedule(conn: Connection, scope: str, code: str) -> ScheduleRow | None:
    found = conn.execute(
        text(_SCHEDULE_SQL + " WHERE t.scope = :scope AND t.code = :code"),
        {"scope": scope, "code": code},
    ).first()
    return None if found is None else _schedule(found)


def list_schedules(conn: Connection, scope: str) -> list[ScheduleRow]:
    found = conn.execute(
        text(_SCHEDULE_SQL + " WHERE t.scope = :scope ORDER BY t.code"), {"scope": scope}
    )
    return [_schedule(r) for r in found]


# --- snapshots -------------------------------------------------------------------------------


def get_snapshot(conn: Connection, snapshot_id: str) -> SnapshotRow | None:
    found = conn.execute(text(_SNAPSHOT_SQL + " WHERE t.id = :id"), {"id": snapshot_id}).first()
    return None if found is None else _snapshot(found)


def find_snapshot(conn: Connection, schedule_id: str, number: int) -> SnapshotRow | None:
    found = conn.execute(
        text(_SNAPSHOT_SQL + " WHERE t.schedule_id = :schedule AND t.number = :number"),
        {"schedule": schedule_id, "number": number},
    ).first()
    return None if found is None else _snapshot(found)


def list_snapshots(conn: Connection, schedule_id: str) -> list[SnapshotRow]:
    """The snapshots of a schedule, newest number first."""
    found = conn.execute(
        text(_SNAPSHOT_SQL + " WHERE t.schedule_id = :schedule ORDER BY t.number DESC"),
        {"schedule": schedule_id},
    )
    return [_snapshot(r) for r in found]


def next_number(conn: Connection, schedule_id: str) -> int:
    found = conn.execute(
        text(f"SELECT MAX(number) FROM {SNAPSHOT_TABLE} WHERE schedule_id = :schedule"),
        {"schedule": schedule_id},
    ).scalar_one()
    return (int(found) if found is not None else 0) + 1


def history(conn: Connection, schedule_id: str) -> list[SnapshotRow]:
    """The published snapshots of a schedule (Published and Superseded), oldest data date first."""
    found = conn.execute(
        text(
            _SNAPSHOT_SQL + " WHERE t.schedule_id = :schedule AND r.status IN (:a, :b) "
            "ORDER BY t.data_date, t.number"
        ),
        {"schedule": schedule_id, "a": PUBLISHED, "b": SUPERSEDED},
    )
    return [_snapshot(r) for r in found]


def previous_of(conn: Connection, snapshot: SnapshotRow) -> SnapshotRow | None:
    """The built snapshot of the schedule with the latest data date before this one's.

    "Built" is Valid, Published or Superseded: a snapshot can be compared before it is published.
    Equal data dates are ordered by number. ``None`` for the first, or while this one has no data
    date.
    """
    if snapshot.data_date is None:
        return None
    found = conn.execute(
        text(
            _SNAPSHOT_SQL + " WHERE t.schedule_id = :schedule AND r.status IN (:a, :b, :c) "
            "AND t.id <> :id AND (t.data_date < :dd OR (t.data_date = :dd AND t.number < :n)) "
            "ORDER BY t.data_date DESC, t.number DESC LIMIT 1"
        ),
        {
            "schedule": snapshot.schedule_id,
            "a": BUILT_STATES[0],
            "b": BUILT_STATES[1],
            "c": BUILT_STATES[2],
            "id": snapshot.id,
            "dd": snapshot.data_date,
            "n": snapshot.number,
        },
    ).first()
    return None if found is None else _snapshot(found)


# --- activity references ---------------------------------------------------------------------


def get_ref(conn: Connection, ref_id: str) -> ActivityRefRow | None:
    found = conn.execute(text(_REF_SQL + " WHERE t.id = :id"), {"id": ref_id}).first()
    return None if found is None else _ref(found)


def find_ref(conn: Connection, schedule_id: str, activity_id: str) -> ActivityRefRow | None:
    found = conn.execute(
        text(_REF_SQL + " WHERE t.schedule_id = :schedule AND t.activity_id = :activity"),
        {"schedule": schedule_id, "activity": activity_id},
    ).first()
    return None if found is None else _ref(found)


def refs_of(conn: Connection, schedule_id: str) -> list[ActivityRefRow]:
    found = conn.execute(
        text(_REF_SQL + " WHERE t.schedule_id = :schedule ORDER BY t.activity_id"),
        {"schedule": schedule_id},
    )
    return [_ref(r) for r in found]


# --- the typed rows ----------------------------------------------------------------------------

_ACTIVITY_SELECT = "snapshot_id, " + ", ".join(ACTIVITY_COLUMNS)
_REL_SELECT = "snapshot_id, " + ", ".join(RELATIONSHIP_COLUMNS)


def _activity(r: Any) -> ActivityRow:
    def f(name: str) -> float | None:
        value = getattr(r, name)
        return None if value is None else float(value)

    return ActivityRow(
        snapshot_id=str(r.snapshot_id),
        activity_id=str(r.activity_id),
        task_id=str(r.task_id),
        name=str(r.name),
        wbs_id=str(r.wbs_id),
        wbs_path=str(r.wbs_path),
        task_type=str(r.task_type),
        status=str(r.status),
        calendar_id=str(r.calendar_id),
        original_duration_hr=f("original_duration_hr"),
        remaining_duration_hr=f("remaining_duration_hr"),
        early_start=_opt(r.early_start),
        early_finish=_opt(r.early_finish),
        late_start=_opt(r.late_start),
        late_finish=_opt(r.late_finish),
        actual_start=_opt(r.actual_start),
        actual_finish=_opt(r.actual_finish),
        target_start=_opt(r.target_start),
        target_finish=_opt(r.target_finish),
        total_float_hr=f("total_float_hr"),
        free_float_hr=f("free_float_hr"),
        percent_complete=float(r.percent_complete),
        percent_type=_opt(r.percent_type),
        constraint_type=_opt(r.constraint_type),
        constraint_date=_opt(r.constraint_date),
        critical=bool(r.critical),
        longest_path=bool(r.longest_path),
        seq=int(r.seq),
    )


def activities(conn: Connection, snapshot_id: str) -> list[ActivityRow]:
    """Every activity of a snapshot in file order."""
    found = conn.execute(
        text(
            f"SELECT {_ACTIVITY_SELECT} FROM {ACTIVITY_TABLE} WHERE snapshot_id = :id ORDER BY seq"
        ),
        {"id": snapshot_id},
    )
    return [_activity(r) for r in found]


def get_activity(conn: Connection, snapshot_id: str, activity_id: str) -> ActivityRow | None:
    found = conn.execute(
        text(
            f"SELECT {_ACTIVITY_SELECT} FROM {ACTIVITY_TABLE} "
            "WHERE snapshot_id = :id AND activity_id = :activity"
        ),
        {"id": snapshot_id, "activity": activity_id},
    ).first()
    return None if found is None else _activity(found)


def activity_ids_present(
    conn: Connection, snapshot_id: str, candidates: Iterable[str], *, chunk: int = 500
) -> set[str]:
    """Which of the candidate activity ids the snapshot has (queried in chunks)."""
    wanted = sorted(set(candidates))
    present: set[str] = set()
    for start in range(0, len(wanted), chunk):
        part = wanted[start : start + chunk]
        params: dict[str, Any] = {"id": snapshot_id}
        names = []
        for i, value in enumerate(part):
            params[f"a{i}"] = value
            names.append(f":a{i}")
        found = conn.execute(
            text(
                f"SELECT activity_id FROM {ACTIVITY_TABLE} WHERE snapshot_id = :id "
                f"AND activity_id IN ({', '.join(names)})"
            ),
            params,
        )
        present.update(str(r.activity_id) for r in found)
    return present


def _relationship(r: Any) -> RelationshipRow:
    return RelationshipRow(
        snapshot_id=str(r.snapshot_id),
        pred_activity_id=str(r.pred_activity_id),
        succ_activity_id=str(r.succ_activity_id),
        relationship_type=str(r.relationship_type),
        lag_hr=float(r.lag_hr),
        seq=int(r.seq),
    )


def relationships(conn: Connection, snapshot_id: str) -> list[RelationshipRow]:
    found = conn.execute(
        text(
            f"SELECT {_REL_SELECT} FROM {RELATIONSHIP_TABLE} WHERE snapshot_id = :id ORDER BY seq"
        ),
        {"id": snapshot_id},
    )
    return [_relationship(r) for r in found]


def day_hours(conn: Connection, snapshot_id: str) -> dict[str, float]:
    """Work hours per day of each calendar of a snapshot, by calendar id."""
    found = conn.execute(
        text(f"SELECT calendar_id, day_hr FROM {CALENDAR_TABLE} WHERE snapshot_id = :id"),
        {"id": snapshot_id},
    )
    return {str(r.calendar_id): float(r.day_hr) for r in found}


def _like(term: str) -> str:
    """A LIKE pattern that finds ``term`` anywhere, with its own ``%``, ``_`` and ``\\`` literal."""
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def activity_page(
    conn: Connection,
    snapshot_id: str,
    *,
    critical: bool | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[int, list[ActivityRow]]:
    """A page of a snapshot's activities in file order, and how many match in all.

    ``search`` finds a text in the activity id or the name, in any case.
    """
    where = ["snapshot_id = :id"]
    params: dict[str, Any] = {"id": snapshot_id}
    if critical is not None:
        where.append("critical = :critical")
        params["critical"] = critical
    if status is not None:
        where.append("status = :status")
        params["status"] = status
    if search:
        where.append("(lower(activity_id) LIKE :q ESCAPE '\\' OR lower(name) LIKE :q ESCAPE '\\')")
        params["q"] = _like(search)
    clause = " AND ".join(where)
    total = conn.execute(
        text(f"SELECT COUNT(*) FROM {ACTIVITY_TABLE} WHERE {clause}"), params
    ).scalar_one()
    found = conn.execute(
        text(
            f"SELECT {_ACTIVITY_SELECT} FROM {ACTIVITY_TABLE} WHERE {clause} "
            "ORDER BY seq LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    )
    return int(total), [_activity(r) for r in found]


def relationships_of(conn: Connection, snapshot_id: str, activity_id: str) -> list[RelationshipRow]:
    """The relationships that name the activity as predecessor or successor, in file order."""
    found = conn.execute(
        text(
            f"SELECT {_REL_SELECT} FROM {RELATIONSHIP_TABLE} WHERE snapshot_id = :id "
            "AND (pred_activity_id = :a OR succ_activity_id = :a) ORDER BY seq"
        ),
        {"id": snapshot_id, "a": activity_id},
    )
    return [_relationship(r) for r in found]
