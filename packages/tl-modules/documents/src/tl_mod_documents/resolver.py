"""The pin and stale resolver: what a link's pin means, when it is stale, what changed (brief 7.3).

A link to a document can pin a revision (``pin`` is the revision code) or float (no pin: it means
the document's current revision). This module is the one place that decides what a pin means:

* ``resolve_pin`` says which revision a pin names and whether a newer one has been issued;
* ``flag_stale_on_issue`` is called when a revision is issued: every active link pinned to another
  revision of the document goes ``stale`` (the core's ``MarkPinsStale``; one ``Link.Flagged`` event
  per link, which webhook subscribers and the feed see, so the link's owners are told);
* ``flag_links_to_document`` is called when a document is voided or superseded: every active link to
  it, pinned or floating, goes ``stale`` (brief 7.3: target voided or superseded);
* ``revision_diff`` summarises what changed between two revisions, for the re-pin dialog: a person
  sees it before confirming (``RepinDocumentLink``);
* ``link_to_document`` and ``repin_document_link`` are the commands that check a pin names an
  issued revision before they call the core's link handlers.

A link with a floating pin is never stale because of a new revision; it always resolves to the
current one. A pin that names a revision the document does not have resolves as ``unknown``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import ConfigDict, Field
from sqlalchemy import Connection, text
from tl_core.ledger import Event
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.services.links import (
    AddLink,
    FlagLink,
    MarkPinsStale,
    RepinLink,
    handle_add_link,
    handle_flag_link,
    handle_mark_pins_stale,
    handle_repin_link,
)
from tl_core.uow import UnitOfWork

from tl_mod_documents import registry
from tl_mod_documents.errors import DocumentNotFoundError, InvalidPinError
from tl_mod_documents.handlers.common import correlated, load_document
from tl_mod_documents.limits import MAX_NUMBER, MAX_REASON
from tl_mod_documents.names import DOCUMENT, PIN_RELATION

PinState = Literal["current", "stale", "floating", "no_current", "unknown"]
_LIVE_TO_SQL = text(
    "SELECT link_id, scope, from_id, relation, status, pin, version FROM cur_links "
    "WHERE to_id = :id AND status = 'active' ORDER BY created_at, link_id"
)
_LINKS_OF_DOCS_SQL = (
    "SELECT l.link_id, l.scope, l.from_id, l.to_id, l.relation, l.status, l.pin, l.updated_at, "
    "d.key AS document_number, d.title AS document_title, "
    "x.key AS from_key, x.type AS from_type, x.title AS from_title "
    "FROM cur_links l JOIN cur_core_record d ON d.id = l.to_id "
    "JOIN cur_core_record x ON x.id = l.from_id "
    "WHERE d.type = :document_type AND l.scope = :scope AND l.status IN ('active', 'stale')"
)


@dataclass(frozen=True)
class PinResolution:
    """What a pin on a document means now."""

    document_id: str
    document_number: str
    pin: str | None  # as stored on the link; None floats
    state: PinState
    resolved_code: (
        str | None
    )  # the revision the link means: the pin, or the current one when floating
    resolved_revision_id: str | None
    current_code: str | None  # the document's current revision
    newer_codes: list[str] = field(default_factory=lambda: [])  # issued revisions after the pin

    @property
    def stale(self) -> bool:
        return self.state == "stale"


def resolve_pin(conn: Connection, document_id: str, pin: str | None) -> PinResolution:
    """Which revision ``pin`` means for the document, and whether it is behind.

    ``current`` the pin is the document's current revision; ``stale`` an issued revision after the
    pinned one exists (``newer_codes`` lists them); ``floating`` no pin, so it means the current
    revision; ``no_current`` floating on a document with no issued revision yet; ``unknown`` the
    pin names no revision of the document. Raises ``DocumentNotFoundError``.
    """
    doc = registry.get_document(conn, document_id)
    if doc is None:
        raise DocumentNotFoundError(f"no document {document_id!r}")
    if pin is None:
        state: PinState = "floating" if doc.current_revision_id is not None else "no_current"
        return PinResolution(
            document_id=doc.id,
            document_number=doc.number,
            pin=None,
            state=state,
            resolved_code=doc.current_revision_code,
            resolved_revision_id=doc.current_revision_id,
            current_code=doc.current_revision_code,
        )
    pinned = registry.find_revision(conn, doc.id, pin)
    if pinned is None or not pinned.issued or pinned.voided:
        return PinResolution(
            document_id=doc.id,
            document_number=doc.number,
            pin=pin,
            state="unknown",
            resolved_code=None,
            resolved_revision_id=None,
            current_code=doc.current_revision_code,
        )
    newer = [
        r.code
        for r in registry.revisions_of(conn, doc.id, include_void=False)
        if r.issued and r.ordinal > pinned.ordinal
    ]
    return PinResolution(
        document_id=doc.id,
        document_number=doc.number,
        pin=pin,
        state="stale" if newer else "current",
        resolved_code=pinned.code,
        resolved_revision_id=pinned.id,
        current_code=doc.current_revision_code,
        newer_codes=newer,
    )


@dataclass(frozen=True)
class PinnedLink:
    """One link that points to a document, with what its pin means now."""

    link_id: str
    from_id: str
    from_key: str | None
    from_type: str
    from_title: str
    document_id: str
    document_number: str
    document_title: str
    relation: str
    link_status: str  # active | stale (the link lifecycle)
    pin: str | None
    resolution: PinResolution


def links_to_documents(
    conn: Connection,
    scope: str,
    *,
    document_id: str | None = None,
    only_stale: bool = False,
    limit: int = 1000,
) -> list[PinnedLink]:
    """Links (active or stale) that point to a document of the scope, with each pin resolved.

    ``only_stale`` keeps links whose status is stale or whose pin is behind. Ordered by document
    number, then the key of the record that links. This is what the stale pinned revisions report
    and a document's links tab read.
    """
    sql = _LINKS_OF_DOCS_SQL
    params: dict[str, object] = {"document_type": DOCUMENT, "scope": scope, "limit": limit}
    if document_id is not None:
        sql += " AND l.to_id = :document_id"
        params["document_id"] = document_id
    sql += " ORDER BY d.key, x.key, l.link_id LIMIT :limit"
    found: list[PinnedLink] = []
    for row in conn.execute(text(sql), params).all():
        resolution = resolve_pin(conn, row.to_id, row.pin)
        if only_stale and row.status != "stale" and not resolution.stale:
            continue
        found.append(
            PinnedLink(
                link_id=row.link_id,
                from_id=row.from_id,
                from_key=row.from_key,
                from_type=row.from_type,
                from_title=row.from_title,
                document_id=row.to_id,
                document_number=row.document_number,
                document_title=row.document_title,
                relation=row.relation,
                link_status=row.status,
                pin=row.pin,
                resolution=resolution,
            )
        )
    return found


# --- revision diff ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenditionChange:
    kind: str
    change: Literal["added", "removed", "changed", "unchanged"]
    before: str | None  # "name, 48 KB, 3 pages"
    after: str | None


@dataclass(frozen=True)
class RevisionDiff:
    """What changed from one revision of a document to another, for a person about to re-pin."""

    document_number: str
    from_code: str
    to_code: str
    from_status: str | None
    to_status: str | None
    steps: list[str]  # one line per revision issued after ``from`` up to ``to``
    renditions: list[RenditionChange]
    summary: list[str]  # the same facts as short sentences, in reading order

    @property
    def changed(self) -> bool:
        return any(c.change != "unchanged" for c in self.renditions) or bool(self.steps)


def _describe(row: registry.RenditionRow) -> str:
    pages = f", {row.page_count} pages" if row.page_count is not None else ""
    return f"{row.filename}, {_size(row.size)}{pages}"


def _size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def revision_diff(conn: Connection, document_id: str, from_code: str, to_code: str) -> RevisionDiff:
    """The difference between two issued revisions of a document.

    ``steps`` lists each revision issued after ``from_code`` up to and including ``to_code``, with
    its status, date, purpose and change note; ``renditions`` compares the current file of each
    kind on the two revisions (by content hash). Raises ``DocumentNotFoundError`` and
    ``InvalidPinError`` (a code that is not an issued revision of the document).
    """
    doc = registry.get_document(conn, document_id)
    if doc is None:
        raise DocumentNotFoundError(f"no document {document_id!r}")
    before = registry.find_revision(conn, doc.id, from_code)
    after = registry.find_revision(conn, doc.id, to_code)
    for code, row in ((from_code, before), (to_code, after)):
        if row is None or not row.issued or row.voided:
            raise InvalidPinError(f"{code!r} is not an issued revision of {doc.number}")
    assert before is not None and after is not None
    ordered = registry.revisions_of(conn, doc.id, include_void=False)
    lo, hi = sorted((before.ordinal, after.ordinal))
    steps = []
    for rev in ordered:
        if lo < rev.ordinal <= hi and rev.issued:
            line = f"{rev.code} ({rev.issue_status}, {rev.issued_on})"
            notes = [n for n in (rev.purpose, rev.change_note) if n]
            steps.append(line + (": " + "; ".join(notes) if notes else ""))
    old = {r.kind: r for r in registry.renditions_of(conn, before.id, current_only=True)}
    new = {r.kind: r for r in registry.renditions_of(conn, after.id, current_only=True)}
    changes: list[RenditionChange] = []
    for kind in sorted(set(old) | set(new)):
        a, b = old.get(kind), new.get(kind)
        if a is None and b is not None:
            changes.append(RenditionChange(kind, "added", None, _describe(b)))
        elif a is not None and b is None:
            changes.append(RenditionChange(kind, "removed", _describe(a), None))
        elif a is not None and b is not None:
            same = a.sha256 == b.sha256
            changes.append(
                RenditionChange(
                    kind, "unchanged" if same else "changed", _describe(a), _describe(b)
                )
            )
    first = f"{before.code} ({before.issue_status})"
    last = f"{after.code} ({after.issue_status})"
    summary = [f"{doc.number}: {first} to {last}"]
    if before.issue_status != after.issue_status:
        summary.append(f"status {before.issue_status} to {after.issue_status}")
    summary += [f"issued {step}" for step in steps]
    for change in changes:
        if change.change == "added":
            summary.append(f"{change.kind} added: {change.after}")
        elif change.change == "removed":
            summary.append(f"{change.kind} no longer present (was {change.before})")
        elif change.change == "changed":
            summary.append(f"{change.kind} changed: {change.before} to {change.after}")
    return RevisionDiff(
        document_number=doc.number,
        from_code=before.code,
        to_code=after.code,
        from_status=before.issue_status,
        to_status=after.issue_status,
        steps=steps,
        renditions=changes,
        summary=summary,
    )


# --- flagging --------------------------------------------------------------------------------


def flag_stale_on_issue(uow: UnitOfWork, cmd: Command, document_id: str, code: str) -> list[Event]:
    """Flag every active link pinned to another revision than ``code`` as stale; return the events.

    One ``Link.Flagged`` event (stale, reason ``revision <code> issued``) per link, in the same
    unit of work and correlation as the issue. A floating link is untouched.
    """
    try:
        result = handle_mark_pins_stale(
            uow,
            MarkPinsStale(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                record_id=document_id,
                current_pin=code,
            ),
        )
    except NoChangesError:
        return []
    return list(result.events)


def flag_links_to_document(
    uow: UnitOfWork, cmd: Command, document_id: str, reason: str
) -> list[Event]:
    """Flag every active link to the document stale (voided or superseded); return the events."""
    rows = uow.conn().execute(_LIVE_TO_SQL, {"id": document_id}).all()
    events: list[Event] = []
    for row in rows:
        flagged = handle_flag_link(
            uow,
            FlagLink(
                actor=cmd.actor,
                source=cmd.source,
                scope=row.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                link_id=row.link_id,
                status="stale",
                reason=reason,
            ),
            by_module=True,
        )
        events += flagged.events
    return events


# --- commands --------------------------------------------------------------------------------

CURRENT = "current"  # the pin keyword that means "the document's current revision, pinned"


def _pin_code(conn: Connection, document_id: str, number: str, pin: str | None) -> str | None:
    """The revision code to store for ``pin``: None floats, ``current`` becomes today's code."""
    if pin is None:
        return None
    if pin == CURRENT:
        doc = registry.get_document(conn, document_id)
        if doc is None or doc.current_revision_code is None:
            raise InvalidPinError(f"{number} has no current revision to pin")
        return doc.current_revision_code
    found = registry.find_revision(conn, document_id, pin)
    if found is None or not found.issued or found.voided:
        raise InvalidPinError(f"{pin!r} is not an issued revision of {number}")
    return found.code


