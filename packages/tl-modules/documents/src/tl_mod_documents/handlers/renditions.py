"""Rendition commands: register an uploaded file as a rendition of a revision (brief 9 M1).

The file service holds the bytes (``cur_files``). A person uploads a file into one of the four slots
of a revision (``native``, ``pdf``, ``markup``, ``signed``); that upload is only a file until
``AttachRendition`` registers it: the rendition record is the controlled statement that this file
is that revision's copy of that kind. A newer rendition of the same kind supersedes the older one.

What a revision accepts depends on its state, because the content of a revision is frozen once it is
reviewed or issued:

=============  ==========================================
State          Kinds that may be added
=============  ==========================================
Draft          native, pdf, markup
In Review      markup (reviewers' comments on the PDF)
Issued         markup, signed
Superseded     markup, signed
Void           none
=============  ==========================================
"""

from __future__ import annotations

from pydantic import ConfigDict, Field
from tl_core.files.queries import get_file
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, UnknownFileError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_documents import registry
from tl_mod_documents.errors import FileNotAvailableError, RenditionNotAllowedError
from tl_mod_documents.handlers.common import (
    append,
    correlated,
    load_revision,
    open_document,
    require_project,
)
from tl_mod_documents.limits import MAX_NUMBER, MAX_PAGES
from tl_mod_documents.names import (
    RENDITION,
    RENDITION_DEFINED,
    RENDITION_KINDS,
    RENDITION_SUPERSEDED,
)

#: Kinds a revision accepts in each state.
ALLOWED_KINDS: dict[str, tuple[str, ...]] = {
    "Draft": ("native", "pdf", "markup"),
    "In Review": ("markup",),
    "Issued": ("markup", "signed"),
    "Superseded": ("markup", "signed"),
    "Void": (),
}


class AttachRendition(Command):
    """Register an uploaded, scanned file of a revision as a rendition.

    ``file_id`` is a file attached to the revision in the slot named like the rendition kind.
    ``page_count`` is optional (an extractor fills it in later).
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    file_id: str = Field(min_length=1, max_length=MAX_NUMBER)
    page_count: int | None = Field(default=None, ge=0, le=MAX_PAGES)


def handle_attach_rendition(uow: UnitOfWork, cmd: AttachRendition) -> CommandResult:
    """Append ``Record.Created`` and ``Rendition.Defined``; supersede the previous of the kind.

    Raises ``ProjectScopeError``, ``RevisionNotFoundError``, ``DocumentClosedError``,
    ``FileNotAvailableError`` (unknown file, not on this revision, not in a rendition slot, still in
    quarantine or rejected), ``RenditionNotAllowedError`` (the revision's state does not take that
    kind) and ``NoChangesError`` (the file is already a current rendition).
    """
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
    if any(r.file_id == info.file_id and r.is_current for r in existing):
        raise NoChangesError(f"file {info.filename!r} is already the {kind} rendition")
    older = [r for r in existing if r.is_current]
    made = create_module_record(
        uow,
        cmd,
        record_type=RENDITION,
        title=f"{rev.key} {kind}",
        key=f"{rev.key}/{kind}-{len(existing) + 1}",
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
