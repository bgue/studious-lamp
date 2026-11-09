"""The shortages source of the Checks read: take-off lines short of reservations and issues."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Connection
from tl_core.confidentiality import Viewer
from tl_core.insights.types import CheckFinding, RecordFacts
from tl_core.readiness.types import RecordRef

from tl_mod_materials.names import MTO_LINE
from tl_mod_materials.views import mto_lines


def _plain(qty: Decimal) -> str:
    """``6.000`` as ``6`` and ``2.50`` as ``2.5``; never an exponent."""
    shown = f"{qty:f}"
    return shown.rstrip("0").rstrip(".") if "." in shown else shown


def findings(conn: Connection, facts: RecordFacts, viewer: Viewer | None) -> list[CheckFinding]:
    """Each short line that is the record, or that names the record as its work package."""
    out: list[CheckFinding] = []
    for line in mto_lines(conn, facts.scope, short_only=True, viewer=viewer):
        if line.id != facts.record_id and line.work_package_id != facts.record_id:
            continue
        out.append(
            CheckFinding(
                source="shortages",
                subject_id=facts.record_id,
                state="short",
                text=f"short {_plain(line.short)} {line.uom}",
                since=line.need_by,
                severity="warning",
                resolve_via=[RecordRef(record_id=line.id, record_type=MTO_LINE, key=line.key)],
            )
        )
    return out
