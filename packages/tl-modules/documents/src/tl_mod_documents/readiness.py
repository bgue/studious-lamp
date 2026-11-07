"""The readiness check ``documents_current`` (P2-I2-T06a1; brief M3 "Readiness check").

Found through the entry point ``throughline.readiness_checks``; the entry point's callable takes no
argument and returns the check. For one IWP the check answers whether every document the IWP pins
is at a current revision: ``current`` and ``floating`` pins are current, ``stale`` pins are behind,
and ``unknown`` or ``no_current`` pins (and a pin the resolver does not return) are not answerable.

It is read-only and reads without a viewer on purpose (a job runs it): its detail and its
``resolve_via`` carry keys and counts only, never titles. It issues no statement of its own; the
pins are resolved by ``links_to_documents``. A failed read is ``unknown`` with a fixed detail.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Connection
from tl_core.readiness import MAX_RESOLVE_VIA, CheckResult, IwpFacts, ReadinessCheck, RecordRef
from tl_core.readiness.types import CheckState

from tl_mod_documents.names import DOCUMENT
from tl_mod_documents.resolver import PinnedLink, links_to_documents

NAME = "documents_current"
VERSION = "1"
REVISION = "documents.Revision"
NO_PINS = "no documents pinned to this work package"
UNKNOWN = "the pinned documents of this work package could not be read"
SCOPE_LIMIT = 1000
CURRENT_STATES = frozenset({"current", "floating"})


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


def _answer(conn: Connection, iwp: IwpFacts) -> CheckResult:
    pinned = list(iwp.pinned_document_links)
    if not pinned:
        return _result("n_a", NO_PINS)
    wanted = set(pinned)
    found = [
        link
        for link in links_to_documents(conn, iwp.scope, limit=SCOPE_LIMIT)
        if link.link_id in wanted
    ]
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
