"""What a screen, a client or an agent reads about schedules (brief 9 M11; P1-I4).

The TUI client interface, the API (and so the API client), the CLI and the MCP tools all return
these models, so an embedded screen, a remote one and an agent see the same fields. A listing
carries no activities; ``activity_page`` pages them. Every function here only reads, and none
checks a role (the entry points need ``document.read``).

Where a snapshot is named by number and the number is left out, the schedule's *current* snapshot
is meant; where a comparison is asked for without an older snapshot, the built snapshot with the
latest earlier data date is (``registry.previous_of``).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_schedule import registry
from tl_mod_schedule.compare import Comparison, compare, load
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    NoCurrentSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    SnapshotStateError,
)
from tl_mod_schedule.lookahead import LookAhead, look_ahead
from tl_mod_schedule.registry import (
    DEFAULT_DAY_HOURS,
    ActivityRow,
    RelationshipRow,
    ScheduleRow,
    SnapshotRow,
)
from tl_mod_schedule.resolver import (
    ActivityLink,
    AsOf,
    OrphanedLink,
    Resolution,
    links_to_activities,
    orphaned_links,
    resolve_activity,
)

#: The most activities one page holds, and the most rows a comparison view keeps per list.
MAX_PAGE = 1000
DEFAULT_COMPARE_LIMIT = 200
MAX_COMPARE_LIMIT = 5000
MAX_TREND_POINTS = 500


class SnapshotView(BaseModel):
    id: str
    key: str
    number: int
    state: str  # Uploaded | Processing | Invalid | Valid | Published | Superseded | Void
    is_current: bool
    data_date: str | None
    previous_number: int | None  # the built snapshot with the latest earlier data date
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
    source_name: str | None
    source_size: int | None
    source_sha256: str | None
    requested_by: str | None
    attempts: int
    last_error: str | None
    built_at: str | None
    published_at: str | None
    report_file_id: str | None
    raw_file_id: str | None

    @classmethod
    def of(
        cls, row: SnapshotRow, *, current_id: str | None, previous: SnapshotRow | None
    ) -> SnapshotView:
        fields = {
            name: getattr(row, name)
            for name in cls.model_fields
            if name not in {"is_current", "previous_number"}
        }
        return cls(
            **fields,
            is_current=row.id == current_id,
            previous_number=None if previous is None else previous.number,
        )


class ScheduleView(BaseModel):
    id: str
    code: str
    title: str
    schedule_type: str
    owner: str | None
    p6_project: str | None
    current_snapshot_number: int | None
    current_data_date: str | None
    snapshot_count: int

    @classmethod
    def of(cls, row: ScheduleRow, snapshot_count: int) -> ScheduleView:
        return cls(
            id=row.id,
            code=row.code,
            title=row.title,
            schedule_type=row.schedule_type,
            owner=row.owner,
            p6_project=row.p6_project,
            current_snapshot_number=row.current_snapshot_number,
            current_data_date=row.current_data_date,
            snapshot_count=snapshot_count,
        )


class ScheduleDetailView(ScheduleView):
    """A schedule with its snapshots, newest number first."""

    snapshots: list[SnapshotView]


@dataclass(frozen=True)
class ActivityPage:
    """A page of a snapshot's activities and how many matched in all."""

    snapshot_key: str
    snapshot_number: int
    data_date: str | None
    total: int
    offset: int
    rows: tuple[ActivityRow, ...]


@dataclass(frozen=True)
class ActivityDetail:
    """One activity with the relationships that name it."""

    snapshot_key: str
    snapshot_number: int
    activity: ActivityRow
    predecessors: tuple[RelationshipRow, ...]
    successors: tuple[RelationshipRow, ...]


@dataclass(frozen=True)
class TrendPoint:
    """One activity in one published snapshot (the float trend of brief 9 M11)."""

    snapshot_number: int
    data_date: str | None
    state: str
    total_float_days: float | None
    early_start: str | None
    early_finish: str | None
    percent_complete: float
    critical: bool


