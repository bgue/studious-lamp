"""Rendition commands: register an uploaded file as a rendition of a revision (brief 9 M1).

The file service holds the bytes (``cur_files``). A person uploads a file into one of the four slots
of a revision (``native``, ``pdf``, ``markup``, ``signed``); that upload is only a file until
``AttachRendition`` registers it: the rendition record is the controlled statement that this file
is that revision's copy of that kind.

What a revision accepts depends on its state, because the content of a revision is frozen once it is
reviewed or issued (the same table guards the upload itself, ``guards.UPLOAD_KINDS``):

=============  ==========================================
State          Kinds that may be added
=============  ==========================================
Draft          native, pdf, markup
In Review      markup (reviewers' comments on the PDF)
Issued         markup, signed
Superseded     markup, signed
Void           none
=============  ==========================================

How a new rendition treats the old ones depends on the kind (P1-I2 security review):

* ``native`` and ``pdf``: the newest is the copy; the older one is superseded.
* ``markup``: additive. Every reviewer's markup stays current; one never replaces another's.
* ``signed``: an admin's act from the first copy (ADR-0011). ``AttachRendition`` refuses it for
  everyone; the admin command ``RegisterSignedRendition`` registers the first signed copy, and the
  write-once rule keeps it: a correction is ``ReplaceSignedRendition`` with a reason, which
  supersedes it.

``markup`` is capped (``limits.MAX_MARKUPS`` current ones per revision), so a loop cannot fill a
revision with them.

Concurrency. Every check below reads the revision's renditions and then appends. On Postgres and
SQLite a write unit of work takes the ledger's single writer lock before its first statement
(``tl_adapters.postgres.engine``), so two registrations of the same kind never interleave and
"one current rendition per native or PDF" and "one signed copy" hold without a unique index.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from tl_core.files.queries import get_file
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, UnknownFileError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_documents import registry
from tl_mod_documents.errors import FileNotAvailableError, RenditionNotAllowedError
from tl_mod_documents.guards import UPLOAD_KINDS
from tl_mod_documents.handlers.common import (
    append,
    correlated,
    load_revision,
    open_document,
    require_project,
)
from tl_mod_documents.limits import MAX_MARKUPS, MAX_NUMBER, MAX_PAGES, MAX_REASON
from tl_mod_documents.names import (
    RENDITION,
    RENDITION_DEFINED,
    RENDITION_KINDS,
    RENDITION_SUPERSEDED,
)

#: Kinds a revision accepts in each state (the table above; shared with the upload guard).
ALLOWED_KINDS = UPLOAD_KINDS
#: Kinds where the newest rendition replaces the older one.
REPLACING_KINDS = ("native", "pdf")


class AttachRendition(Command):
    """Register an uploaded, scanned file of a revision as a rendition.

    ``file_id`` is a file attached to the revision in the slot named like the rendition kind.
    ``page_count`` is optional (an extractor fills it in later).
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    file_id: str = Field(min_length=1, max_length=MAX_NUMBER)
    page_count: int | None = Field(default=None, ge=0, le=MAX_PAGES)


