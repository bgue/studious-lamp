"""Pinned links of documents: `tl doc link|stale|diff|repin`.

A record can be linked to a document floating (it means whatever revision is current) or pinned to
an issued revision. When a later revision is issued, a pinned link goes stale; `tl doc stale` lists
them and `tl doc repin` moves one to another revision after showing what changed between the two
(`tl doc diff` shows the same without moving anything). The rules live in
`tl_mod_documents.resolver`; the commands parse options, make one call and print.
The four functions are registered on the `tl doc` group by `tl_cli.main`.
"""

from __future__ import annotations

from typing import Annotated

import typer
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.queries import get_record
from tl_mod_documents import registry
from tl_mod_documents.resolver import (
    CURRENT,
    LinkToDocument,
    RepinDocumentLink,
    RevisionDiff,
    handle_link_to_document,
    handle_repin_document_link,
    links_to_documents,
    revision_diff,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _document,
    _fail,
    _Project,
    _service_errors,
)
from tl_cli.doc_rev import _Number

_LINK_SQL = text(
    "SELECT l.to_id, l.pin, l.status, x.key AS from_key FROM cur_links l "
    "JOIN cur_core_record x ON x.id = l.from_id "
    "WHERE l.link_id = :id AND l.scope = :scope"
)


def _diff_lines(result: RevisionDiff) -> list[str]:
    """A revision diff as lines: the heading (`ISO-1234: A (IFR) to B (IFC)`), then `- ` facts."""
    return [result.summary[0], *(f"- {line}" for line in result.summary[1:])]