# --- finding things ---------------------------------------------------------------------------


def find_schedule(conn: Connection, scope: str, code: str) -> ScheduleRow:
    found = registry.find_schedule(conn, scope, code)
    if found is None:
        raise ScheduleNotFoundError(f"no schedule {code!r} in {scope}")
    return found


def find_snapshot(
    conn: Connection, schedule: ScheduleRow, number: int | None, *, built: bool = False
) -> SnapshotRow:
    """The snapshot ``number`` of a schedule, or the current one when ``number`` is ``None``.

    ``built`` also requires that its typed rows exist (Valid, Published or Superseded).
    """
    if number is None:
        if schedule.current_snapshot_id is None:
            raise NoCurrentSnapshotError(f"schedule {schedule.code} has no published snapshot yet")
        found = registry.get_snapshot(conn, schedule.current_snapshot_id)
    else:
        found = registry.find_snapshot(conn, schedule.id, number)
    if found is None:
        raise SnapshotNotFoundError(f"schedule {schedule.code} has no snapshot {number}")
    if built and not found.built:
        raise SnapshotStateError(
            f"snapshot {found.key} is {found.state}: it has no activities to read"
        )
    return found


def as_of_of(text: str | None) -> AsOf:
    """An as-of written as text: nothing or ``current`` is the current snapshot, ASCII digits a
    snapshot number, anything else a date for ``resolver.resolve_snapshot`` to judge."""
    if text is None or text in {"", "current"}:
        return None
    if text.isascii() and text.isdigit() and len(text) <= 9:
        return int(text)
    return text


# --- schedules and snapshots -----------------------------------------------------------------


def schedule_views(conn: Connection, scope: str) -> list[ScheduleView]:
    return [
        ScheduleView.of(s, len(registry.list_snapshots(conn, s.id)))
        for s in registry.list_schedules(conn, scope)
    ]


def snapshot_views(conn: Connection, schedule: ScheduleRow) -> list[SnapshotView]:
    return [
        SnapshotView.of(
            s, current_id=schedule.current_snapshot_id, previous=registry.previous_of(conn, s)
        )
        for s in registry.list_snapshots(conn, schedule.id)
    ]


def schedule_detail(conn: Connection, scope: str, code: str) -> ScheduleDetailView:
    schedule = find_schedule(conn, scope, code)
    snapshots = snapshot_views(conn, schedule)
    return ScheduleDetailView(
        **ScheduleView.of(schedule, len(snapshots)).model_dump(), snapshots=snapshots
    )


def snapshot_view(conn: Connection, scope: str, code: str, number: int | None) -> SnapshotView:
    schedule = find_schedule(conn, scope, code)
    row = find_snapshot(conn, schedule, number)
    return SnapshotView.of(
        row, current_id=schedule.current_snapshot_id, previous=registry.previous_of(conn, row)
    )


# --- the activities of a snapshot -------------------------------------------------------------


