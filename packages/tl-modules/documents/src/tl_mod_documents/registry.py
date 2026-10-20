"""Reading the documents tables: documents, revisions, renditions, transmittals and review cycles.

Every function takes a connection (``uow.conn()`` inside a unit of work, a read transaction
elsewhere) and returns frozen rows read from the module's flat views (``v_documents_<class>``,
which join the typed table to the envelope in ``cur_core_record``). Nothing here writes. JSON
columns come back as Python values on both adapters, booleans as ``bool``.

A voided record is never returned by a list unless a function says so; a ``get`` or ``find`` returns
it with ``voided`` set, so a caller can say "this was voided" instead of "not found". A record that
never moved is in its workflow's first state: ``state`` is that state, not ``None``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_documents.names import (
    DOC_DRAFT,
    DOCUMENT_VIEW,
    RENDITION_VIEW,
    REVIEW_CYCLE_VIEW,
    REVIEWER_TABLE,
    REVISION_VIEW,
    TR_DRAFT,
    TRANSMITTAL_ITEM_TABLE,
    TRANSMITTAL_VIEW,
)

#: Revision states in which the revision is still being prepared or reviewed.
OPEN_STATES = ("Draft", "In Review")


def _hidden(conn: Connection, record_id: str) -> bool:
    """True when the viewer may not read this record (ADR-0016): it then does not exist for them.

    Documents and everything that hangs on a document (revisions, renditions, reviews, derived
    documents) are covered by the documents module's confidential source.
    """
    return confidentiality.is_hidden(conn, record_id)


def _json(value: Any, default: Any) -> Any:
    """A JSON column as Python: text on SQLite and through the Postgres adapter."""
    if value is None:
        return default
    return json.loads(value) if isinstance(value, str) else value


@dataclass(frozen=True)
class DocumentRow:
    id: str
    scope: str
    number: str
    title: str
    description: str | None
    state: str  # the document workflow state
    voided: bool
    version: int
    conformance: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None
    revision_scheme: str
    pattern_code: str | None
    current_revision_id: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None
    created_at: str
    updated_at: str

    @property
    def closed(self) -> bool:
        """True once the document is void or superseded: it takes no more changes."""
        return self.voided or self.state in ("Void", "Superseded")


@dataclass(frozen=True)
class RevisionRow:
    id: str
    scope: str
    document_id: str
    document_number: str
    key: str
    title: str
    code: str
    ordinal: int
    state: str  # Draft, In Review, Issued, Superseded, Void
    voided: bool
    version: int
    previous_revision_id: str | None
    purpose: str | None
    change_note: str | None
    revision_date: str | None
    intended_status: str | None
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    superseded_by: str | None

    @property
    def issued(self) -> bool:
        return self.issued_on is not None

    @property
    def open(self) -> bool:
        return self.state in OPEN_STATES and not self.voided


@dataclass(frozen=True)
class RenditionRow:
    id: str
    scope: str
    revision_id: str
    document_id: str
    key: str
    kind: str
    file_id: str
    filename: str
    content_type: str
    size: int
    sha256: str
    page_count: int | None
    is_current: bool
    superseded_by: str | None
    version: int
    created_at: str


@dataclass(frozen=True)
class TransmittalRow:
    id: str
    scope: str
    number: str
    title: str
    description: str | None
    state: str  # Draft, Issued, Acknowledged, Closed, Void
    voided: bool
    version: int
    direction: str
    purpose: str
    due_date: str | None
    issued_on: str | None
    response_code: str | None
    response_note: str | None
    responded_on: str | None
    recipients: list[dict[str, Any]]
    item_count: int
    created_at: str


@dataclass(frozen=True)
class TransmittalItemRow:
    transmittal_id: str
    position: int
    revision_id: str
    document_id: str
    document_number: str
    revision_code: str
    issue_status: str | None


@dataclass(frozen=True)
class ReviewCycleRow:
    id: str
    scope: str
    key: str
    title: str
    voided: bool
    version: int
    revision_id: str
    document_id: str
    round: int
    state: str  # open | closed
    due_date: str | None
    outcome: str | None
    opened_on: str | None
    closed_on: str | None


@dataclass(frozen=True)
class ReviewerRow:
    review_cycle_id: str
    revision_id: str
    document_id: str
    reviewer: str
    due_date: str | None
    outcome: str | None
    comment: str | None
    responded_on: str | None


# --- documents -------------------------------------------------------------------------------

_DOCUMENT_COLUMNS = (
    "id, scope, key, title, description, status, voided, version, conformance, doc_type, "
    "discipline, originator, confidentiality, revision_scheme, pattern_code, "
    "current_revision_id, current_revision_code, current_revision_status, current_revision_class, "
    "current_revision_issued_on, superseded_by, created_at, updated_at"
)


def _document(row: Any) -> DocumentRow:
    return DocumentRow(
        id=row.id,
        scope=row.scope,
        number=row.key,
        title=row.title,
        description=row.description,
        state=row.status or DOC_DRAFT,
        voided=bool(row.voided),
        version=row.version,
        conformance=row.conformance,
        doc_type=row.doc_type,
        discipline=row.discipline,
        originator=row.originator,
        confidentiality=row.confidentiality,
        revision_scheme=row.revision_scheme,
        pattern_code=row.pattern_code,
        current_revision_id=row.current_revision_id,
        current_revision_code=row.current_revision_code,
        current_revision_status=row.current_revision_status,
        current_revision_class=row.current_revision_class,
        current_revision_issued_on=row.current_revision_issued_on,
        superseded_by=row.superseded_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_document(conn: Connection, document_id: str) -> DocumentRow | None:
    row = conn.execute(
        text(f"SELECT {_DOCUMENT_COLUMNS} FROM {DOCUMENT_VIEW} WHERE id = :id"), {"id": document_id}
    ).first()
    return None if row is None or _hidden(conn, document_id) else _document(row)


def find_document(conn: Connection, scope: str, number: str) -> DocumentRow | None:
    row = conn.execute(
        text(
            f"SELECT {_DOCUMENT_COLUMNS} FROM {DOCUMENT_VIEW} WHERE scope = :scope AND key = :key"
        ),
        {"scope": scope, "key": number},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _document(row)


def list_documents(
    conn: Connection,
    scope: str,
    *,
    doc_type: str | None = None,
    discipline: str | None = None,
    state: str | None = None,
    limit: int = 500,
    offset: int = 0,
    include_void: bool = False,
) -> list[DocumentRow]:
    """The documents of a scope ordered by number. A void document is left out unless asked."""
    sql = f"SELECT {_DOCUMENT_COLUMNS} FROM {DOCUMENT_VIEW} WHERE scope = :scope"
    params: dict[str, Any] = {"scope": scope, "limit": limit, "offset": offset}
    visible, visible_params = confidentiality.not_hidden("id")
    sql += f" AND {visible}"
    params.update(visible_params)
    if doc_type is not None:
        sql += " AND doc_type = :doc_type"
        params["doc_type"] = doc_type
    if discipline is not None:
        sql += " AND discipline = :discipline"
        params["discipline"] = discipline
    if state is not None:
        sql += " AND COALESCE(status, 'Draft') = :state"
        params["state"] = state
    if not include_void:
        sql += " AND COALESCE(status, 'Draft') <> 'Void'"
    sql += " ORDER BY key LIMIT :limit OFFSET :offset"
    return [_document(r) for r in conn.execute(text(sql), params).all()]


# --- revisions -------------------------------------------------------------------------------

_REVISION_COLUMNS = (
    "id, scope, key, title, status, voided, version, document_id, document_number, code, ordinal, "
    "previous_revision_id, purpose, change_note, revision_date, intended_status, issue_status, "
    "status_class, issued_on, is_current, superseded_by"
)


def _revision(row: Any) -> RevisionRow:
    return RevisionRow(
        id=row.id,
        scope=row.scope,
        document_id=row.document_id,
        document_number=row.document_number,
        key=row.key,
        title=row.title,
        code=row.code,
        ordinal=int(row.ordinal),
        state=row.status or "Draft",
        voided=bool(row.voided),
        version=row.version,
        previous_revision_id=row.previous_revision_id,
        purpose=row.purpose,
        change_note=row.change_note,
        revision_date=row.revision_date,
        intended_status=row.intended_status,
        issue_status=row.issue_status,
        status_class=row.status_class,
        issued_on=row.issued_on,
        is_current=bool(row.is_current),
        superseded_by=row.superseded_by,
    )


def get_revision(conn: Connection, revision_id: str) -> RevisionRow | None:
    row = conn.execute(
        text(f"SELECT {_REVISION_COLUMNS} FROM {REVISION_VIEW} WHERE id = :id"),
        {"id": revision_id},
    ).first()
    return None if row is None or _hidden(conn, revision_id) else _revision(row)


def find_revision(conn: Connection, document_id: str, code: str) -> RevisionRow | None:
    row = conn.execute(
        text(
            f"SELECT {_REVISION_COLUMNS} FROM {REVISION_VIEW} "
            "WHERE document_id = :document_id AND code = :code"
        ),
        {"document_id": document_id, "code": code},
    ).first()
    return None if row is None or _hidden(conn, document_id) else _revision(row)


def revisions_of(
    conn: Connection, document_id: str, *, include_void: bool = True
) -> list[RevisionRow]:
    """The revisions of a document, oldest first (by ordinal)."""
    if _hidden(conn, document_id):
        return []
    sql = f"SELECT {_REVISION_COLUMNS} FROM {REVISION_VIEW} WHERE document_id = :document_id"
    if not include_void:
        sql += " AND COALESCE(status, 'Draft') <> 'Void'"
    sql += " ORDER BY ordinal"
    return [_revision(r) for r in conn.execute(text(sql), {"document_id": document_id}).all()]


def last_revision(conn: Connection, document_id: str) -> RevisionRow | None:
    """The revision with the highest ordinal, whatever its state (a void one keeps its code)."""
    if _hidden(conn, document_id):
        return None
    row = conn.execute(
        text(
            f"SELECT {_REVISION_COLUMNS} FROM {REVISION_VIEW} "
            "WHERE document_id = :document_id ORDER BY ordinal DESC LIMIT 1"
        ),
        {"document_id": document_id},
    ).first()
    return None if row is None else _revision(row)


def open_revision(conn: Connection, document_id: str) -> RevisionRow | None:
    """The revision being prepared or reviewed (state Draft or In Review), if any."""
    if _hidden(conn, document_id):
        return None
    row = conn.execute(
        text(
            f"SELECT {_REVISION_COLUMNS} FROM {REVISION_VIEW} WHERE document_id = :document_id "
            "AND COALESCE(status, 'Draft') IN ('Draft', 'In Review') ORDER BY ordinal DESC LIMIT 1"
        ),
        {"document_id": document_id},
    ).first()
    return None if row is None else _revision(row)


def highest_issued_ordinal(conn: Connection, document_id: str) -> int:
    """The highest ordinal among issued revisions (superseded ones count); 0 when none."""
    if _hidden(conn, document_id):
        return 0
    value = conn.execute(
        text(
            f"SELECT COALESCE(MAX(ordinal), 0) FROM {REVISION_VIEW} "
            "WHERE document_id = :document_id AND issued_on IS NOT NULL"
        ),
        {"document_id": document_id},
    ).scalar_one()
    return int(value)


def current_revisions(conn: Connection, document_id: str) -> list[RevisionRow]:
    """Revisions that are current in their status class, highest ordinal first."""
    if _hidden(conn, document_id):
        return []
    rows = conn.execute(
        text(
            f"SELECT {_REVISION_COLUMNS} FROM {REVISION_VIEW} "
            "WHERE document_id = :document_id AND is_current = :yes ORDER BY ordinal DESC"
        ),
        {"document_id": document_id, "yes": True},
    ).all()
    return [_revision(r) for r in rows]


# --- renditions ------------------------------------------------------------------------------

_RENDITION_COLUMNS = (
    "id, scope, key, version, created_at, revision_id, document_id, kind, file_id, filename, "
    "content_type, size, sha256, page_count, is_current, superseded_by"
)


def _rendition(row: Any) -> RenditionRow:
    return RenditionRow(
        id=row.id,
        scope=row.scope,
        revision_id=row.revision_id,
        document_id=row.document_id,
        key=row.key,
        kind=row.kind,
        file_id=row.file_id,
        filename=row.filename,
        content_type=row.content_type,
        size=int(row.size),
        sha256=row.sha256,
        page_count=None if row.page_count is None else int(row.page_count),
        is_current=bool(row.is_current),
        superseded_by=row.superseded_by,
        version=row.version,
        created_at=row.created_at,
    )


def get_rendition(conn: Connection, rendition_id: str) -> RenditionRow | None:
    row = conn.execute(
        text(f"SELECT {_RENDITION_COLUMNS} FROM {RENDITION_VIEW} WHERE id = :id"),
        {"id": rendition_id},
    ).first()
    return None if row is None or _hidden(conn, rendition_id) else _rendition(row)


def renditions_of(
    conn: Connection, revision_id: str, *, current_only: bool = False, kind: str | None = None
) -> list[RenditionRow]:
    """The renditions of a revision ordered by kind, then oldest first (by creation, id)."""
    if _hidden(conn, revision_id):
        return []
    sql = f"SELECT {_RENDITION_COLUMNS} FROM {RENDITION_VIEW} WHERE revision_id = :revision_id"
    params: dict[str, Any] = {"revision_id": revision_id}
    if current_only:
        sql += " AND is_current = :yes"
        params["yes"] = True
    if kind is not None:
        sql += " AND kind = :kind"
        params["kind"] = kind
    sql += " ORDER BY kind, created_at, id"
    return [_rendition(r) for r in conn.execute(text(sql), params).all()]


def rendition_count(conn: Connection, revision_id: str, kind: str) -> int:
    """How many renditions of ``kind`` the revision has had (superseded ones included)."""
    if _hidden(conn, revision_id):
        return 0
    value = conn.execute(
        text(
            f"SELECT COUNT(*) FROM {RENDITION_VIEW} "
            "WHERE revision_id = :revision_id AND kind = :kind"
        ),
        {"revision_id": revision_id, "kind": kind},
    ).scalar_one()
    return int(value)


# --- transmittals ----------------------------------------------------------------------------

_TRANSMITTAL_COLUMNS = (
    "id, scope, key, title, description, status, voided, version, created_at, direction, purpose, "
    "due_date, issued_on, response_code, response_note, responded_on, recipients_json, item_count"
)


def _transmittal(row: Any) -> TransmittalRow:
    return TransmittalRow(
        id=row.id,
        scope=row.scope,
        number=row.key,
        title=row.title,
        description=row.description,
        state=row.status or TR_DRAFT,
        voided=bool(row.voided),
        version=row.version,
        direction=row.direction,
        purpose=row.purpose,
        due_date=row.due_date,
        issued_on=row.issued_on,
        response_code=row.response_code,
        response_note=row.response_note,
        responded_on=row.responded_on,
        recipients=list(_json(row.recipients_json, [])),
        item_count=int(row.item_count),
        created_at=row.created_at,
    )


def get_transmittal(conn: Connection, transmittal_id: str) -> TransmittalRow | None:
    row = conn.execute(
        text(f"SELECT {_TRANSMITTAL_COLUMNS} FROM {TRANSMITTAL_VIEW} WHERE id = :id"),
        {"id": transmittal_id},
    ).first()
    return None if row is None else _transmittal(row)


def find_transmittal(conn: Connection, scope: str, number: str) -> TransmittalRow | None:
    row = conn.execute(
        text(
            f"SELECT {_TRANSMITTAL_COLUMNS} FROM {TRANSMITTAL_VIEW} "
            "WHERE scope = :scope AND key = :key"
        ),
        {"scope": scope, "key": number},
    ).first()
    return None if row is None else _transmittal(row)


def list_transmittals(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[TransmittalRow]:
    """The transmittals of a scope by number; void ones are left out unless asked for by state."""
    sql = f"SELECT {_TRANSMITTAL_COLUMNS} FROM {TRANSMITTAL_VIEW} WHERE scope = :scope"
    params: dict[str, Any] = {"scope": scope, "limit": limit, "offset": offset}
    if state is not None:
        sql += " AND COALESCE(status, 'Draft') = :state"
        params["state"] = state
    else:
        sql += " AND COALESCE(status, 'Draft') <> 'Void'"
    if direction is not None:
        sql += " AND direction = :direction"
        params["direction"] = direction
    sql += " ORDER BY key LIMIT :limit OFFSET :offset"
    return [_transmittal(r) for r in conn.execute(text(sql), params).all()]


def transmittal_items(conn: Connection, transmittal_id: str) -> list[TransmittalItemRow]:
    rows = conn.execute(
        text(
            "SELECT transmittal_id, position, revision_id, document_id, document_number, "
            f"revision_code, issue_status FROM {TRANSMITTAL_ITEM_TABLE} "
            "WHERE transmittal_id = :id ORDER BY position"
        ),
        {"id": transmittal_id},
    ).all()
    hidden = confidentiality.hidden_among(conn, [r.revision_id for r in rows])
    rows = [r for r in rows if r.revision_id not in hidden]  # an item the viewer may not read
    return [
        TransmittalItemRow(
            transmittal_id=r.transmittal_id,
            position=int(r.position),
            revision_id=r.revision_id,
            document_id=r.document_id,
            document_number=r.document_number,
            revision_code=r.revision_code,
            issue_status=r.issue_status,
        )
        for r in rows
    ]


def transmittals_of_revision(conn: Connection, revision_id: str) -> list[TransmittalRow]:
    """The transmittals that carry a revision (void ones left out), oldest number first."""
    if _hidden(conn, revision_id):
        return []
    rows = conn.execute(
        text(
            f"SELECT {_TRANSMITTAL_COLUMNS} FROM {TRANSMITTAL_VIEW} WHERE id IN "
            f"(SELECT transmittal_id FROM {TRANSMITTAL_ITEM_TABLE} WHERE revision_id = :rid) "
            "AND COALESCE(status, 'Draft') <> 'Void' ORDER BY key"
        ),
        {"rid": revision_id},
    ).all()
    return [_transmittal(r) for r in rows]


# --- review cycles ---------------------------------------------------------------------------

_CYCLE_COLUMNS = (
    "id, scope, key, title, voided, version, revision_id, document_id, round, state, due_date, "
    "outcome, opened_on, closed_on"
)


def _cycle(row: Any) -> ReviewCycleRow:
    return ReviewCycleRow(
        id=row.id,
        scope=row.scope,
        key=row.key,
        title=row.title,
        voided=bool(row.voided),
        version=row.version,
        revision_id=row.revision_id,
        document_id=row.document_id,
        round=int(row.round),
        state=row.state,
        due_date=row.due_date,
        outcome=row.outcome,
        opened_on=row.opened_on,
        closed_on=row.closed_on,
    )


def get_review_cycle(conn: Connection, cycle_id: str) -> ReviewCycleRow | None:
    row = conn.execute(
        text(f"SELECT {_CYCLE_COLUMNS} FROM {REVIEW_CYCLE_VIEW} WHERE id = :id"), {"id": cycle_id}
    ).first()
    return None if row is None or _hidden(conn, cycle_id) else _cycle(row)


def review_cycles_of(conn: Connection, revision_id: str) -> list[ReviewCycleRow]:
    """The review cycles of a revision, round by round."""
    if _hidden(conn, revision_id):
        return []
    rows = conn.execute(
        text(
            f"SELECT {_CYCLE_COLUMNS} FROM {REVIEW_CYCLE_VIEW} "
            "WHERE revision_id = :rid ORDER BY round"
        ),
        {"rid": revision_id},
    ).all()
    return [_cycle(r) for r in rows]


def open_review_cycle(conn: Connection, revision_id: str) -> ReviewCycleRow | None:
    if _hidden(conn, revision_id):
        return None
    row = conn.execute(
        text(
            f"SELECT {_CYCLE_COLUMNS} FROM {REVIEW_CYCLE_VIEW} "
            "WHERE revision_id = :rid AND state = 'open' ORDER BY round DESC LIMIT 1"
        ),
        {"rid": revision_id},
    ).first()
    return None if row is None else _cycle(row)


def reviewers_of(conn: Connection, cycle_id: str) -> list[ReviewerRow]:
    if _hidden(conn, cycle_id):
        return []
    rows = conn.execute(
        text(
            "SELECT review_cycle_id, revision_id, document_id, reviewer, due_date, outcome, "
            f"comment, responded_on FROM {REVIEWER_TABLE} WHERE review_cycle_id = :id "
            "ORDER BY reviewer_id"
        ),
        {"id": cycle_id},
    ).all()
    return [
        ReviewerRow(
            review_cycle_id=r.review_cycle_id,
            revision_id=r.revision_id,
            document_id=r.document_id,
            reviewer=r.reviewer,
            due_date=r.due_date,
            outcome=r.outcome,
            comment=r.comment,
            responded_on=r.responded_on,
        )
        for r in rows
    ]
