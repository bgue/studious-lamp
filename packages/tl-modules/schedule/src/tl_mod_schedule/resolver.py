"""Resolve a link to an activity: to the current snapshot, as of an earlier one, or orphaned (T07).

A link from a record points at an activity *reference* (``schedule.ActivityRef``), never at a
snapshot row (brief 9 M11). This module is the one place that decides what such a link means:

* ``resolve_snapshot`` says which snapshot an *as-of* names: nothing (the current one), a snapshot
  number, or a date (the latest published snapshot whose data date is on or before that day);
* ``resolve_activity`` reads the activity of that snapshot and says in which state the link is;
* ``links_to_activities`` lists the activity links of one record, each resolved the way its own pin
  asks (floating: the current snapshot; pinned to a number: that snapshot);
* ``orphaned_links`` lists the links of a schedule whose activity left the current snapshot (the
  link-health view of brief 7.3).

Only *published* snapshots (Published and Superseded) are history: a snapshot that is built but not
published is not what the project was planning with. Nothing here writes, and nothing here checks a
role (reads need ``document.read``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection, text

from tl_mod_schedule import registry
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.names import ACTIVITY_REF_TABLE, ORPHAN_REASON

#: ``None`` is the current snapshot; an ``int`` a snapshot number; a ``str`` a date written
#: ``YYYY-MM-DD`` (the end of that day) or ``YYYY-MM-DDTHH:MM``.
AsOf = int | str | None
#: ``current``: the activity of the current snapshot. ``as_of``: the activity of an earlier
#: snapshot. ``orphaned``: the snapshot has no such activity but a reference to it exists (it
#: left the schedule). ``unknown_activity``: the snapshot has no such activity and nothing ever
#: referred to it. ``no_snapshot``: the as-of names no published snapshot.
State = Literal["current", "as_of", "orphaned", "unknown_activity", "no_snapshot"]

MAX_PIN_DIGITS = 9
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_MINUTE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


@dataclass(frozen=True)
class Resolution:
    state: State
    schedule_code: str
    activity_id: str
    #: The snapshot the activity was read from; ``None`` for ``no_snapshot``.
    snapshot_id: str | None
    snapshot_number: int | None
    data_date: str | None
    activity: registry.ActivityRow | None


@dataclass(frozen=True)
class ActivityLink:
    """One activity link of a record and what it resolves to now."""

    link_id: str
    status: str  # the link's own status: active or stale
    pin: str | None
    reason: str | None
    ref_key: str
    resolution: Resolution


def resolve_snapshot(
    conn: Connection, schedule_id: str, as_of: AsOf = None
) -> registry.SnapshotRow | None:
    """The published snapshot ``as_of`` names, or ``None``.

    ``None`` names the schedule's current snapshot. An integer names a snapshot by number if it
    is Published or Superseded. A string names the latest published snapshot whose data date is on
    or before it: ``YYYY-MM-DD`` means the end of that day, ``YYYY-MM-DDTHH:MM`` that minute. Any
    other string names nothing. Raises ``ScheduleNotFoundError`` for an unknown schedule.
    """
    schedule = registry.get_schedule(conn, schedule_id)
    if schedule is None:
        raise ScheduleNotFoundError(f"no schedule {schedule_id!r}")
    if as_of is None:
        if schedule.current_snapshot_id is None:
            return None
        return registry.get_snapshot(conn, schedule.current_snapshot_id)
    published = registry.history(conn, schedule_id)
    if isinstance(as_of, bool):
        return None
    if isinstance(as_of, int):
        return next((s for s in published if s.number == as_of), None)
    if _DAY.fullmatch(as_of):
        limit = f"{as_of}T23:59"
    elif _MINUTE.fullmatch(as_of):
        limit = as_of
    else:
        return None
    found = [s for s in published if s.data_date is not None and s.data_date <= limit]
    return found[-1] if found else None


def resolve_activity(
    conn: Connection, schedule_id: str, activity_id: str, as_of: AsOf = None
) -> Resolution:
    """What ``activity_id`` of the schedule is, as of ``as_of`` (see ``State``)."""
    schedule = registry.get_schedule(conn, schedule_id)
    if schedule is None:
        raise ScheduleNotFoundError(f"no schedule {schedule_id!r}")
    snapshot = resolve_snapshot(conn, schedule_id, as_of)
    if snapshot is None:
        return Resolution("no_snapshot", schedule.code, activity_id, None, None, None, None)
    activity = registry.get_activity(conn, snapshot.id, activity_id)
    state: State
    if activity is not None:
        state = "current" if as_of is None else "as_of"
    elif registry.find_ref(conn, schedule_id, activity_id) is not None:
        state = "orphaned"
    else:
        state = "unknown_activity"
    return Resolution(
        state,
        schedule.code,
        activity_id,
        snapshot.id,
        snapshot.number,
        snapshot.data_date,
        activity,
    )


_LINKS_SQL = text(
    "SELECT l.link_id, l.status, l.pin, l.reason, r.key AS ref_key, a.schedule_id, a.activity_id "
    f"FROM cur_links l JOIN {ACTIVITY_REF_TABLE} a ON a.id = l.to_id "
    "JOIN cur_core_record r ON r.id = a.id "
    "WHERE l.from_id = :record AND l.status IN ('active', 'stale') "
    "ORDER BY l.created_at, l.link_id"
)


def _pin_as_of(pin: str | None) -> AsOf:
    """A link's pin as an as-of: a snapshot number, or floating.

    A pin is the label a person gave (``RepinLink``), so only plain ASCII digits (nine at most:
    ``int`` refuses a text of thousands) name a snapshot; any other pin floats.
    """
    if pin is not None and pin.isascii() and pin.isdigit() and len(pin) <= MAX_PIN_DIGITS:
        return int(pin)
    return None


def links_to_activities(conn: Connection, record_id: str) -> list[ActivityLink]:
    """The activity links of a record (active and stale), oldest first, each resolved by its pin."""
    found: list[ActivityLink] = []
    for row in conn.execute(_LINKS_SQL, {"record": record_id}):
        found.append(
            ActivityLink(
                link_id=str(row.link_id),
                status=str(row.status),
                pin=None if row.pin is None else str(row.pin),
                reason=None if row.reason is None else str(row.reason),
                ref_key=str(row.ref_key),
                resolution=resolve_activity(
                    conn,
                    str(row.schedule_id),
                    str(row.activity_id),
                    _pin_as_of(row.pin),
                ),
            )
        )
    return found


_ORPHANED_SQL = text(
    "SELECT l.link_id, l.from_id, l.reason, a.activity_id, a.last_seen_number "
    f"FROM cur_links l JOIN {ACTIVITY_REF_TABLE} a ON a.id = l.to_id "
    "WHERE a.schedule_id = :schedule AND a.present = :absent AND l.status = 'stale' "
    "AND l.reason LIKE :reason ORDER BY a.activity_id, l.created_at, l.link_id"
)


@dataclass(frozen=True)
class OrphanedLink:
    link_id: str
    from_id: str
    activity_id: str
    last_seen_number: int | None
    reason: str


def orphaned_links(conn: Connection, schedule_id: str) -> list[OrphanedLink]:
    """The stale links of a schedule whose activity left the current snapshot.

    Only links the module flagged on a publication (their reason starts with ``ORPHAN_REASON``)
    are listed, ordered by activity id, then by age of the link.
    """
    rows = conn.execute(
        _ORPHANED_SQL,
        {"schedule": schedule_id, "absent": False, "reason": ORPHAN_REASON + "%"},
    )
    return [
        OrphanedLink(
            link_id=str(row.link_id),
            from_id=str(row.from_id),
            activity_id=str(row.activity_id),
            last_seen_number=None if row.last_seen_number is None else int(row.last_seen_number),
            reason=str(row.reason),
        )
        for row in rows
    ]