def activity_page(
    conn: Connection,
    scope: str,
    code: str,
    number: int | None = None,
    *,
    critical: bool | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> ActivityPage:
    """A page of activities in file order. ``limit`` is cut to ``MAX_PAGE``."""
    schedule = find_schedule(conn, scope, code)
    snapshot = find_snapshot(conn, schedule, number, built=True)
    total, rows = registry.activity_page(
        conn,
        snapshot.id,
        critical=critical,
        status=status,
        search=search,
        limit=max(1, min(limit, MAX_PAGE)),
        offset=max(0, offset),
    )
    return ActivityPage(
        snapshot_key=snapshot.key,
        snapshot_number=snapshot.number,
        data_date=snapshot.data_date,
        total=total,
        offset=max(0, offset),
        rows=tuple(rows),
    )


def activity_detail(
    conn: Connection, scope: str, code: str, activity_id: str, number: int | None = None
) -> ActivityDetail:
    schedule = find_schedule(conn, scope, code)
    snapshot = find_snapshot(conn, schedule, number, built=True)
    activity = registry.get_activity(conn, snapshot.id, activity_id)
    if activity is None:
        raise ActivityNotFoundError(f"snapshot {snapshot.key} has no activity {activity_id!r}")
    related = registry.relationships_of(conn, snapshot.id, activity_id)
    return ActivityDetail(
        snapshot_key=snapshot.key,
        snapshot_number=snapshot.number,
        activity=activity,
        predecessors=tuple(r for r in related if r.succ_activity_id == activity_id),
        successors=tuple(r for r in related if r.pred_activity_id == activity_id),
    )


def float_trend(conn: Connection, scope: str, code: str, activity_id: str) -> list[TrendPoint]:
    """The activity in every published snapshot, oldest data date first (at most 500 points).

    A snapshot that lacks the activity is left out of the list. An activity no snapshot has is
    ``ActivityNotFoundError``.
    """
    schedule = find_schedule(conn, scope, code)
    points: list[TrendPoint] = []
    for snapshot in registry.history(conn, schedule.id)[-MAX_TREND_POINTS:]:
        a = registry.get_activity(conn, snapshot.id, activity_id)
        if a is None:
            continue
        hours = registry.day_hours(conn, snapshot.id).get(a.calendar_id) or DEFAULT_DAY_HOURS
        points.append(
            TrendPoint(
                snapshot_number=snapshot.number,
                data_date=snapshot.data_date,
                state=snapshot.state,
                total_float_days=None
                if a.total_float_hr is None
                else round(a.total_float_hr / hours, 2),
                early_start=a.early_start,
                early_finish=a.early_finish,
                percent_complete=a.percent_complete,
                critical=a.critical,
            )
        )
    if not points:
        raise ActivityNotFoundError(f"no published snapshot of {code} has activity {activity_id!r}")
    return points


# --- comparison, look-ahead, links -------------------------------------------------------------


def comparison(
    conn: Connection,
    scope: str,
    code: str,
    new: int | None = None,
    old: int | None = None,
    *,
    limit: int = DEFAULT_COMPARE_LIMIT,
) -> Comparison:
    """What changed from ``old`` to ``new`` (default: the current snapshot and the one before).

    Both must be built. ``SnapshotNotFoundError`` when ``old`` is not given and ``new`` is the
    first. Each list is cut to ``limit`` rows (at most 5000); ``totals`` keeps the full counts.
    """
    schedule = find_schedule(conn, scope, code)
    newer = find_snapshot(conn, schedule, new, built=True)
    if old is None:
        older = registry.previous_of(conn, newer)
        if older is None:
            raise SnapshotNotFoundError(f"snapshot {newer.key} has no earlier snapshot to compare")
    else:
        older = find_snapshot(conn, schedule, old, built=True)
    result = compare(load(conn, older), load(conn, newer))
    return result.limited(max(1, min(limit, MAX_COMPARE_LIMIT)))


def look_ahead_view(
    conn: Connection, scope: str, code: str, number: int | None = None, weeks: int = 4
) -> LookAhead:
    """The look-ahead of a built snapshot (default: the current one). ``ValueError`` for weeks."""
    schedule = find_schedule(conn, scope, code)
    return look_ahead(conn, find_snapshot(conn, schedule, number, built=True), weeks)


def resolution(
    conn: Connection, scope: str, code: str, activity_id: str, as_of: AsOf = None
) -> Resolution:
    """What ``activity_id`` is now (``as_of`` ``None``) or as of a snapshot number or a date."""
    schedule = find_schedule(conn, scope, code)
    return resolve_activity(conn, schedule.id, activity_id, as_of)


def orphans(conn: Connection, scope: str, code: str) -> list[OrphanedLink]:
    """The links the last publication flagged because their activity left the schedule."""
    return orphaned_links(conn, find_schedule(conn, scope, code).id)


def activity_links(conn: Connection, record_id: str) -> list[ActivityLink]:
    """The activity links of a record and what each resolves to now."""
    return links_to_activities(conn, record_id)
