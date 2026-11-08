"""The Checks read: what needs attention on one record, over five existing sources (ADR-0028).

Each source is a function ``(conn, facts, viewer) -> list[CheckFinding]`` (``findings`` in a module
package; ``constraint_findings`` and ``expected_link_findings`` here, which need only core tables).
``record_checks`` runs the list it is given, in order, and never fails because one source did. The
read writes nothing: it opens a savepoint per source (so a failed statement cannot poison the
caller's transaction) and issues only SELECTs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from sqlalchemy import Connection, text

from tl_core import confidentiality
from tl_core.confidentiality import Viewer
from tl_core.constraints.guard import OPEN_STATES
from tl_core.constraints.queries import list_constraints
from tl_core.insights.types import CheckFinding, RecordFacts
from tl_core.links.expected import missing_expected_links
from tl_core.readiness.types import RecordRef
from tl_core.uow import UnitOfWork

log = logging.getLogger(__name__)

CheckSource = Callable[[Connection, RecordFacts, Viewer | None], list[CheckFinding]]

#: The order findings are listed in, by source. A source not named sorts after these.
SOURCE_ORDER = ("readiness", "constraints", "expected_links", "clocks", "shortages")
MAX_FINDINGS = 200
MAX_PER_SOURCE = 50
TEXT_DESCRIPTION_CHARS = 120

_RECORD_SQL = text("SELECT id, type, key, scope FROM cur_core_record WHERE id = :id")


def record_facts(
    conn: Connection, record_id: str, viewer: Viewer | None = None
) -> RecordFacts | None:
    """The facts of a record the viewer may read; ``None`` when it is unknown or hidden (alike)."""
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or confidentiality.is_hidden(conn, record_id, viewer):
        return None
    return RecordFacts(
        record_id=str(row.id),
        record_type=str(row.type),
        key=str(row.key or ""),
        scope=str(row.scope),
    )


def _rank(source: str) -> int:
    return SOURCE_ORDER.index(source) if source in SOURCE_ORDER else len(SOURCE_ORDER)


def _sort_key(finding: CheckFinding) -> tuple[int, int, int, str]:
    return (
        _rank(finding.source),
        0 if finding.severity == "blocking" else 1,
        0 if finding.since is not None else 1,
        finding.since or "",
    )


def _run(
    conn: Connection, source: CheckSource, record: RecordFacts, viewer: Viewer | None
) -> list[CheckFinding]:
    """One source, or nothing when it raises. The savepoint keeps Postgres usable afterwards."""
    try:
        with conn.begin_nested():
            return list(source(conn, record, viewer))
    except Exception:
        log.warning("insight check source failed", extra={"code": "insight_source_failed"})
        return []


def record_checks(
    conn: Connection,
    record: RecordFacts,
    sources: Sequence[CheckSource],
    viewer: Viewer | None = None,
) -> list[CheckFinding]:
    """Every finding of every source for ``record``, ordered by source, blocking first, then by
    ``since`` (oldest first); at most 50 per source and 200 in all. Writes nothing."""
    found: list[CheckFinding] = []
    reader = viewer if viewer is not None else confidentiality.current_viewer()
    with confidentiality.use_viewer(reader):
        for source in sources:
            found.extend(sorted(_run(conn, source, record, reader), key=_sort_key)[:MAX_PER_SOURCE])
    found.sort(key=_sort_key)  # stable: the order within one source and rank is kept
    return found[:MAX_FINDINGS]


def constraint_findings(
    conn: Connection, facts: RecordFacts, viewer: Viewer | None
) -> list[CheckFinding]:
    """Open constraints raised on the record (``list_constraints``, which filters by viewer)."""
    out: list[CheckFinding] = []
    for state in OPEN_STATES:
        for c in list_constraints(
            conn, facts.scope, subject_id=facts.record_id, state=state, viewer=viewer
        ):
            description = (c.description or "").strip()
            if len(description) > TEXT_DESCRIPTION_CHARS:
                description = description[:TEXT_DESCRIPTION_CHARS]
            line = f"{c.category} {c.key}, open {c.age_days} days"
            out.append(
                CheckFinding(
                    source="constraints",
                    subject_id=facts.record_id,
                    state="open",
                    text=f"{line}: {description}" if description else line,
                    since=c.effective_at or c.raised_on,
                    severity="blocking" if c.severity == "blocking" else "warning",
                    resolve_via=[
                        RecordRef(record_id=c.id, record_type="core.Constraint", key=c.key)
                    ],
                )
            )
    return out


@dataclass
class _ConnUow:
    """Just enough of a unit of work for ``missing_expected_links``, which only reads."""

    connection: Connection

    def conn(self) -> Connection:
        return self.connection


def expected_link_findings(
    conn: Connection, facts: RecordFacts, viewer: Viewer | None
) -> list[CheckFinding]:
    """Links the record's type expects and it does not have yet."""
    out: list[CheckFinding] = []
    for m in missing_expected_links(cast(UnitOfWork, _ConnUow(conn)), facts.record_id):
        label = m.expectation.label or m.expectation.relation
        out.append(
            CheckFinding(
                source="expected_links",
                subject_id=facts.record_id,
                state="missing",
                text=f"missing link: {label} ({m.found} of {m.needed})",
                severity="warning",
            )
        )
    return out
