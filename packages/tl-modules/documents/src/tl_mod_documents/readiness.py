"""The readiness check ``documents_current`` (P2-I2-T06a1; brief M3 "Readiness check").

Found through the entry point ``throughline.readiness_checks``; the entry point's callable takes no
argument and returns the check. For one IWP the check answers whether every document the IWP pins
is at a current revision: ``current`` and ``floating`` pins are current, ``stale`` pins are behind,
and ``unknown`` or ``no_current`` pins (and a pin the resolver does not return) are not answerable.

The pins are read here, not from ``IwpFacts.pinned_document_links`` (that list drops stale and
floating links): every ``references`` link of the IWP with status ``active`` or ``stale`` that
points at a document or at a missing record. One SQL statement reads them; the links are then
resolved by ``links_to_documents`` for exactly those link ids (the default viewer). A pin the
viewer may not read is not in the resolver's result, so it answers like a missing document:
counted, not current.

It is read-only and reads without a viewer on purpose (a job runs it): its detail and its
``resolve_via`` carry keys and counts only, never titles. A failed read is ``unknown`` with a fixed
detail.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Connection, text
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState

from tl_mod_documents.names import DOCUMENT, PIN_RELATION
from tl_mod_documents.resolver import PinnedLink, links_to_documents

NAME = "documents_current"
VERSION = "1"
REVISION = "documents.Revision"
NO_PINS = "no documents pinned to this work package"
UNKNOWN = "the pinned documents of this work package could not be read"
CURRENT_STATES = frozenset({"current", "floating"})
#: The IWP's pins: every reference link of the IWP that is active or stale. The target is a document
#: or a missing record (the LEFT JOIN keeps a missing one; the resolver then answers it as unknown).
_PIN_LINKS_SQL = text(
    "SELECT l.link_id FROM cur_links l LEFT JOIN cur_core_record d ON d.id = l.to_id "
    "WHERE l.from_id = :iwp AND l.scope = :scope AND l.relation = :relation "
    "AND l.status IN ('active', 'stale') AND (d.id IS NULL OR d.type = :document_type) "
    "ORDER BY l.link_id"
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


def _resolve_via(stale: list[PinnedLink], others: list[PinnedLink]) -> list[RecordRef]:
    """The stale documents first, then the others; one record per document; at most the bound."""
    refs: dict[str, RecordRef] = {}
    for found in [*stale, *others]:
        refs.setdefault(
            found.document_id,
            RecordRef(record_id=found.document_id, record_type=DOCUMENT, key=found.document_number),
        )
    return list(refs.values())[:MAX_RESOLVE_VIA]


def _pin_ids(conn: Connection, iwp: IwpFacts) -> list[str]:
    """The link ids of the IWP's pins (one statement)."""
    params = {
        "iwp": iwp.record_id,
        "scope": iwp.scope,
        "relation": PIN_RELATION,
        "document_type": DOCUMENT,
    }
    return [str(row[0]) for row in conn.execute(_PIN_LINKS_SQL, params).all()]


def _answer(conn: Connection, iwp: IwpFacts) -> CheckResult:
    pinned = _pin_ids(conn, iwp)
    if not pinned:
        return _result("n_a", NO_PINS)
    found = links_to_documents(conn, iwp.scope, link_ids=pinned, limit=len(pinned))
    total = len(pinned)
    current = sum(1 for link in found if link.resolution.state in CURRENT_STATES)
    if current == total:
        return _result("ok", f"{current}/{total} pinned drawings current", ok=current, total=total)

    stale = [link for link in found if link.resolution.state == "stale"]
    others = [
        link
        for link in found
        if link.resolution.state not in CURRENT_STATES and link.resolution.state != "stale"
    ]
    detail = f"{current}/{total} pinned drawings current"
    if stale:
        detail += f"; {len(stale)} behind"
    return _result(
        "blocked",
        detail,
        _resolve_via(stale, others),
        current,
        total,
    )


class DocumentsCurrent:
    """Every document pinned by the IWP is at a current revision."""

    name: str = NAME
    version: str = VERSION
    watches: frozenset[str] = frozenset({DOCUMENT, REVISION})

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        """Answer for one IWP. ``today`` is not used: the pins name revisions, not dates."""
        del today
        try:
            return _answer(conn, iwp)
        except Exception:  # noqa: BLE001  (a bad record answers unknown; the check never raises)
            return _result("unknown", UNKNOWN)


def documents_current() -> ReadinessCheck:
    """The entry point of ``throughline.readiness_checks``: a zero-argument callable."""
    return DocumentsCurrent()
