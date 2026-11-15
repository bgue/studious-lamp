"""The readiness check ``scaffold_tagged`` (P2-I4B T05a fills the body; the interface is fixed).

Found through the entry point ``throughline.readiness_checks`` (T05a adds the line): the entry
point's callable takes no argument and returns the check.

For one IWP the check answers whether every scaffold the IWP ``requires`` stands (Inspected or In
Use), is tagged green and is in date (``next_due_on`` is unset or not before ``today``). It reads
through one statement with no viewer (a job runs it), and its detail and ``resolve_via`` carry
keys and counts only. A failed read is ``unknown`` with a fixed detail; the check never raises.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final

from sqlalchemy import Connection, text
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState

from tl_mod_scaffold.names import (
    GREEN,
    IN_USE,
    INSPECTED_STATE,
    REQUESTED,
    REQUIRES,
    SCAFFOLD,
    SCAFFOLD_TABLE,
)

NAME: Final = "scaffold_tagged"
VERSION: Final = "1"
NO_SCAFFOLD: Final = "this work package requires no scaffold"
UNKNOWN: Final = "the scaffolds of this work package could not be read"

#: The live ``requires`` links from the IWP to scaffolds, one statement, ordered by key then id
#: (the link filter of ``_REQUIRING_SQL`` in ``handlers/scaffold.py``, read from the other side).
_REQUIRED = text(
    "SELECT cr.id, cr.key, COALESCE(cr.status, :initial) AS state, s.tag, s.next_due_on "
    "FROM cur_links l JOIN cur_core_record cr ON cr.id = l.to_id "
    f"JOIN {SCAFFOLD_TABLE} s ON s.id = cr.id "
    "WHERE l.scope = :scope AND l.from_id = :iwp AND l.relation = :relation "
    "AND l.status <> 'retracted' AND cr.type = :type AND cr.voided = :no "
    "ORDER BY cr.key, cr.id"
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
        resolve_via=resolve or [],
        count_ok=ok,
        count_total=total,
    )


def _due_day(value: Any) -> date | None:
    """``next_due_on`` as a day: an ISO date text (SQLite) or a date (Postgres); None when unset."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _good(state: str, tag: Any, next_due: Any, today: date) -> bool:
    """Standing (Inspected or In Use), tagged green, not overdue (the due day is in date)."""
    if state not in (INSPECTED_STATE, IN_USE) or tag != GREEN:
        return False
    due = _due_day(next_due)
    return due is None or due >= today


def _answer(conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
    rows = conn.execute(
        _REQUIRED,
        {
            "initial": REQUESTED,
            "scope": iwp.scope,
            "iwp": iwp.record_id,
            "relation": REQUIRES,
            "type": SCAFFOLD,
            "no": False,
        },
    ).all()
    # One entry per scaffold, in statement order: the counts are per required scaffold.
    by_id: dict[str, Any] = {}
    for row in rows:
        by_id.setdefault(str(row.id), row)
    if not by_id:
        return _result("n_a", NO_SCAFFOLD)

    total = len(by_id)
    not_good: list[RecordRef] = []
    for row in by_id.values():
        if not _good(str(row.state), row.tag, row.next_due_on, today):
            not_good.append(
                RecordRef(record_id=str(row.id), record_type=SCAFFOLD, key=str(row.key))
            )
    good = total - len(not_good)
    detail = f"{good}/{total} required scaffolds tagged green and in date"
    if not not_good:
        return _result("ok", detail, ok=good, total=total)
    return _result("blocked", detail, not_good[:MAX_RESOLVE_VIA], good, total)


class ScaffoldTagged:
    """Every scaffold the IWP ``requires`` stands, is tagged green and is not overdue."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({SCAFFOLD})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP as of ``today`` (the job's clock; this check never reads another)."""
        try:
            return _answer(conn, iwp, today)
        except Exception:  # noqa: BLE001  (a bad record answers unknown; the check never raises)
            return _result("unknown", UNKNOWN)


def scaffold_tagged() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return ScaffoldTagged()