def link(
    ctx: typer.Context,
    from_key: Annotated[str, typer.Argument(help="Key of the record that links, e.g. 47-FV-1001.")],
    number: _Number,
    project: _Project,
    pin: Annotated[
        str | None,
        typer.Option("--pin", help="A revision code, or `current`. Omit to float."),
    ] = None,
    relation: Annotated[str | None, typer.Option("--relation")] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Link a record to a document, floating or pinned to an issued revision."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` doc = _document(uow, scope, project,
    #    number); source = get_record(uow, scope, from_key); if source is None, _fail(f"no record
    #    with key {from_key!r} in project {project!r}").
    # 3. fields = {"actor": actor, "source": "cli", "scope": scope, "from_id": source["id"],
    #    "document_id": doc.id, "pin": pin, "note": note}; add "relation": relation only when it
    #    is not None (the command has a default). made = handle_link_to_document(uow,
    #    LinkToDocument(**fields)).
    # 4. Print `linked <from_key> to <number> pinned <resolved pin>` or `... floating`, then
    #    `link <made.stream_id>`. The resolved pin is the stored one: read it with the SQL
    #    `SELECT pin FROM cur_links WHERE link_id = :id` (made.stream_id) in the same unit of work
    #    (`current` becomes the revision code).
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        doc = _document(uow, scope, project, number)
        source = get_record(uow, scope, from_key)
        if source is None:
            _fail(f"no record with key {from_key!r} in project {project!r}")
        fields: dict[str, object] = {
            "actor": actor,
            "source": "cli",
            "scope": scope,
            "from_id": source["id"],
            "document_id": doc.id,
            "pin": pin,
            "note": note,
        }
        if relation is not None:
            fields["relation"] = relation
        made = handle_link_to_document(uow, LinkToDocument.model_validate(fields))
        stored = (
            uow.conn()
            .execute(text("SELECT pin FROM cur_links WHERE link_id = :id"), {"id": made.stream_id})
            .scalar_one()
        )
    how = f"pinned {stored}" if stored else "floating"
    typer.echo(f"linked {from_key} to {number} {how}")
    typer.echo(f"link {made.stream_id}")


def stale(
    ctx: typer.Context,
    project: _Project,
    number: Annotated[
        str | None, typer.Option("--document", help="Only the links to this document.")
    ] = None,
) -> None:
    """List links that are stale: the record, the document, its pin, what is current now, the id."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` doc_id = None, or
    #    _document(uow, scope, project, number).id when --document is given; found =
    #    links_to_documents(uow.conn(), scope, document_id=doc_id, only_stale=True).
    # 3. For each PinnedLink print, joined by two spaces: from_key or "-", "->", document_number,
    #    f"pin {pin or '-'}", f"current {resolution.current_code or '-'}", link_id.
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        doc_id = _document(uow, scope, project, number).id if number is not None else None
        found = links_to_documents(uow.conn(), scope, document_id=doc_id, only_stale=True)
    for item in found:
        fields = [
            item.from_key or "-",
            "->",
            item.document_number,
            f"pin {item.pin or '-'}",
            f"current {item.resolution.current_code or '-'}",
            item.link_id,
        ]
        typer.echo("  ".join(fields))


def diff(
    ctx: typer.Context,
    number: _Number,
    from_code: Annotated[str, typer.Argument(metavar="FROM", help="The earlier revision code.")],
    to_code: Annotated[str, typer.Argument(metavar="TO", help="The later revision code.")],
    project: _Project,
) -> None:
    """Show what changed between two issued revisions of a document, without changing anything."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` doc = _document(uow, scope,
    #    project, number); result = revision_diff(uow.conn(), doc.id, from_code, to_code).
    # 3. Print the lines of _diff_lines(result) (the helper is final).
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        doc = _document(uow, scope, project, number)
        result = revision_diff(uow.conn(), doc.id, from_code, to_code)
    for line in _diff_lines(result):
        typer.echo(line)


def repin(
    ctx: typer.Context,
    link_id: Annotated[str, typer.Argument(help="The link id (from `tl doc stale`).")],
    project: _Project,
    pin: Annotated[str, typer.Option("--pin", help="A revision code, or `current`.")] = CURRENT,
    apply: Annotated[bool, typer.Option("--apply", help="Confirm and move the pin.")] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Show what changed between the pinned revision and another; with --apply, move the pin."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=not apply) as uow:` row =
    #    uow.conn().execute(_LINK_SQL, {"id": link_id, "scope": scope}).first(); if it is None,
    #    _fail(f"no link {link_id!r} in project {project!r}"). doc = registry.get_document(
    #    uow.conn(), row.to_id); if doc is None, _fail("this link does not point to a document").
    #    If row.pin is None, _fail("this link floats; it has no pin to move").
    # 3. target = doc.current_revision_code when pin == CURRENT, else pin. If target is None,
    #    _fail(f"{doc.number} has no issued revision"). result = revision_diff(uow.conn(), doc.id,
    #    row.pin, target) and print the lines of _diff_lines(result).
    # 4. Without --apply print `not re-pinned; run again with --apply to confirm` and stop.
    # 5. With --apply: handle_repin_document_link(uow, RepinDocumentLink(actor=actor,
    #    source="cli", scope=scope, link_id=link_id, pin=target)) and print
    #    `re-pinned <link_id> to <target>`.
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=not apply) as uow:
        row = uow.conn().execute(_LINK_SQL, {"id": link_id, "scope": scope}).first()
        if row is None:
            _fail(f"no link {link_id!r} in project {project!r}")
        doc = registry.get_document(uow.conn(), row.to_id)
        if doc is None:
            _fail("this link does not point to a document")
        if row.pin is None:
            _fail("this link floats; it has no pin to move")
        target = doc.current_revision_code if pin == CURRENT else pin
        if target is None:
            _fail(f"{doc.number} has no issued revision")
        result = revision_diff(uow.conn(), doc.id, row.pin, target)
        for line in _diff_lines(result):
            typer.echo(line)
        if not apply:
            typer.echo("not re-pinned; run again with --apply to confirm")
            return
        handle_repin_document_link(
            uow,
            RepinDocumentLink(actor=actor, source="cli", scope=scope, link_id=link_id, pin=target),
        )
    typer.echo(f"re-pinned {link_id} to {target}")
