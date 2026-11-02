"""The readiness check ``materials_reserved`` (P2-I3-T03; brief M4 readiness, M3 "Readiness check").

Found through the entry point ``throughline.readiness_checks``; the entry point's callable takes no
argument and returns the check. For one IWP the check answers whether the material take-off lines
of the IWP are covered by reservations and issues (``reserved_qty + issued_qty >= qty``).

It is read-only and reads without a viewer on purpose (a job runs it): its detail and its
``resolve_via`` carry keys and counts only. It never raises for a bad record; a failed read is
``unknown`` with a fixed detail. It runs at most three statements: the lines, the open receipts of
their items, and the PO lines of their items promised on or before ``planned_start``.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Connection, text
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState

from tl_mod_materials.common import dec
from tl_mod_materials.names import (
    MTO_LINE,
    MTO_LINE_TABLE,
    PO_LINE_TABLE,
    RECEIPT,
    RECEIPT_LINE_TABLE,
    RECEIPT_TABLE,
    STOCK_LOT,
)

NAME = "materials_reserved"
VERSION = "1"
NO_LINES = "no material take-off lines on this work package"
UNKNOWN = "the material take-off lines of this work package could not be read"

_LINES = text(
    "SELECT l.id, l.project_item_id, l.qty, l.reserved_qty, l.issued_qty, lr.key "
    f"FROM {MTO_LINE_TABLE} l JOIN cur_core_record lr ON lr.id = l.id "
    "WHERE l.work_package_id = :wp AND lr.voided = :no ORDER BY lr.key"
)
#: Receipts not yet decided (state Received: status NULL; or Inspected) holding one of the items.
_OPEN_RECEIPTS = text(
    "SELECT x.project_item_id, t.id AS receipt_id, r.key "
    f"FROM {RECEIPT_LINE_TABLE} x JOIN {RECEIPT_TABLE} t ON t.id = x.receipt_id "
    "JOIN cur_core_record r ON r.id = t.id "
    "WHERE r.voided = :no AND (r.status IS NULL OR r.status IN ('Received', 'Inspected')) "
    f"AND x.project_item_id IN (SELECT l.project_item_id FROM {MTO_LINE_TABLE} l "
    "WHERE l.work_package_id = :wp) ORDER BY r.key"
)
#: PO lines of one of the items promised on or before the IWP's planned start (ISO dates).
_PROMISED = text(
    f"SELECT p.project_item_id FROM {PO_LINE_TABLE} p JOIN cur_core_record pr ON pr.id = p.id "
    "WHERE pr.voided = :no AND p.promised_date IS NOT NULL AND p.promised_date <= :planned "
    f"AND p.project_item_id IN (SELECT l.project_item_id FROM {MTO_LINE_TABLE} l "
    "WHERE l.work_package_id = :wp)"
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


def _answer(conn: Connection, iwp: IwpFacts) -> CheckResult:
    lines = conn.execute(_LINES, {"wp": iwp.record_id, "no": False}).all()
    if not lines:
        return _result("n_a", NO_LINES)
    total = len(lines)
    short = [r for r in lines if dec(r.reserved_qty) + dec(r.issued_qty) < dec(r.qty)]
    covered = total - len(short)
    if not short:
        return _result(
            "ok",
            f"{covered}/{total} material take-off lines covered by reservations and issues",
            ok=covered,
            total=total,
        )

    short_items = {str(r.project_item_id) for r in short}
    open_by_item: dict[str, dict[str, RecordRef]] = {}
    for found in conn.execute(_OPEN_RECEIPTS, {"wp": iwp.record_id, "no": False}):
        ref = RecordRef(record_id=str(found.receipt_id), record_type=RECEIPT, key=str(found.key))
        open_by_item.setdefault(str(found.project_item_id), {}).setdefault(ref.record_id, ref)
    promised: set[str] = set()
    if iwp.planned_start is not None:
        planned: date = iwp.planned_start
        promised = {
            str(found.project_item_id)
            for found in conn.execute(
                _PROMISED,
                {"wp": iwp.record_id, "no": False, "planned": planned.isoformat()},
            )
        }

    uncovered = [
        r
        for r in short
        if str(r.project_item_id) not in open_by_item and str(r.project_item_id) not in promised
    ]
    short_refs = [
        RecordRef(record_id=str(r.id), record_type=MTO_LINE, key=str(r.key)) for r in short
    ]
    receipts: dict[str, RecordRef] = {}
    for item in short_items:
        for ref in open_by_item.get(item, {}).values():
            receipts.setdefault(ref.record_id, ref)
    receipt_refs = sorted(receipts.values(), key=lambda ref: ref.key)
    resolve = (short_refs + receipt_refs)[:MAX_RESOLVE_VIA]

    if uncovered:
        return _result(
            "blocked",
            f"{covered}/{total} material take-off lines covered; {len(uncovered)} short with no "
            "open receipt and no PO line due by planned start",
            resolve,
            covered,
            total,
        )
    return _result(
        "pending",
        f"{covered}/{total} material take-off lines covered; {len(short)} short, each with an "
        "open receipt or a PO line due by planned start",
        resolve,
        covered,
        total,
    )


class MaterialsReserved:
    """The material take-off lines of an IWP are covered by reservations and issues."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({STOCK_LOT, MTO_LINE, RECEIPT})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP. ``today`` is not used: the check compares ``planned_start``."""
        del today
        try:
            return _answer(conn, iwp)
        except Exception:  # noqa: BLE001  (a bad record answers unknown; the check never raises)
            return _result("unknown", UNKNOWN)


def materials_reserved() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return MaterialsReserved()
