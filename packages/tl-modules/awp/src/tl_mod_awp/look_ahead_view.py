"""The look-ahead joined with the IWPs linked to each activity and their readiness (P2-I5-T03).

Reads only; ids and counts only. `open_blocking` counts per IWP with the viewer, never truncated.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from sqlalchemy import Connection, bindparam, text
from tl_core import confidentiality
from tl_core.confidentiality import Viewer
from tl_core.constraints.queries import count_constraints
from tl_mod_schedule.lookahead import LookAheadRow, look_ahead
from tl_mod_schedule.registry import SnapshotRow

from tl_mod_awp import common, iwp_views
from tl_mod_awp.names import READINESS_CHECK_TABLE, READINESS_TABLE
from tl_mod_awp.readiness.engine import PASSING


@dataclass(frozen=True)
class LookAheadIwp:
    id: str
    number: str
    state: str
    planned_start: str | None
    need_by: str | None  # planned_start minus awp.iwp.ready_lead_weeks weeks (ISO date)
    evaluated: bool  # False: never evaluated (then ready False, checks 0/0)
    ready: bool
    checks_ok: int  # checks in state ok or n_a
    checks_total: int
    open_blocking: int  # Open or Assigned blocking constraints the viewer may read


@dataclass(frozen=True)
class LookAheadItem:
    row: LookAheadRow
    iwps: tuple[LookAheadIwp, ...]  # by IWP number


@dataclass(frozen=True)
class LookAheadView:
    snapshot_key: str
    data_date: str
    window_start: str
    window_end: str
    weeks: int
    lead_weeks: int
    counts: Mapping[str, int]  # the look_ahead counts
    items: tuple[LookAheadItem, ...]  # the look_ahead rows, same order


#: The most ids one IN list carries (the chunk size of the link read).
_CHUNK: Final = 500
#: Workflow states that are left off the look-ahead.
_LEFT_OUT: Final = frozenset({"Cancelled", "Split"})

_LINKS_SQL = text(
    "SELECT l.from_id, a.activity_id FROM cur_links l "
    "JOIN cur_schedule_activity_ref a ON a.id = l.to_id "
    "WHERE a.schedule_id = :schedule AND a.scope = :scope AND l.scope = :scope "
    "AND l.status = 'active' AND a.activity_id IN :ids"
).bindparams(bindparam("ids", expanding=True))
_READY_SQL = text(f"SELECT iwp_id, ready FROM {READINESS_TABLE} WHERE iwp_id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)
_CHECKS_SQL = text(
    "SELECT iwp_id, COUNT(*) AS total, "
    "SUM(CASE WHEN state IN :passing THEN 1 ELSE 0 END) AS ok "
    f"FROM {READINESS_CHECK_TABLE} WHERE iwp_id IN :ids GROUP BY iwp_id"
).bindparams(bindparam("ids", expanding=True), bindparam("passing", expanding=True))


def _chunks(values: Sequence[str]) -> Iterator[list[str]]:
    for start in range(0, len(values), _CHUNK):
        yield list(values[start : start + _CHUNK])


def _need_by(planned_start: str | None, lead_weeks: int) -> str | None:
    if planned_start is None:
        return None
    return (date.fromisoformat(planned_start) - timedelta(weeks=lead_weeks)).isoformat()


def _links(
    conn: Connection, snapshot: SnapshotRow, scope: str, activity_ids: list[str]
) -> list[tuple[str, str]]:
    """(IWP id, activity id) for every active link to a listed activity; one statement per chunk."""
    found: list[tuple[str, str]] = []
    for ids in _chunks(activity_ids):
        rows = conn.execute(
            _LINKS_SQL, {"schedule": snapshot.schedule_id, "scope": scope, "ids": ids}
        ).all()
        found.extend((str(r[0]), str(r[1])) for r in rows)
    return found


def _readiness(
    conn: Connection, ids: list[str]
) -> tuple[dict[str, bool], dict[str, tuple[int, int]]]:
    """The ``ready`` flag of each evaluated IWP, and (ok, total) of its checks. Two statements."""
    ready_by = {str(r[0]): bool(r[1]) for r in conn.execute(_READY_SQL, {"ids": ids}).all()}
    checks: dict[str, tuple[int, int]] = {}
    for r in conn.execute(_CHECKS_SQL, {"ids": ids, "passing": sorted(PASSING)}).all():
        checks[str(r[0])] = (int(r[2] or 0), int(r[1]))
    return ready_by, checks


def _open_blocking(
    conn: Connection, scope: str, viewer: Viewer | None, ids: set[str]
) -> dict[str, int]:
    """Open or Assigned blocking constraints per IWP id, by count (never a truncated list): one
    ``count_constraints`` per IWP and open state, the viewer's class filter applied."""
    return {
        iwp_id: sum(
            count_constraints(
                conn, scope, subject_id=iwp_id, state=state, blocking=True, viewer=viewer
            )
            for state in iwp_views.OPEN_STATES
        )
        for iwp_id in sorted(ids)
    }


def look_ahead_view(
    conn: Connection,
    scope: str,
    snapshot: SnapshotRow,
    viewer: Viewer | None = None,
    *,
    weeks: int = 4,
) -> LookAheadView:
    look = look_ahead(conn, snapshot, weeks, scope=scope)
    lead_weeks = int(common.setting_value(conn, scope, "awp.iwp.ready_lead_weeks") or 0)
    activity_ids = sorted({row.activity_id for row in look.rows})

    with confidentiality.use_viewer(viewer) if viewer is not None else nullcontext():
        visible = {
            iwp.id: iwp
            for iwp in iwp_views.iwp_list(conn, scope, limit=500)
            if iwp.state not in _LEFT_OUT
        }
        links = [
            (from_id, activity)
            for from_id, activity in _links(conn, snapshot, scope, activity_ids)
            if from_id in visible
        ]
        linked = sorted({from_id for from_id, _ in links})
        ready_by: dict[str, bool] = {}
        checks: dict[str, tuple[int, int]] = {}
        blocking: dict[str, int] = {}
        if linked:
            ready_by, checks = _readiness(conn, linked)
            blocking = _open_blocking(conn, scope, viewer, set(linked))

    by_activity: dict[str, set[str]] = defaultdict(set)
    for from_id, activity in links:
        by_activity[activity].add(from_id)

    def build(iwp_id: str) -> LookAheadIwp:
        iwp = visible[iwp_id]
        evaluated = iwp_id in ready_by
        checks_ok, checks_total = checks.get(iwp_id, (0, 0))
        return LookAheadIwp(
            id=iwp.id,
            number=iwp.number,
            state=iwp.state,
            planned_start=iwp.planned_start,
            need_by=_need_by(iwp.planned_start, lead_weeks),
            evaluated=evaluated,
            ready=evaluated and ready_by[iwp_id],
            checks_ok=checks_ok,
            checks_total=checks_total,
            open_blocking=blocking.get(iwp_id, 0),
        )

    items = tuple(
        LookAheadItem(
            row=row,
            iwps=tuple(
                sorted(
                    (build(iwp_id) for iwp_id in by_activity.get(row.activity_id, ())),
                    key=lambda x: x.number,
                )
            ),
        )
        for row in look.rows
    )
    return LookAheadView(
        snapshot_key=look.snapshot_key,
        data_date=look.data_date,
        window_start=look.window_start,
        window_end=look.window_end,
        weeks=look.weeks,
        lead_weeks=lead_weeks,
        counts=look.counts,
        items=items,
    )
