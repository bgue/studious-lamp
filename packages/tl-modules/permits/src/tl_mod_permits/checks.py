"""The readiness check ``permits_planned`` (P2-PTW-S4; permits design section 6).

Found through the entry point ``throughline.readiness_checks``; the entry point's callable takes no
argument and returns the check. For one IWP it reads the permits that name it
(``cur_permits_permit.for_record_id``) and answers:

* ``n_a``: no permit counts and ``permits.required_for_iwp`` is off;
* ``blocked``: the setting is on and no permit counts; or a permit is Rejected, Suspended or Lapsed
  and no other live permit of its type exists for the IWP;
* ``pending``: a permit is Requested, or a counted permit is not yet Approved or Active (a
  Suspended or Lapsed one covered by a live permit of its type, or one Handed back);
* ``ok``: every counted permit is Approved or Active and not Lapsed.

A Cancelled, Closed or Rejected permit counts in neither number. A live permit is Requested,
Approved or Active and not Lapsed. Lapsed is derived by ``rules.effective_state`` with ``now`` the
start of ``today`` in UTC (day granularity); no clock is read. The check is read-only, takes no
viewer (a job runs it) and answers with keys and counts only, never a description or a holder. A
failed read is ``unknown`` with a fixed detail.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import Connection, text
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of

from tl_mod_permits import rules
from tl_mod_permits.names import (
    ACTIVE,
    APPROVED,
    CANCELLED,
    CLOSED,
    LAPSED,
    PERMIT,
    PERMIT_TABLE,
    REJECTED,
    REQUESTED,
    SUSPENDED,
)

NAME = "permits_planned"
VERSION = "1"
SETTING = "permits.required_for_iwp"
NO_PERMITS = "no permit is planned for this work package"
REQUIRED_NONE = "a permit is required and none is planned"
UNKNOWN = "the permits of this work package could not be read"
MAX_ROWS = 1000
_OUT = frozenset({CANCELLED, CLOSED, REJECTED})
_PROBLEM = frozenset({REJECTED, SUSPENDED, LAPSED})
_LIVE = frozenset({REQUESTED, APPROVED, ACTIVE})
_GOOD = frozenset({APPROVED, ACTIVE})

#: The IWP's permits (one read-only statement); a permit with no transition yet is Requested.
_SQL = text(
    f"SELECT p.id, r.key, p.permit_type, COALESCE(w.state, '{REQUESTED}') AS state, p.valid_until "
    f"FROM {PERMIT_TABLE} p JOIN cur_core_record r ON r.id = p.id "
    "LEFT JOIN cur_workflow_state w ON w.record_id = p.id "
    "WHERE p.for_record_id = :iwp AND p.scope = :scope AND r.voided = :no "
    "ORDER BY r.key, r.id LIMIT :limit"
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
    return RecordRef(record_id=str(row["id"]), record_type=PERMIT, key=str(row["key"]))


def _when(value: Any) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(str(value))
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _shown(raw: Any, now: datetime) -> dict[str, Any]:
    """The row with its state as shown at ``now`` (Lapsed derived, never stored)."""
    row = dict(raw)
    row["state"] = rules.effective_state(str(raw["state"]), _when(raw["valid_until"]), now)
    return row


def _answer(conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
    now = datetime.combine(today, time.min, tzinfo=UTC)
    params = {"iwp": iwp.record_id, "scope": iwp.scope, "no": False, "limit": MAX_ROWS + 1}
    raws = conn.execute(_SQL, params).mappings().all()
    if len(raws) > MAX_ROWS:
        return _result("unknown", UNKNOWN)
    rows = [_shown(raw, now) for raw in raws]
    counted = [r for r in rows if r["state"] not in _OUT]
    live_types = {r["permit_type"] for r in rows if r["state"] in _LIVE and r["state"] != LAPSED}
    blocking = [r for r in rows if r["state"] in _PROBLEM and r["permit_type"] not in live_types]
    required = bool(value_of(conn, SETTING, project=project_of_scope(iwp.scope)))
    total = len(counted)
    ok = sum(1 for r in counted if r["state"] in _GOOD)
    if not counted and not blocking:
        return _result("blocked", REQUIRED_NONE) if required else _result("n_a", NO_PERMITS)
    detail = f"{ok}/{total} permits approved or active"
    if blocking:
        detail += f"; {len(blocking)} rejected, suspended or lapsed with no live permit of its type"
        return _result("blocked", detail, [_ref(r) for r in blocking], ok, total)
    requested = [r for r in counted if r["state"] == REQUESTED]
    if requested:
        detail += f"; {len(requested)} awaiting approval"
        return _result("pending", detail, [_ref(r) for r in requested], ok, total)
    other = [r for r in counted if r["state"] not in _GOOD]
    if other:
        detail += f"; {len(other)} not in force"
        return _result("pending", detail, [_ref(r) for r in other], ok, total)
    return _result("ok", detail, ok=ok, total=total)


class PermitsPlanned:
    """The permits the IWP needs are requested, approved and in force."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({PERMIT})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP as of ``today`` (a date; Lapsed is decided at its UTC start)."""
        try:
            return _answer(conn, iwp, today)
        except Exception:  # noqa: BLE001  (a bad read answers unknown; the check never raises)
            return _result("unknown", UNKNOWN)


def permits_planned() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return PermitsPlanned()
