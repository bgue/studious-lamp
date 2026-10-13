"""Base reports of document control (brief 15; P1-I2-T11): the register, a document's history,
overdue reviews, the transmittal log and the stale pinned revisions.

Every function takes a connection (``uow.conn()`` inside a unit of work, a read transaction
elsewhere) and a project scope, reads the flat views (``v_documents_<class>``) and the review and
transmittal tables, and returns frozen lines in a stable order. Nothing here writes. A void record
is left out. Dates are ISO text (``YYYY-MM-DD``); "today" is a parameter (``on``) so a report is
repeatable.

STUB (P1-I2-T11a): the bodies of the five report functions raise NotImplementedError; the line
dataclasses and every signature are final. Each body has a STEPS comment. Implement them, then
delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Connection, text

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
    """A link pinned to a revision that a newer issue has replaced (or flagged stale)."""

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
    # STEPS
    # 1. Build one SELECT over the view v_documents_document (DOCUMENT_VIEW, alias d) with the
    #    columns key, title, doc_type, discipline, status, current_revision_code,
    #    current_revision_status, current_revision_class, current_revision_issued_on and three
    #    scalar subqueries: `revisions` = COUNT of the document's rows in REVISION_VIEW (alias
    #    r, r.document_id = d.id) whose COALESCE(r.status, 'Draft') <> 'Void'; `open_code` =
    #    MAX(r.code) over its revisions whose COALESCE(r.status, 'Draft') IN ('Draft', 'In
    #    Review'); `stale_links` = COUNT of rows of cur_links l with l.to_id = d.id AND l.status
    #    = 'stale'.
    # 2. WHERE d.scope = :scope AND COALESCE(d.status, 'Draft') <> 'Void'; add `AND d.doc_type =
    #    :doc_type`, `AND d.discipline = :discipline`, `AND COALESCE(d.status, 'Draft') =
    #    :state` only for the arguments that are not None. ORDER BY d.key LIMIT :limit. Run it
    #    with conn.execute(text(sql), params).
    # 3. One RegisterLine per row: number = row.key, state = row.status or "Draft", the revision
    #    counts as int(...), the rest as read.
    raise NotImplementedError


def revision_history(conn: Connection, scope: str, number: str) -> list[HistoryLine]:
    """Every revision of a document, oldest first, with its renditions, transmittals and review.

    Raises ``DocumentNotFoundError``. Void revisions are kept in the history and shown as Void.
    """
    # STEPS
    # 1. doc = registry.find_document(conn, scope, number); None: raise
    #    DocumentNotFoundError(f"no document {number!r} in scope {scope!r}").
    # 2. revisions = registry.revisions_of(conn, doc.id) (void ones included, oldest first);
    #    codes = {r.id: r.code for r in revisions}.
    # 3. For each revision: closed = [c for c in registry.review_cycles_of(conn, rev.id) if
    #    c.state == "closed"]; one HistoryLine with state = "Void" if rev.voided else rev.state;
    #    renditions = len(registry.renditions_of(conn, rev.id, current_only=True)); transmittals
    #    = [t.number for t in registry.transmittals_of_revision(conn, rev.id)]; review_outcome =
    #    closed[-1].outcome if closed else None; superseded_by = codes.get(rev.superseded_by) if
    #    rev.superseded_by else None; the other fields come straight from the row (code,
    #    ordinal, issue_status, status_class, issued_on, is_current, purpose, change_note).
    raise NotImplementedError


def overdue_reviews(conn: Connection, scope: str, *, on: date | None = None) -> list[OverdueLine]:
    """Reviewers of open review cycles who have not answered and whose due date has passed.

    A reviewer with no date of their own is due on the cycle's date; one with no date at all is
    never overdue. The reviewers of a void or superseded document are left out: nobody is waiting
    for them. Ordered by due date, then cycle key, then reviewer.
    """
    # STEPS
    # 1. day = (on or date.today()).isoformat().
    # 2. SELECT c.key AS cycle_key, r.reviewer, r.due_date, rv.document_number, rv.code FROM
    #    REVIEWER_TABLE r JOIN REVIEW_CYCLE_VIEW c ON c.id = r.review_cycle_id JOIN
    #    REVISION_VIEW rv ON rv.id = r.revision_id JOIN DOCUMENT_VIEW d ON d.id = r.document_id
    #    WHERE r.scope = :scope AND c.state = 'open' AND r.outcome IS NULL AND r.due_date IS NOT
    #    NULL AND r.due_date < :day AND NOT c.voided AND NOT d.voided AND COALESCE(d.status,
    #    'Draft') NOT IN ('Void', 'Superseded') ORDER BY r.due_date, c.key, r.reviewer.
    # 3. One OverdueLine per row; days_overdue = (date.fromisoformat(day) -
    #    date.fromisoformat(row.due_date)).days.
    raise NotImplementedError


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
    # STEPS
    # 1. day = (on or date.today()).isoformat().
    # 2. SELECT t.key, t.title, t.direction, t.purpose, t.status, t.issued_on, t.due_date,
    #    t.response_code, t.responded_on and `items` = (SELECT COUNT(*) FROM
    #    TRANSMITTAL_ITEM_TABLE i WHERE i.transmittal_id = t.id) FROM TRANSMITTAL_VIEW t WHERE
    #    t.scope = :scope. With `state` add AND COALESCE(t.status, 'Draft') = :state; without it
    #    AND COALESCE(t.status, 'Draft') <> 'Void'. With `direction` add AND t.direction =
    #    :direction. ORDER BY t.key.
    # 3. One TransmittalLine per row: state = row.status or "Draft"; overdue is True exactly
    #    when that state is "Issued" and row.due_date is not None and row.due_date < day.
    raise NotImplementedError


def stale_pins(conn: Connection, scope: str) -> list[StalePinLine]:
    """Links pinned to a revision that has been replaced, or flagged stale, by document and record.

    Ordered by document number, then the key of the record that links.
    """
    # STEPS
    # 1. For each link in links_to_documents(conn, scope, only_stale=True) (from
    #    tl_mod_documents.resolver) read current = registry.get_document(conn,
    #    link.document_id).
    # 2. One StalePinLine per link: document_number, document_title, pinned_code = link.pin,
    #    current_code = link.resolution.current_code, current_status = the document's
    #    current_revision_status (None when current is None), linked_key = link.from_key,
    #    linked_type = link.from_type, link_id, link_status = link.link_status, newer_codes =
    #    list(link.resolution.newer_codes). Keep the order the function returns.
    raise NotImplementedError