class RegisterSignedRendition(Command):
    """Register the first signed copy of a revision (admin). The reason is optional.

    The signed copy is evidence, so registering it is not open to everyone (ADR-0011). Once a
    revision has one, a correction is ``ReplaceSignedRendition``.
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    file_id: str = Field(min_length=1, max_length=MAX_NUMBER)
    page_count: int | None = Field(default=None, ge=0, le=MAX_PAGES)
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class ReplaceSignedRendition(Command):
    """Replace the signed copy of a revision by another file, with a reason (admin).

    The signed copy is write-once for everyone else: a correction is an admin's decision and the
    reason is kept in the event.
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    file_id: str = Field(min_length=1, max_length=MAX_NUMBER)
    page_count: int | None = Field(default=None, ge=0, le=MAX_PAGES)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def _register(
    uow: UnitOfWork,
    cmd: AttachRendition | RegisterSignedRendition | ReplaceSignedRendition,
    *,
    replacing: bool,
    signed_command: bool = False,
) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    rev = load_revision(uow, cmd, cmd.revision_id)
    open_document(uow, cmd, rev.document_id)
    state = "Void" if rev.voided else rev.state
    try:
        info = get_file(uow, cmd.scope, cmd.file_id)
    except UnknownFileError as exc:
        raise FileNotAvailableError(str(exc)) from exc
    if info.record_id != rev.id:
        raise FileNotAvailableError(f"file {info.filename!r} is not attached to revision {rev.key}")
    if info.slot not in RENDITION_KINDS:
        raise FileNotAvailableError(
            f"file {info.filename!r} is not in a rendition slot ({', '.join(RENDITION_KINDS)})"
        )
    if not info.current:
        raise FileNotAvailableError(
            f"file {info.filename!r} is {info.status}"
            + (" and was replaced" if info.superseded_by else "")
            + "; only an available file can become a rendition"
        )
    kind = info.slot
    allowed = ALLOWED_KINDS.get(state, ())
    if kind not in allowed:
        raise RenditionNotAllowedError(
            f"revision {rev.code} of {rev.document_number} is {state}; "
            + (f"it accepts {', '.join(allowed)}" if allowed else "it accepts no renditions")
        )
    conn = uow.conn()
    existing = registry.renditions_of(conn, rev.id, kind=kind)
    current = [r for r in existing if r.is_current]
    if any(r.file_id == info.file_id for r in current):
        raise NoChangesError(f"file {info.filename!r} is already a {kind} rendition")
    if (replacing or signed_command) and kind != "signed":
        raise RenditionNotAllowedError("only a signed copy is registered this way")
    if kind == "signed":
        if not (replacing or signed_command):
            raise RenditionNotAllowedError(
                "the signed copy is registered by an admin with RegisterSignedRendition "
                "(ReplaceSignedRendition to correct it)"
            )
        if current and not replacing:
            raise RenditionNotAllowedError(
                f"revision {rev.code} of {rev.document_number} already has a signed copy, which "
                "is final; an admin replaces it with ReplaceSignedRendition and a reason"
            )
        if replacing and not current:
            raise RenditionNotAllowedError(
                f"revision {rev.code} of {rev.document_number} has no signed copy to replace; "
                "register the first one with RegisterSignedRendition"
            )
    if kind == "markup" and len(current) >= MAX_MARKUPS:
        raise RenditionNotAllowedError(
            f"revision {rev.code} of {rev.document_number} already has {MAX_MARKUPS} markups"
        )
    older = current if kind in REPLACING_KINDS or replacing else []
    made = create_module_record(
        uow,
        cmd,
        record_type=RENDITION,
        title=f"{rev.key} {kind}",
        key=f"{rev.key}/{kind}-{len(existing) + 1}",
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=RENDITION_DEFINED,
                payload={
                    "revision_id": rev.id,
                    "document_id": rev.document_id,
                    "kind": kind,
                    "file_id": info.file_id,
                    "filename": info.filename,
                    "content_type": info.content_type,
                    "size": info.size,
                    "sha256": info.sha256,
                    "page_count": cmd.page_count,
                    "supersedes": [r.id for r in older],
                    "replace_reason": None if isinstance(cmd, AttachRendition) else cmd.reason,
                },
            )
        ],
    )
    events: list[Event] = list(made.events)
    for previous in older:
        events += append(
            uow,
            cmd,
            previous.id,
            RENDITION,
            [NewEvent(event_type=RENDITION_SUPERSEDED, payload={"superseded_by": made.stream_id})],
        ).events
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=made.version, events=events
    )


def handle_attach_rendition(uow: UnitOfWork, cmd: AttachRendition) -> CommandResult:
    """Append ``Record.Created`` and ``Rendition.Defined``; supersede the previous native or PDF.

    Raises ``ProjectScopeError``, ``RevisionNotFoundError``, ``DocumentClosedError``,
    ``FileNotAvailableError`` (unknown file, not on this revision, not in a rendition slot, still in
    quarantine or rejected), ``RenditionNotAllowedError`` (the revision's state does not take that
    kind, the kind is ``signed``, or the revision already has the most markups it may) and
    ``NoChangesError`` (the file is already a current rendition).
    """
    return _register(uow, cmd, replacing=False)


def handle_register_signed_rendition(
    uow: UnitOfWork, cmd: RegisterSignedRendition
) -> CommandResult:
    """Register the file as the revision's first signed copy. Admin only.

    Raises as ``handle_attach_rendition`` does, and ``RenditionNotAllowedError`` when the file is
    not in the signed slot or the revision already has a signed copy.
    """
    return _register(uow, cmd, replacing=False, signed_command=True)


def handle_replace_signed_rendition(uow: UnitOfWork, cmd: ReplaceSignedRendition) -> CommandResult:
    """Register the file as the signed copy and supersede the current one. Admin only.

    Raises as ``handle_attach_rendition`` does, and ``RenditionNotAllowedError`` when the revision
    has no signed copy to replace.
    """
    return _register(uow, cmd, replacing=True)
