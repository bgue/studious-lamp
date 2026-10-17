"""Base reports of document control (brief 15; P1-I2-T11): the register, a document's history,
overdue reviews, the transmittal log and the stale pinned revisions.

Every function takes a connection (``uow.conn()`` inside a unit of work, a read transaction
elsewhere) and a project scope, reads the flat views (``v_documents_<class>``) and the review and
transmittal tables, and returns frozen lines in a stable order. Nothing here writes. A void record
is left out. Dates are ISO text (``YYYY-MM-DD``); "today" is a parameter (``on``) so a report is
repeatable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_documents import registry
from tl_mod_documents.errors import DocumentNotFoundError
from tl_mod_documents.names import (
    DOCUMENT_VIEW,
    REVIEW_CYCLE_VIEW,
    REVIEWER_TABLE,
    REVISION_VIEW,
    TRANSMITTAL_ITEM_TABLE,
    TRANSMITTAL_VIEW,
)
from tl_mod_documents.resolver import links_to_documents


@dataclass(frozen=True)
class RegisterLine:
    """One document in the register."""

    number: str
    title: str
    doc_type: str | None
    discipline: str | None
    state: str
    current_code: str | None
    current_status: str | None
    current_class: str | None
    current_issued_on: str | None
    revisions: int  # revisions that are not void
    open_code: str | None  # the revision being prepared or reviewed
    stale_links: int  # links to the document whose status is stale


@dataclass(frozen=True)
class HistoryLine:
    """One revision in a document's history."""

    code: str
    ordinal: int
    state: str
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    purpose: str | None
    change_note: str | None
    renditions: int  # current renditions
    transmittals: list[str]  # numbers of the transmittals that carry it
    review_outcome: str | None  # outcome of the latest closed review cycle
    superseded_by: str | None  # the code of the revision that replaced it


@dataclass(frozen=True)
class OverdueLine:
    """A reviewer who should have answered by now."""

    document_number: str
    revision_code: str
    cycle_key: str
    reviewer: str
    due_date: str
    days_overdue: int


@dataclass(frozen=True)
class TransmittalLine:
    """One transmittal in the log."""

    number: str
    title: str
    direction: str
    purpose: str
    state: str
    issued_on: str | None
    due_date: str | None
    response_code: str | None
    responded_on: str | None
    items: int
    overdue: bool  # issued, not answered, and the due date has passed


@dataclass(frozen=True)
class StalePinLine:
    """A link pinned to a revision that a later revision has replaced (or flagged stale).

    A later revision replaces a pin when it was issued in the pinned revision's status class or a
    later one (ADR-0012); ``newer_codes`` are the revisions that did.
    """

    document_number: str
    document_title: str
    pinned_code: str | None
    current_code: str | None
    current_status: str | None
    linked_key: str | None
    linked_type: str
    link_id: str
    link_status: str
    newer_codes: list[str]


def document_register(
    conn: Connection,
    scope: str,
    *,
    doc_type: str | None = None,
    discipline: str | None = None,
    state: str | None = None,
    limit: int = 1000,
) -> list[RegisterLine]:
    """The documents of a project by number, with the facts a register shows.

    ``state`` is a document state (Registered, In Review, Issued, Superseded). A void document is
    left out.
    """
    where = ["d.scope = :scope", "COALESCE(d.status, 'Draft') <> 'Void'"]
    params: dict[str, Any] = {"scope": scope, "limit": limit}
    visible, visible_params = confidentiality.not_hidden("d.id")
    where.append(visible)
    params.update(visible_params)
    if doc_type is not None:
        where.append("d.doc_type = :doc_type")
        params["doc_type"] = doc_type
    if discipline is not None:
        where.append("d.discipline = :discipline")
        params["discipline"] = discipline
    if state is not None:
        where.append("COALESCE(d.status, 'Draft') = :state")
        params["state"] = state
    sql = (
        "SELECT d.key AS key, d.title AS title, d.doc_type AS doc_type, "
        "d.discipline AS discipline, d.status AS status, "
        "d.current_revision_code AS current_revision_code, "
        "d.current_revision_status AS current_revision_status, "
        "d.current_revision_class AS current_revision_class, "
        "d.current_revision_issued_on AS current_revision_issued_on, "
        f"(SELECT COUNT(*) FROM {REVISION_VIEW} r WHERE r.document_id = d.id "
        "AND COALESCE(r.status, 'Draft') <> 'Void') AS revisions, "
        f"(SELECT MAX(r.code) FROM {REVISION_VIEW} r WHERE r.document_id = d.id "
        "AND COALESCE(r.status, 'Draft') IN ('Draft', 'In Review')) AS open_code, "
        "(SELECT COUNT(*) FROM cur_links l WHERE l.to_id = d.id AND l.status = 'stale') "
        "AS stale_links "
        f"FROM {DOCUMENT_VIEW} d WHERE {' AND '.join(where)} ORDER BY d.key LIMIT :limit"
    )
    return [
        RegisterLine(
            number=row.key,
            title=row.title,
            doc_type=row.doc_type,
            discipline=row.discipline,
            state=row.status or "Draft",
            current_code=row.current_revision_code,
            current_status=row.current_revision_status,
            current_class=row.current_revision_class,
            current_issued_on=row.current_revision_issued_on,
            revisions=int(row.revisions),
            open_code=row.open_code,
            stale_links=int(row.stale_links),
        )
        for row in conn.execute(text(sql), params).all()
    ]


