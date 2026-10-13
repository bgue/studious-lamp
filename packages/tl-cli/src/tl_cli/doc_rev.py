"""The `tl doc rev` group: start, issue, supersede, void and list the revisions of a document.

Each subcommand parses options, makes one call into `tl_mod_documents` (a handler or a read) and
prints. The rules (the revision scheme, one open revision, the status classes, stale pins, dates)
live in the module. A revision is named by its document number and its code (`ISO-1234 A`); the
project comes from `--project`. Issuing and superseding a revision are a controller's acts
(ADR-0013).
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry
from tl_mod_documents.handlers.revisions import (
    CreateRevision,
    IssueRevision,
    SupersedeRevision,
    VoidRevision,
    handle_create_revision,
    handle_issue_revision,
    handle_supersede_revision,
    handle_void_revision,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _document,
    _fail,
    _Project,
    _Reason,
    _revision_line,
    _service_errors,
)
from tl_cli.session import require_controller

app = typer.Typer(help="Start, issue, supersede, void and list revisions.", no_args_is_help=True)

_Number = Annotated[str, typer.Argument(help="The document number, for example ISO-1234.")]
_Code = Annotated[str, typer.Argument(help="The revision code, for example A.")]


def _revision(
    uow: UnitOfWork, scope: str, project: str, number: str, code: str
) -> registry.RevisionRow:
    """The revision ``code`` of document ``number``; exits `error: no revision 'X' of N`."""
    doc = _document(uow, scope, project, number)
    found = registry.find_revision(uow.conn(), doc.id, code)
    if found is None:
        _fail(f"no revision {code!r} of {number}")
    return found


@app.command("create")
def create(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    code: Annotated[str | None, typer.Option("--code", help="Default: the next code.")] = None,
    stage: Annotated[str | None, typer.Option("--stage", help="For a staged scheme.")] = None,
    purpose: Annotated[str | None, typer.Option("--purpose")] = None,
    change_note: Annotated[str | None, typer.Option("--change-note")] = None,
    intended_status: Annotated[str | None, typer.Option("--intended-status")] = None,
    revision_date: Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Start the next revision of a document, as a draft. Prints `created revision <code> Draft`."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _document(uow, scope, project, number)
        made = handle_create_revision(
            uow,
            CreateRevision(
                actor=actor,
                source="cli",
                scope=scope,
                document_id=row.id,
                code=code,
                stage=stage,
                purpose=purpose,
                change_note=change_note,
                revision_date=revision_date,
                intended_status=intended_status,
            ),
        )
    made_code = (made.key or "").rsplit("@", 1)[-1]
    typer.echo(f"created revision {made_code} Draft")


@app.command("issue")
def issue(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    status: Annotated[str, typer.Option("--status", help="Issue status, for example IFR.")],
    issued_on: Annotated[
        str | None, typer.Option("--date", help="YYYY-MM-DD. Default today; never in the future.")
    ] = None,
    date_reason: Annotated[
        str | None, typer.Option("--date-reason", help="Required for a date before today.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Issue a draft revision (controller). Links pinned to other revisions go stale."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        rev = _revision(uow, scope, project, number, code)
        result = handle_issue_revision(
            uow,
            IssueRevision(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=rev.id,
                issue_status=status,
                issued_on=issued_on,
                date_reason=date_reason,
            ),
        )
        issued = _revision(uow, scope, project, number, code)
    flagged = sum(1 for event in result.events if event.event_type == "Link.Flagged")
    typer.echo(f"issued {number}@{code} as {status} on {issued.issued_on}")
    if flagged > 0:
        noun = "link" if flagged == 1 else "links"
        typer.echo(f"flagged {flagged} {noun} stale")


@app.command("supersede")
def supersede(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    by: Annotated[str, typer.Option("--by", help="The code of the revision that replaces it.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Mark an issued revision as replaced by another issued one (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        old = _revision(uow, scope, project, number, code)
        new = _revision(uow, scope, project, number, by)
        handle_supersede_revision(
            uow,
            SupersedeRevision(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=old.id,
                superseded_by_id=new.id,
                reason=reason,
            ),
        )
    typer.echo(f"superseded {number}@{code} by {by}")


@app.command("void")
def void(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Void a draft revision started in error. An issued revision is superseded, never voided."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        rev = _revision(uow, scope, project, number, code)
        handle_void_revision(
            uow,
            VoidRevision(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=rev.id,
                reason=reason,
            ),
        )
    typer.echo(f"voided {number}@{code}")


@app.command("ls")
def ls(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """List the revisions of a document, oldest first, one `revision ...` line each."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = _document(uow, scope, project, number)
        revisions = registry.revisions_of(uow.conn(), row.id)
    for rev in revisions:
        typer.echo(_revision_line(rev))