class LinkToDocument(Command):
    """Link a record to a document, floating or pinned to an issued revision.

    ``pin`` is a revision code, ``current`` (pin the revision that is current now), or empty to
    float. The source record's type decides whether it may be linked at all (the generic ``AddLink``
    allow-list); this command adds the check that the pin names a real issued revision.
    """

    model_config = ConfigDict(extra="forbid")

    from_id: str
    document_id: str
    relation: str = Field(default=PIN_RELATION, max_length=MAX_NUMBER)
    pin: str | None = Field(default=None, max_length=MAX_NUMBER)
    note: str | None = Field(default=None, max_length=MAX_REASON)


class RepinDocumentLink(Command):
    """Move a link to another revision of its document (``current`` for the current one).

    Bring a stale link back to active. Show the person ``revision_diff`` first; the command itself
    only records the decision.
    """

    model_config = ConfigDict(extra="forbid")

    link_id: str
    pin: str | None = Field(default=CURRENT, max_length=MAX_NUMBER)
    expected_version: int | None = None


def handle_link_to_document(uow: UnitOfWork, cmd: LinkToDocument) -> CommandResult:
    """Emits ``Link.Added``. Raises ``DocumentNotFoundError``, ``InvalidPinError``, link errors."""
    document = load_document(uow, cmd, cmd.document_id)
    if document.closed:
        raise InvalidPinError(
            f"document {document.number} is {document.state}; it cannot be linked to"
        )
    pin = _pin_code(uow.conn(), document.id, document.number, cmd.pin)
    return handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=cmd.from_id,
            to_id=document.id,
            relation=cmd.relation,
            pin=pin,
            note=cmd.note,
        ),
    )


_LINK_SQL = text("SELECT link_id, scope, to_id, pin, status FROM cur_links WHERE link_id = :id")


def handle_repin_document_link(uow: UnitOfWork, cmd: RepinDocumentLink) -> CommandResult:
    """Emits ``Link.Repinned``. Raises ``RecordNotFoundError``, ``InvalidPinError``, link errors."""
    cmd = correlated(cmd)
    link = uow.conn().execute(_LINK_SQL, {"id": cmd.link_id}).first()
    if link is None or link.scope != cmd.scope:
        raise RecordNotFoundError(f"no link {cmd.link_id!r} in scope {cmd.scope!r}")
    document = registry.get_document(uow.conn(), link.to_id)
    if document is None:
        raise InvalidPinError("this link does not point to a document")
    pin = _pin_code(uow.conn(), document.id, document.number, cmd.pin)
    return handle_repin_link(
        uow,
        RepinLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            link_id=cmd.link_id,
            expected_version=cmd.expected_version,
            pin=pin,
        ),
    )
