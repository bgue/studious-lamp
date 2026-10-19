"""Reports of the schedule module: records that point at no schedule activity.

``unscheduled_records`` answers "which work packages have no activity?" (brief 9 M11: execution
records link to the schedule through the stable activity id). It only reads, checks no role (the
entry points need ``document.read``) and is bound to a project scope in every query. The type is a
parameter because the work packages (IWPs) of the next phase do not exist yet: asked for a type no
record has, the report is empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, text

from tl_mod_schedule import registry
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.names import ACTIVITY_REF_TABLE, ACTIVITY_RELATION

#: The most rows a report returns.
MAX_LINES: Final = 1000

# A link lives in the scope of its ``from`` record (``tl_core.services.links``) and can only point
# into the same scope (or ``company``, which holds no activity reference), so the scope of the
# record bounds the join. An activity reference cannot be voided (no generic ``VoidRecord``).
_UNSCHEDULED_SQL = (
    "SELECT r.id, r.key, r.type, r.title FROM cur_core_record r "
    "WHERE r.scope = :scope AND r.type = :type AND r.voided = :no AND NOT EXISTS ("
    f"SELECT 1 FROM cur_links l JOIN {ACTIVITY_REF_TABLE} a ON a.id = l.to_id "
    "WHERE l.from_id = r.id AND l.relation = :relation AND l.status = 'active'{schedule}) "
    "ORDER BY (r.key IS NULL), r.key, r.id LIMIT :limit"
)
_ONE_SCHEDULE = " AND a.schedule_id = :schedule"


@dataclass(frozen=True)
class UnscheduledRecord:
    id: str
    key: str | None
    record_type: str
    title: str


def unscheduled_records(
    conn: Connection,
    scope: str,
    record_type: str,
    *,
    schedule_code: str | None = None,
    limit: int = MAX_LINES,
) -> list[UnscheduledRecord]:
    """The records of ``record_type`` in ``scope`` with no active link to an activity, by key.

    With ``schedule_code`` only links to that schedule's activities count (a record linked to
    another schedule is listed); without it a link to any schedule of the project counts. A link
    whose activity left the schedule is flagged stale and does not count. Void records are left
    out. ``ScheduleNotFoundError`` for a code the project lacks. At most ``limit`` (and
    ``MAX_LINES``).
    """
    schedule_id: str | None = None
    if schedule_code is not None:
        schedule = registry.find_schedule(conn, scope, schedule_code)
        if schedule is None:
            raise ScheduleNotFoundError(f"no schedule {schedule_code!r} in {scope}")
        schedule_id = schedule.id
    params: dict[str, object] = {
        "scope": scope,
        "type": record_type,
        "relation": ACTIVITY_RELATION,
        "no": False,
        "limit": max(1, min(limit, MAX_LINES)),
    }
    if schedule_id is not None:
        params["schedule"] = schedule_id
    sql = _UNSCHEDULED_SQL.format(schedule=_ONE_SCHEDULE if schedule_id is not None else "")
    found = conn.execute(text(sql), params)
    return [
        UnscheduledRecord(
            id=str(r.id),
            key=None if r.key is None else str(r.key),
            record_type=str(r.type),
            title=str(r.title),
        )
        for r in found
    ]
