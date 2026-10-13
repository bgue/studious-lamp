"""What a screen, a client or an agent reads about documents (brief 9 M1; P1-I2).

The TUI client interface, the API (and so the API client) and the MCP tools all return these models,
so an embedded screen, a remote one and an agent see the same fields. A listing carries no revisions
or links; ``document_view`` fills them for one document. Every function here only reads.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import Connection

from tl_mod_documents import registry, reports, resolver
from tl_mod_documents.errors import DocumentNotFoundError, TransmittalNotFoundError
from tl_mod_documents.limits import CONFIDENTIALITY_NOTE


class RenditionView(BaseModel):
    kind: str
    filename: str
    content_type: str
    size: int
    sha256: str
    page_count: int | None
    is_current: bool

    @classmethod
    def of(cls, row: registry.RenditionRow) -> RenditionView:
        return cls(**{name: getattr(row, name) for name in cls.model_fields})


class RevisionView(BaseModel):
    id: str
    code: str
    state: str  # Draft | In Review | Issued | Superseded | Void
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    purpose: str | None
    change_note: str | None
    revision_date: str | None
    intended_status: str | None
    superseded_by: str | None  # the code of the revision that replaced it
    renditions: list[RenditionView] = []


class DocumentLinkView(BaseModel):
    """A link to the document and what its pin means now."""

    link_id: str
    from_key: str | None
    from_type: str
    from_title: str
    relation: str
    link_status: str  # active | stale
    pin: str | None  # None floats
    pin_state: str  # current | stale | floating | no_current | unknown
    current_code: str | None
    newer_codes: list[str]


class DocumentView(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    state: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None = Field(description=CONFIDENTIALITY_NOTE)
    revision_scheme: str
    pattern_code: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None  # the number of the document that replaced it
    conformance: str
    version: int
    revisions: list[RevisionView] = []
    links: list[DocumentLinkView] = []


class TransmittalItemView(BaseModel):
    position: int
    document_number: str
    revision_code: str
    issue_status: str | None


class TransmittalView(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    state: str
    direction: str
    purpose: str
    due_date: str | None
    issued_on: str | None
    response_code: str | None
    response_note: str | None
    responded_on: str | None
    recipients: list[dict[str, str | None]] = Field(description=CONFIDENTIALITY_NOTE)
    version: int
    items: list[TransmittalItemView] = []


class RevisionDiffView(BaseModel):
    document_number: str
    from_code: str
    to_code: str
    from_status: str | None
    to_status: str | None
    summary: list[str]


def _document_number(conn: Connection, document_id: str | None) -> str | None:
    if document_id is None:
        return None
    found = registry.get_document(conn, document_id)
    return None if found is None else found.number


def _document(conn: Connection, row: registry.DocumentRow) -> DocumentView:
    return DocumentView(
        id=row.id,
        number=row.number,
        title=row.title,
        description=row.description,
        state="Void" if row.voided else row.state,
        doc_type=row.doc_type,
        discipline=row.discipline,
        originator=row.originator,
        confidentiality=row.confidentiality,
        revision_scheme=row.revision_scheme,
        pattern_code=row.pattern_code,
        current_revision_code=row.current_revision_code,
        current_revision_status=row.current_revision_status,
        current_revision_class=row.current_revision_class,
        current_revision_issued_on=row.current_revision_issued_on,
        superseded_by=_document_number(conn, row.superseded_by),
        conformance=row.conformance,
        version=row.version,
    )


def document_views(
    conn: Connection,
    scope: str,
    *,
    doc_type: str | None = None,
    discipline: str | None = None,
    state: str | None = None,
    include_void: bool = False,
    limit: int = 1000,
) -> list[DocumentView]:
    """The documents of ``scope`` by number, without revisions or links."""
    rows = registry.list_documents(
        conn,
        scope,
        doc_type=doc_type,
        discipline=discipline,
        state=state,
        limit=limit,
        include_void=include_void,
    )
    return [_document(conn, row) for row in rows]


def document_view(conn: Connection, scope: str, number: str) -> DocumentView:
    """One document with its revisions (renditions included) and the links to it.

    Raises ``DocumentNotFoundError`` when the number is unknown in the scope.
    """
    row = registry.find_document(conn, scope, number)
    if row is None:
        raise DocumentNotFoundError(f"no document {number!r} in scope {scope!r}")
    revisions = registry.revisions_of(conn, row.id)
    codes = {r.id: r.code for r in revisions}
    shown = [
        RevisionView(
            id=r.id,
            code=r.code,
            state="Void" if r.voided else r.state,
            issue_status=r.issue_status,
            status_class=r.status_class,
            issued_on=r.issued_on,
            is_current=r.is_current,
            purpose=r.purpose,
            change_note=r.change_note,
            revision_date=r.revision_date,
            intended_status=r.intended_status,
            superseded_by=codes.get(r.superseded_by) if r.superseded_by else None,
            renditions=[
                RenditionView.of(x) for x in registry.renditions_of(conn, r.id, current_only=True)
            ],
        )
        for r in revisions
    ]
    links = [
        DocumentLinkView(
            link_id=item.link_id,
            from_key=item.from_key,
            from_type=item.from_type,
            from_title=item.from_title,
            relation=item.relation,
            link_status=item.link_status,
            pin=item.pin,
            pin_state=item.resolution.state,
            current_code=item.resolution.current_code,
            newer_codes=item.resolution.newer_codes,
        )
        for item in resolver.links_to_documents(conn, scope, document_id=row.id)
    ]
    return _document(conn, row).model_copy(update={"revisions": shown, "links": links})


def stale_links(conn: Connection, scope: str) -> list[reports.StalePinLine]:
    """Links whose pin is behind or whose target was voided or superseded (the report rows)."""
    return reports.stale_pins(conn, scope)


def overdue_reviews(
    conn: Connection, scope: str, *, on: date | None = None
) -> list[reports.OverdueLine]:
    """Open reviews with a reviewer who has not answered by the date (the report rows)."""
    return reports.overdue_reviews(conn, scope, on=on)


def revision_diff_view(
    conn: Connection, scope: str, number: str, from_code: str, to_code: str
) -> RevisionDiffView:
    """What changed between two issued revisions. Raises ``DocumentNotFoundError`` and
    ``InvalidPinError``."""
    row = registry.find_document(conn, scope, number)
    if row is None:
        raise DocumentNotFoundError(f"no document {number!r} in scope {scope!r}")
    found = resolver.revision_diff(conn, row.id, from_code, to_code)
    return RevisionDiffView(
        document_number=found.document_number,
        from_code=found.from_code,
        to_code=found.to_code,
        from_status=found.from_status,
        to_status=found.to_status,
        summary=found.summary,
    )


def transmittal_views(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    limit: int = 500,
) -> list[TransmittalView]:
    """The transmittals of ``scope`` by number, without items."""
    rows = registry.list_transmittals(conn, scope, state=state, direction=direction, limit=limit)
    return [_transmittal(row, []) for row in rows]


def transmittal_view(conn: Connection, scope: str, number: str) -> TransmittalView:
    """One transmittal with its items. Raises ``TransmittalNotFoundError``."""
    row = registry.find_transmittal(conn, scope, number)
    if row is None:
        raise TransmittalNotFoundError(f"no transmittal {number!r} in scope {scope!r}")
    return _transmittal(row, registry.transmittal_items(conn, row.id))


def _transmittal(
    row: registry.TransmittalRow, items: list[registry.TransmittalItemRow]
) -> TransmittalView:
    return TransmittalView(
        id=row.id,
        number=row.number,
        title=row.title,
        description=row.description,
        state="Void" if row.voided else row.state,
        direction=row.direction,
        purpose=row.purpose,
        due_date=row.due_date,
        issued_on=row.issued_on,
        response_code=row.response_code,
        response_note=row.response_note,
        responded_on=row.responded_on,
        recipients=row.recipients,
        version=row.version,
        items=[
            TransmittalItemView(
                position=i.position,
                document_number=i.document_number,
                revision_code=i.revision_code,
                issue_status=i.issue_status,
            )
            for i in items
        ],
    )
