"""The `tl doc` group: register, show, list and change controlled documents (brief 9 M1; T09a).

Each subcommand parses options, makes one call into `tl_mod_documents` (a handler or a read) and
prints. The rules (the number pattern, the code lists, the revision scheme, what a void document
does to its links) live in the module. Documents are named by number; the project comes from
`--project`. Revisions, renditions, links and reports are the groups `tl doc rev`, `tl doc
rendition`, `tl doc link` and `tl doc report`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry
from tl_mod_documents.errors import InvalidDocumentNumberError
from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    SetDocumentConfidentiality,
    SupersedeDocument,
    UpdateDocument,
    VoidDocument,
    handle_register_document,
    handle_set_document_confidentiality,
    handle_supersede_document,
    handle_update_document,
    handle_void_document,
)
from tl_mod_documents.handlers.revisions import CreateRevision, handle_create_revision

from tl_cli.session import require_controller

app = typer.Typer(help="Register, show and change controlled documents.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]

_LINKS_SQL = text(
    "SELECT COUNT(*) AS total, "
    "COALESCE(SUM(CASE WHEN status = 'stale' THEN 1 ELSE 0 END), 0) AS stale "
    "FROM cur_links WHERE to_id = :id AND status IN ('active', 'stale')"
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1.

    A document number the registry pattern refuses prints one `  - <segment>: <message>
    (<level>)` line per problem.
    """
    try:
        yield
    except InvalidDocumentNumberError as exc:
        typer.echo(f"error: {exc}", err=True)
        for issue in exc.issues:
            where = issue["segment"] or "number"
            typer.echo(f"  - {where}: {issue['message']} ({issue['level']})", err=True)
        raise typer.Exit(code=1) from exc
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _document(uow: UnitOfWork, scope: str, project: str, number: str) -> registry.DocumentRow:
    found = registry.find_document(uow.conn(), scope, number)
    if found is None:
        _fail(f"no document {number!r} in project {project!r}")
    return found


def _current_text(row: registry.DocumentRow) -> str:
    """``B IFC construction 2026-10-14``, or ``-`` while no revision is issued."""
    if row.current_revision_code is None:
        return "-"
    parts = [
        row.current_revision_code,
        row.current_revision_status or "-",
        row.current_revision_class or "-",
        row.current_revision_issued_on or "-",
    ]
    return " ".join(parts)


def _revision_line(rev: registry.RevisionRow) -> str:
    current = " current" if rev.is_current else ""
    return (
        f"revision {rev.code} {'Void' if rev.voided else rev.state} {rev.issue_status or '-'} "
        f"{rev.status_class or '-'} {rev.issued_on or '-'}{current}"
    )


