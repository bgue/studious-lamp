"""The readiness check ``labour_requested`` (P2-I4B T05b).

It replaces the ``n_a`` placeholder of the same name in ``tl_mod_awp.checks_na`` (T05b moves the
entry point). Found through the entry point ``throughline.readiness_checks``.

For one IWP the check answers whether an approved labour requisition serves it and covers its
planned window. It reads the requisitions tables only, through one statement with no viewer (a
job runs it). Its detail and ``resolve_via`` carry fixed texts and keys only. A failed read is
``unknown`` with a fixed detail; the check never raises.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final

from sqlalchemy import Connection, text
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState
from tl_mod_requisitions.names import (
    LABOR,
    LABOR_TABLE,
    ST_APPROVED,
    ST_CANCELLED,
    ST_CLOSED,
    ST_DONE,
    ST_IN_PROGRESS,
    ST_REJECTED,
    ST_REQUESTED,
    ST_SCHEDULED,
)

NAME: Final = "labour_requested"
VERSION: Final = "1"
NO_ESTIMATE: Final = "this work package has no labour estimate yet"
NO_REQUISITION: Final = "no labour requisition for this work package"
NOT_APPROVED: Final = "a labour requisition is requested and not yet approved"
NOT_COVERED: Final = "no approved labour requisition covers the planned window"
COVERED: Final = "an approved labour requisition covers the planned window"
UNKNOWN: Final = "the labour requisitions of this work package could not be read"

#: States that count as approved: an approved requisition or any state after it.
_APPROVED_OR_LATER: Final = frozenset(
    {ST_APPROVED, ST_SCHEDULED, ST_IN_PROGRESS, ST_DONE, ST_CLOSED}
)
#: States that count for nothing.
_DEAD: Final = frozenset({ST_REJECTED, ST_CANCELLED})

#: The labour requisitions of one IWP, one statement, ordered by key then id. A record that never
#: moved reads as ``Requested``; the states are filtered in Python.
_LABOUR_SQL = text(
    "SELECT t.id, r.key, COALESCE(r.status, :initial) AS state, t.start_date, t.end_date "
    f"FROM {LABOR_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.for_record_id = :iwp AND r.scope = :scope AND r.voided = :no "
    "ORDER BY r.key, r.id"
)


def _result(state: CheckState, detail: str, resolve: list[RecordRef] | None = None) -> CheckResult:
    return CheckResult(
        name=NAME,
        version=VERSION,
        state=state,
        detail=detail,
        resolve_via=resolve or [],
        count_ok=None,
        count_total=None,
    )


def _covers(start: Any, end: Any, planned_start: date, planned_finish: date) -> bool:
    """The requisition window (ISO dates) contains the planned window; an unset date never does."""
    if start is None or end is None:
        return False
    return str(start) <= planned_start.isoformat() and str(end) >= planned_finish.isoformat()


def _answer(conn: Connection, iwp: IwpFacts) -> CheckResult:
    rows = conn.execute(
        _LABOUR_SQL,
        {"initial": ST_REQUESTED, "iwp": iwp.record_id, "scope": iwp.scope, "no": False},
    ).all()
    live = [row for row in rows if str(row.state) not in _DEAD]
    approved = [row for row in live if str(row.state) in _APPROVED_OR_LATER]
    requested = [row for row in live if str(row.state) == ST_REQUESTED]

    def refs(found: list[Any]) -> list[RecordRef]:
        return [
            RecordRef(record_id=str(r.id), record_type=LABOR, key=str(r.key))
            for r in found[:MAX_RESOLVE_VIA]
        ]

    if approved:
        planned_start, planned_finish = iwp.planned_start, iwp.planned_finish
        if planned_start is None or planned_finish is None:
            return _result("ok", COVERED)
        if any(_covers(r.start_date, r.end_date, planned_start, planned_finish) for r in approved):
            return _result("ok", COVERED)
    if requested:
        return _result("pending", NOT_APPROVED, refs(requested))
    if approved:
        return _result("blocked", NOT_COVERED, refs(approved))
    return _result("blocked", NO_REQUISITION)


class LabourRequested:
    """An approved labour requisition serves the IWP and covers its planned window."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({LABOR})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP. ``today`` is unused: the window is the IWP's planned dates."""
        del today
        if iwp.estimated_hours is None or iwp.estimated_hours <= 0:
            return _result("n_a", NO_ESTIMATE)
        try:
            return _answer(conn, iwp)
        except Exception:  # noqa: BLE001  (a bad record answers unknown; the check never raises)
            return _result("unknown", UNKNOWN)


def labour_requested() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return LabourRequested()
