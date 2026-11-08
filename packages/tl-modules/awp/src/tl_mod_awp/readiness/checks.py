"""The readiness check ``constraints_cleared`` (ADR-0024 decision 5; P2-I2 S4).

Counts the open blocking constraints of phase ``ready`` on the IWP by a plain read of
``cur_core_constraint`` joined to ``cur_core_record`` (open: status not Cleared or Withdrawn,
NULL is Open). It never reads a description or an owner; the detail is fixed words and a count.
Found through the entry point ``throughline.readiness_checks``.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Connection, text
from tl_core.readiness.types import MAX_RESOLVE_VIA, CheckResult, IwpFacts, RecordRef

from tl_mod_awp.names import CONSTRAINT_TABLE, CONSTRAINT_TYPE

NAME = "constraints_cleared"
VERSION = "1"
PHASE = "ready"
UNKNOWN = "the constraints of this work package could not be read"
_ROWS = text(
    "SELECT c.id, r.key, r.status FROM "
    f"{CONSTRAINT_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.subject_id = :iwp AND c.phase = :phase AND c.severity = :severity "
    "AND r.voided = :no ORDER BY c.id"
)
_CLOSED = frozenset({"Cleared", "Withdrawn"})


class ConstraintsCleared:
    name = NAME
    version = VERSION
    watches: frozenset[str] = frozenset({CONSTRAINT_TYPE})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        try:
            rows = conn.execute(
                _ROWS, {"iwp": iwp.record_id, "phase": PHASE, "severity": "blocking", "no": False}
            ).all()
        except Exception:  # noqa: BLE001 - a failed read is "unknown", never an error
            return CheckResult(name=NAME, version=VERSION, state="unknown", detail=UNKNOWN)
        total = len(rows)
        opened = [r for r in rows if r.status not in _CLOSED]
        if not opened:
            return CheckResult(
                name=NAME,
                version=VERSION,
                state="ok",
                detail=f"0 open blocking constraints of {total}",
                count_ok=total,
                count_total=total,
            )
        # ids only in the keys: a key could name what a hidden record is (ADR-0028)
        refs = [
            RecordRef(record_id=str(r.id), record_type=CONSTRAINT_TYPE, key=str(r.id))
            for r in opened[:MAX_RESOLVE_VIA]
        ]
        return CheckResult(
            name=NAME,
            version=VERSION,
            state="blocked",
            detail=f"{len(opened)} open blocking constraints",
            resolve_via=refs,
            count_ok=total - len(opened),
            count_total=total,
        )


def constraints_cleared() -> ConstraintsCleared:
    return ConstraintsCleared()