@app.command("register")
def register(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number, for example ISO-1234.")],
    project: _Project,
    title: Annotated[str, typer.Option("--title", help="The document title.")],
    doc_type: Annotated[str | None, typer.Option("--type", help="Document type code.")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    originator: Annotated[str | None, typer.Option("--originator")] = None,
    confidentiality: Annotated[str | None, typer.Option("--confidentiality")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    scheme: Annotated[
        str | None, typer.Option("--scheme", help="Revision scheme; default from the scheme file.")
    ] = None,
    first_revision: Annotated[
        bool, typer.Option("--first-revision", help="Also start the first revision, as a draft.")
    ] = False,
    purpose: Annotated[
        str | None, typer.Option("--purpose", help="Purpose of the first revision.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Register a document under its number. The number must fit the registry pattern."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    common: dict[str, Any] = {"actor": actor, "source": "cli", "scope": scope}
    revision: str | None = None
    with _service_errors(), open_uow(db) as uow:
        made = handle_register_document(
            uow,
            RegisterDocument(
                **common,
                number=number,
                title=title,
                description=description,
                doc_type=doc_type,
                discipline=discipline,
                originator=originator,
                confidentiality=confidentiality,
                revision_scheme=scheme,
            ),
        )
        if first_revision:
            started = handle_create_revision(
                uow,
                CreateRevision(
                    **common,
                    document_id=made.stream_id,
                    purpose=purpose,
                    correlation_id=made.events[0].correlation_id,
                ),
            )
            revision = started.key
        row = _document(uow, scope, project, number)
    typer.echo(f"registered {made.stream_id}")
    typer.echo(f"document {row.number}")
    typer.echo(f"state {row.state}")
    typer.echo(f"scheme {row.revision_scheme}")
    if revision is not None:
        typer.echo(f"revision {revision.rsplit('@', 1)[-1]} Draft")


@app.command("show")
def show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
) -> None:
    """Show a document: its register fields, its current revision, its revisions, its links."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = _document(uow, scope, project, number)
        revisions = registry.revisions_of(uow.conn(), row.id)
        links = uow.conn().execute(_LINKS_SQL, {"id": row.id}).one()
        replaced_by = (
            registry.get_document(uow.conn(), row.superseded_by)
            if row.superseded_by is not None
            else None
        )
    typer.echo(f"id: {row.id}")
    typer.echo(f"number: {row.number}")
    typer.echo(f"title: {row.title}")
    typer.echo(f"state: {row.state}")
    typer.echo(f"type: {row.doc_type or '-'}")
    typer.echo(f"discipline: {row.discipline or '-'}")
    typer.echo(f"originator: {row.originator or '-'}")
    typer.echo(f"confidentiality: {row.confidentiality or '-'}")
    typer.echo(f"scheme: {row.revision_scheme}")
    typer.echo(f"pattern: {row.pattern_code or '-'}")
    typer.echo(f"current: {_current_text(row)}")
    typer.echo(f"superseded_by: {replaced_by.number if replaced_by is not None else '-'}")
    typer.echo(f"conformance: {row.conformance}")
    typer.echo(f"version: {row.version}")
    for rev in revisions:
        typer.echo(_revision_line(rev))
    typer.echo(f"links: {int(links.total)} ({int(links.stale)} stale)")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    doc_type: Annotated[str | None, typer.Option("--type")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    include_void: Annotated[bool, typer.Option("--all", help="Include void documents.")] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=5000)] = 1000,
) -> None:
    """List a project's documents by number: number, state, current, type, discipline, title."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        rows = registry.list_documents(
            uow.conn(),
            f"project:{project}",
            doc_type=doc_type,
            discipline=discipline,
            state=state,
            limit=limit,
            include_void=include_void,
        )
    for row in rows:
        current = (
            "-"
            if row.current_revision_code is None
            else f"{row.current_revision_code}({row.current_revision_status})"
        )
        fields = [
            row.number,
            row.state,
            current,
            row.doc_type or "-",
            row.discipline or "-",
            row.title,
        ]
        typer.echo("  ".join(fields))


@app.command("update")
def update(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    title: Annotated[str | None, typer.Option("--title")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    doc_type: Annotated[str | None, typer.Option("--type")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    originator: Annotated[str | None, typer.Option("--originator")] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change a document's title or register fields. An empty value ('') clears a field."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    given: dict[str, str | None] = {
        "title": title,
        "description": description,
        "doc_type": doc_type,
        "discipline": discipline,
        "originator": originator,
    }
    fields: dict[str, Any] = {
        name: (value or None) for name, value in given.items() if value is not None
    }
    if not fields:
        _fail("give at least one field to change (--title, --type, --discipline, ...)")
    with _service_errors(), open_uow(db) as uow:
        row = _document(uow, scope, project, number)
        handle_update_document(
            uow,
            UpdateDocument(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                reason=reason,
                **fields,
            ),
        )
    typer.echo(f"updated {number}")


@app.command("confidentiality")
def confidentiality(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    reason: _Reason,
    value: Annotated[
        str | None,
        typer.Option("--class", help="The new confidentiality class. Omit it with --clear."),
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Remove the class.")] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Set or clear a document's confidentiality class (controller). The reason is kept.

    In Phase 1 the class is recorded but not enforced: every signed-in person and every agent can
    read all documents and transmittals of a project, including recipient emails.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    if (value is None) == (not clear):
        _fail("give the new class with --class, or --clear to remove it")
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        row = _document(uow, scope, project, number)
        handle_set_document_confidentiality(
            uow,
            SetDocumentConfidentiality(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                confidentiality=value,
                reason=reason,
            ),
        )
    typer.echo(f"confidentiality of {number}: {row.confidentiality or '-'} -> {value or '-'}")


@app.command("supersede")
def supersede(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document to replace.")],
    project: _Project,
    by: Annotated[str, typer.Option("--by", help="The number of the document that replaces it.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace a document by another one (controller). Every link to the old one goes stale."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        old = _document(uow, scope, project, number)
        new = _document(uow, scope, project, by)
        handle_supersede_document(
            uow,
            SupersedeDocument(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=old.id,
                superseded_by_id=new.id,
                reason=reason,
            ),
        )
    typer.echo(f"superseded {number} by {by}")


@app.command("void")
def void(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Void a document registered in error (controller). Every link to it goes stale."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        row = _document(uow, scope, project, number)
        handle_void_document(
            uow,
            VoidDocument(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                reason=reason,
            ),
        )
    typer.echo(f"voided {number}")
