"""The readiness check ``rfis_answered`` (P2-I2-T06a2; brief M3 "Readiness check").

Found through the entry point ``throughline.readiness_checks`` (see ``pyproject.toml``). The entry
point's callable takes no argument and returns the check. For one IWP the check answers whether
every RFI the IWP references has an answer: Answered, Accepted and Closed are answered; Issued and
Awaiting response are open (pending); Draft, Internal review and Rejected are not asked or sent
back (blocked).

It is read-only and reads without a viewer on purpose (a job runs it): its detail and its
``resolve_via`` carry keys and counts only. It runs one statement, a join of the active
``references`` links of the IWP with the item rows and the Technical rows. It never raises for a bad
record: a failed read or an unknown workflow state is ``unknown`` with a fixed detail.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Connection, text
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState

from tl_mod_correspondence.names import (
    CORRESPONDENCE_TABLE,
    ST_ACCEPTED,
    ST_ANSWERED,
    ST_AWAITING_RESPONSE,
    ST_CLOSED,
    ST_DRAFT,
    ST_INTERNAL_REVIEW,
    ST_ISSUED,
    ST_REJECTED,
    ST_VOID,
    TECHNICAL,
    TECHNICAL_TABLE,
)

NAME = "rfis_answered"
VERSION = "1"
NO_RFIS = "no RFIs linked to this work package"
UNKNOWN = "the RFIs of this work package could not be read"

_ANSWERED = frozenset({ST_ANSWERED, ST_ACCEPTED, ST_CLOSED})
_OPEN = frozenset({ST_ISSUED, ST_AWAITING_RESPONSE})
_NOT_ANSWERED = frozenset({ST_DRAFT, ST_INTERNAL_REVIEW, ST_REJECTED})

#: The RFIs an IWP references: one statement for the links and the rows. The subtype lives on the
#: item row; a NULL workflow state is Draft; voided records and state Void are left out.
_RFIS = text(
    "SELECT r.id, r.key, r.status "
    "FROM cur_links l "
    f"JOIN {CORRESPONDENCE_TABLE} c ON c.id = l.to_id "
    f"JOIN {TECHNICAL_TABLE} t ON t.id = l.to_id "
    "JOIN cur_core_record r ON r.id = l.to_id "
    "WHERE l.from_id = :iwp AND l.relation = 'references' AND l.status = 'active' "
    "AND c.subtype = 'rfi' AND r.type = :tech AND r.voided = :no "
    f"AND COALESCE(r.status, '{ST_DRAFT}') <> '{ST_VOID}' "
    "ORDER BY r.key, r.id"
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
    rows = conn.execute(_RFIS, {"iwp": iwp.record_id, "tech": TECHNICAL, "no": False}).all()
    rfis: dict[str, tuple[str, str]] = {}
    for row in rows:
        rfis.setdefault(str(row.id), (str(row.key or ""), str(row.status or ST_DRAFT)))
    if not rfis:
        return _result("ok", NO_RFIS)

    blocked: list[RecordRef] = []
    pending: list[RecordRef] = []
    answered = 0
    for record_id, (key, status) in rfis.items():
        ref = RecordRef(record_id=record_id, record_type=TECHNICAL, key=key)
        if status in _ANSWERED:
            answered += 1
        elif status in _OPEN:
            pending.append(ref)
        elif status in _NOT_ANSWERED:
            blocked.append(ref)
        else:
            raise ValueError("an RFI is in a workflow state this check does not know")

    total = len(rfis)
    if blocked:
        state: CheckState = "blocked"
    elif pending:
        state = "pending"
    else:
        state = "ok"
    resolve = (blocked + pending)[:MAX_RESOLVE_VIA]
    return _result(
        state,
        f"{answered}/{total} RFIs answered",
        resolve,
        answered,
        total,
    )


class RfisAnswered:
    """Every RFI linked from an IWP has an answer."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({TECHNICAL})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP. ``today`` is not used: the check reads the workflow states."""
        del today
        try:
            return _answer(conn, iwp)
        except Exception:  # noqa: BLE001  (a bad record answers unknown; the check never raises)
            return _result("unknown", UNKNOWN)


def rfis_answered() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return RfisAnswered()
