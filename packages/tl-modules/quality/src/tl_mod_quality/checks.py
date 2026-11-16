"""The readiness check ``inspections_planned`` (P2-INSP-S3; inspections design section 5).

Found through the entry point ``throughline.readiness_checks``; the entry point's callable takes no
argument and returns the check. For one IWP it reads the inspections that name it
(``cur_quality_inspection.for_iwp_id``) and answers:

* ``n_a``: none counts and ``quality.inspections.required_for_iwp`` is off;
* ``blocked``: the setting is on and none counts; a linked inspection is still Planned; or a hold
  point is Done (or Verified) with ``reject`` and no live reinspection;
* ``pending``: every inspection is Scheduled or better and one scheduled before the IWP's planned
  start is not yet Done;
* ``ok``: otherwise.

A Cancelled inspection counts in neither number. A hold point that is not yet released does not
un-ready an issued IWP. The check is read-only, takes no viewer (a job runs it) and answers with
keys and counts only, never a title. A failed read is ``unknown`` with a fixed detail.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Connection, text
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of

from tl_mod_quality.names import CANCELLED, DONE, INSPECTION, INSPECTION_TABLE, PLANNED, VERIFIED

NAME = "inspections_planned"
VERSION = "1"
SETTING = "quality.inspections.required_for_iwp"
NO_INSPECTIONS = "no inspection is planned for this work package"
REQUIRED_NONE = "an inspection is required and none is planned"
UNKNOWN = "the inspections of this work package could not be read"
MAX_ROWS = 1000
_DONE = frozenset({DONE, VERIFIED})

#: The IWP's live inspections (one statement); a record without a status never moved: Planned.
_SQL = text(
    "SELECT i.id, r.key, r.status, i.point, i.result, i.scheduled_for, "
    "(SELECT count(*) FROM " + INSPECTION_TABLE + " c JOIN cur_core_record cr ON cr.id = c.id "
    "WHERE c.reinspection_of_id = i.id AND (cr.status IS NULL OR cr.status <> 'Cancelled')) "
    "AS children "
    "FROM " + INSPECTION_TABLE + " i JOIN cur_core_record r ON r.id = i.id "
    "WHERE i.for_iwp_id = :iwp AND i.scope = :scope ORDER BY r.key LIMIT :limit"
)


def _result(
    state: CheckState,
    detail: str,
    resolve: list[RecordRef] | None = None,
    ok: int | None = None,
    total: int | None = None,
) -> CheckResult:
    return CheckResult(
        name=NAME,
        version=VERSION,
        state=state,
        detail=detail,
        resolve_via=(resolve or [])[:MAX_RESOLVE_VIA],
        count_ok=ok,
        count_total=total,
    )


def _ref(row: dict[str, Any]) -> RecordRef:
    return RecordRef(record_id=str(row["id"]), record_type=INSPECTION, key=str(row["key"]))


def _status(row: dict[str, Any]) -> str:
    return PLANNED if row["status"] is None else str(row["status"])


def _answer(conn: Connection, iwp: IwpFacts) -> CheckResult:
    found = conn.execute(_SQL, {"iwp": iwp.record_id, "scope": iwp.scope, "limit": MAX_ROWS + 1})
    rows = [dict(r) for r in found.mappings()]
    if len(rows) > MAX_ROWS:
        return _result("unknown", UNKNOWN)
    live = [r for r in rows if _status(r) != CANCELLED]
    required = bool(value_of(conn, SETTING, project=project_of_scope(iwp.scope)))
    if not live:
        return _result("blocked", REQUIRED_NONE) if required else _result("n_a", NO_INSPECTIONS)
    total = len(live)
    planned = [r for r in live if _status(r) == PLANNED]
    ok = total - len(planned)
    rejected = [
        r
        for r in live
        if _status(r) in _DONE
        and r["point"] == "hold"
        and r["result"] == "reject"
        and not r["children"]
    ]
    if planned or rejected:
        detail = f"{ok}/{total} inspections scheduled or done"
        if planned:
            detail += f"; {len(planned)} not yet scheduled"
        if rejected:
            detail += f"; {len(rejected)} hold point rejected without reinspection"
        return _result("blocked", detail, [_ref(r) for r in [*planned, *rejected]], ok, total)
    start = None if iwp.planned_start is None else iwp.planned_start.isoformat()
    late = [
        r
        for r in live
        if start is not None
        and _status(r) not in _DONE
        and r["scheduled_for"] is not None
        and str(r["scheduled_for"]) < start
    ]
    if late:
        detail = f"{ok}/{total} inspections scheduled or done; {len(late)} due before the start"
        return _result("pending", detail, [_ref(r) for r in late], ok, total)
    return _result("ok", f"{ok}/{total} inspections scheduled or done", ok=ok, total=total)


class InspectionsPlanned:
    """The inspections the IWP needs are planned, scheduled and not rejected."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({INSPECTION})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP. ``today`` is not used: the IWP's planned start is the line."""
        del today
        try:
            return _answer(conn, iwp)
        except Exception:  # noqa: BLE001  (a bad read answers unknown; the check never raises)
            return _result("unknown", UNKNOWN)


def inspections_planned() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return InspectionsPlanned()