def revision_history(conn: Connection, scope: str, number: str) -> list[HistoryLine]:
    """Every revision of a document, oldest first, with its renditions, transmittals and review.

    Raises ``DocumentNotFoundError``. Void revisions are kept in the history and shown as Void.
    """
    doc = registry.find_document(conn, scope, number)
    if doc is None:
        raise DocumentNotFoundError(f"no document {number!r} in scope {scope!r}")
    revisions = registry.revisions_of(conn, doc.id)
    codes = {r.id: r.code for r in revisions}
    lines: list[HistoryLine] = []
    for rev in revisions:
        closed = [c for c in registry.review_cycles_of(conn, rev.id) if c.state == "closed"]
        lines.append(
            HistoryLine(
                code=rev.code,
                ordinal=rev.ordinal,
                state="Void" if rev.voided else rev.state,
                issue_status=rev.issue_status,
                status_class=rev.status_class,
                issued_on=rev.issued_on,
                is_current=rev.is_current,
                purpose=rev.purpose,
                change_note=rev.change_note,
                renditions=len(registry.renditions_of(conn, rev.id, current_only=True)),
                transmittals=[t.number for t in registry.transmittals_of_revision(conn, rev.id)],
                review_outcome=closed[-1].outcome if closed else None,
                superseded_by=codes.get(rev.superseded_by) if rev.superseded_by else None,
            )
        )
    return lines


def overdue_reviews(conn: Connection, scope: str, *, on: date | None = None) -> list[OverdueLine]:
    """Reviewers of open review cycles who have not answered and whose due date has passed.

    A reviewer with no date of their own is due on the cycle's date; one with no date at all is
    never overdue. The reviewers of a void or superseded document are left out: nobody is waiting
    for them. Ordered by due date, then cycle key, then reviewer.
    """
    day = (on or date.today()).isoformat()
    sql = (
        "SELECT c.key AS cycle_key, r.reviewer AS reviewer, r.due_date AS due_date, "
        "rv.document_number AS document_number, rv.code AS code "
        f"FROM {REVIEWER_TABLE} r "
        f"JOIN {REVIEW_CYCLE_VIEW} c ON c.id = r.review_cycle_id "
        f"JOIN {REVISION_VIEW} rv ON rv.id = r.revision_id "
        f"JOIN {DOCUMENT_VIEW} d ON d.id = r.document_id "
        "WHERE r.scope = :scope AND c.state = 'open' AND r.outcome IS NULL "
        "AND r.due_date IS NOT NULL AND r.due_date < :day AND NOT c.voided AND NOT d.voided "
        "AND COALESCE(d.status, 'Draft') NOT IN ('Void', 'Superseded') "
        "ORDER BY r.due_date, c.key, r.reviewer"
    )
    today = date.fromisoformat(day)
    visible, visible_params = confidentiality.not_hidden("d.id")
    sql = sql.replace("ORDER BY r.due_date", f"AND {visible} ORDER BY r.due_date")
    return [
        OverdueLine(
            document_number=row.document_number,
            revision_code=row.code,
            cycle_key=row.cycle_key,
            reviewer=row.reviewer,
            due_date=row.due_date,
            days_overdue=(today - date.fromisoformat(row.due_date)).days,
        )
        for row in conn.execute(text(sql), {"scope": scope, "day": day, **visible_params}).all()
    ]


def transmittal_log(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    on: date | None = None,
) -> list[TransmittalLine]:
    """The transmittals of a project by number. A void one is left out unless ``state`` is Void.

    ``overdue`` is true for an issued transmittal that has no answer and whose due date has passed.
    """
    day = (on or date.today()).isoformat()
    item_visible, item_params = confidentiality.not_hidden("i.revision_id")
    sql = (
        "SELECT t.key AS key, t.title AS title, t.direction AS direction, "
        "t.purpose AS purpose, t.status AS status, t.issued_on AS issued_on, "
        "t.due_date AS due_date, t.response_code AS response_code, "
        "t.responded_on AS responded_on, "
        f"(SELECT COUNT(*) FROM {TRANSMITTAL_ITEM_TABLE} i WHERE i.transmittal_id = t.id "
        f"AND {item_visible}) AS items FROM {TRANSMITTAL_VIEW} t WHERE t.scope = :scope"
    )
    params: dict[str, Any] = {"scope": scope, **item_params}
    if state is not None:
        sql += " AND COALESCE(t.status, 'Draft') = :state"
        params["state"] = state
    else:
        sql += " AND COALESCE(t.status, 'Draft') <> 'Void'"
    if direction is not None:
        sql += " AND t.direction = :direction"
        params["direction"] = direction
    sql += " ORDER BY t.key"
    lines: list[TransmittalLine] = []
    for row in conn.execute(text(sql), params).all():
        current = row.status or "Draft"
        lines.append(
            TransmittalLine(
                number=row.key,
                title=row.title,
                direction=row.direction,
                purpose=row.purpose,
                state=current,
                issued_on=row.issued_on,
                due_date=row.due_date,
                response_code=row.response_code,
                responded_on=row.responded_on,
                items=int(row.items),
                overdue=(current == "Issued" and row.due_date is not None and row.due_date < day),
            )
        )
    return lines


def stale_pins(conn: Connection, scope: str) -> list[StalePinLine]:
    """Links pinned to a revision that has been replaced, or flagged stale, by document and record.

    Replaced means a later revision of the same status class or a later one (ADR-0012), or a
    document that was voided or superseded.

    Ordered by document number, then the key of the record that links.
    """
    lines: list[StalePinLine] = []
    for link in links_to_documents(conn, scope, only_stale=True):
        current = registry.get_document(conn, link.document_id)
        lines.append(
            StalePinLine(
                document_number=link.document_number,
                document_title=link.document_title,
                pinned_code=link.pin,
                current_code=link.resolution.current_code,
                current_status=None if current is None else current.current_revision_status,
                linked_key=link.from_key,
                linked_type=link.from_type,
                link_id=link.link_id,
                link_status=link.link_status,
                newer_codes=list(link.resolution.newer_codes),
            )
        )
    return lines
