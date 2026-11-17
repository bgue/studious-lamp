"""The schedule module's line-level report (``tl report activities``; V3-P0c).

One row per activity of each schedule's current snapshot (``current_snapshot_id``; a schedule with
none adds no rows), schedules by code, activities in file order, paged with the registry's
``activity_page`` offset. The schedule list read (the API's ``routes/schedule.py``) takes the action
``document.read`` through ``guard`` only and no module word, so the report checks none either.
Schedules carry no class. No record id is a column; the schedule code and the activity id name the
row. Planned dates are the activity's target dates; the float is the stored total float in hours.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.modules import Report

from tl_mod_schedule import registry

#: The page size the activities are read with (a monkeypatched value in the tests).
_PAGE: Final = 500
ACTIVITY_COLUMNS: Final = (
    "schedule", "snapshot", "activity_id", "name", "state", "planned_start", "planned_finish",
    "actual_start", "actual_finish", "total_float_hr",
)  # fmt: skip


def activity_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    for schedule in registry.list_schedules(conn, scope):
        if schedule.current_snapshot_id is None:
            continue
        snapshot = registry.get_snapshot(conn, schedule.current_snapshot_id)
        if snapshot is None:
            continue
        offset = 0
        while True:
            _, page = registry.activity_page(conn, snapshot.id, limit=_PAGE, offset=offset)
            for row in page:
                yield {
                    "schedule": schedule.code,
                    "snapshot": snapshot.number,
                    "activity_id": row.activity_id,
                    "name": row.name,
                    "state": row.status,
                    "planned_start": row.target_start,
                    "planned_finish": row.target_finish,
                    "actual_start": row.actual_start,
                    "actual_finish": row.actual_finish,
                    "total_float_hr": row.total_float_hr,
                }
            offset += len(page)
            if len(page) < _PAGE:
                break


REPORTS: Final = (Report("activities", "Schedule activities", ACTIVITY_COLUMNS, activity_rows),)
