"""`tl derive publish` and `tl derive compensate`: create records from a valid derived document
and take them back (P1-I3-T14d; ADR-0014 sections 5 and 6).

Both preview by default and write only with `--apply`. Publishing into tags needs the admin role,
into documents the document controller (or admin) role; compensating needs admin. A publication
creates records and never changes existing ones. The rules are the module's
(`tl_mod_documents.derivation.publish`); these commands parse options and print.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    PublishDerivedDocuments,
    PublishDerivedTags,
    handle_compensate_publication,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
)
from tl_mod_documents.names import TARGET_TAGS

from tl_cli.derive_support import (
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    configure_files,
    fail,
    service_errors,
)
from tl_cli.session import require_admin, require_controller

app = typer.Typer(help="Publish a valid derived document, or compensate.", no_args_is_help=True)

_Ref = Annotated[str, typer.Argument(help="A derived document's key or id.")]


@app.command("publish")
def publish(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply", help="Create the records (admin for tags, controller for documents)."
        ),
    ] = False,
    rev: Annotated[int | None, typer.Option("--rev", min=1, help="The pass you looked at.")] = None,
    skip_existing: Annotated[
        bool, typer.Option("--skip-existing", help="Leave rows whose key exists alone.")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Rows to list.")] = 40,
    actor: Actor = None,
) -> None:
    """Show what publishing would do; with --apply, do it as one correlated import.

    Preview lines: `publish <key> pass <n> to <tags|documents> (<schema>)`, `create <n>  exists <n>
    differs <n>  invalid <n>`, then `+ <key>` per row to create, `= <key> exists` or
    `= <key> differs` per existing row, `! row <n> <key>: <problems>` per invalid row and
    `problem: <reason>` for what stops the whole publication. Without --apply the last line is
    `dry run: nothing written; add --apply to publish` (or `cannot publish`, exit 1). With --apply
    it prints `published <n> records from <key>` and the import's correlation id.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    configure_files()
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.find_derived(uow.conn(), scope, ref)
        plan = views.publish_preview(uow, scope, ref)
    typer.echo(
        f"publish {found.key} pass {plan.content_rev} to {plan.target or '-'} "
        f"({plan.schema_key or '-'})"
    )
    counts = plan.counts
    typer.echo(
        f"create {counts.get('create', 0)}  exists {counts.get('exists', 0)}  "
        f"differs {counts.get('differs', 0)}  invalid {counts.get('invalid', 0)}"
    )
    for row in plan.rows[:limit]:
        if row.action == "create":
            typer.echo(f"+ {row.key}")
        elif row.action in ("exists", "differs"):
            typer.echo(f"= {row.key} {row.action}")
        else:
            typer.echo(f"! row {row.row} {row.key or '-'}: {'; '.join(row.problems)}")
    if len(plan.rows) > limit:
        typer.echo(f"... {len(plan.rows) - limit} more rows not shown")
    for problem in plan.problems:
        typer.echo(f"problem: {problem}")
    if not apply:
        if plan.can_publish or plan.needs_skip_existing:
            hint = (
                " (add --skip-existing)" if plan.needs_skip_existing and not skip_existing else ""
            )
            typer.echo(f"dry run: nothing written; add --apply to publish{hint}")
            return
        typer.echo("cannot publish")
        raise typer.Exit(code=1)
    if plan.target is None:
        fail(f"{found.key}: its schema has no publish mapping")
    if plan.target == TARGET_TAGS:
        require_admin(db)  # a bulk creation of tags is an admin's decision (ADR-0014)
    else:
        require_controller(db)
    fields = {
        "actor": acting(db, actor),
        "source": SOURCE,
        "scope": scope,
        "derived_id": found.id,
        "expected_content_rev": rev or plan.content_rev,
        "skip_existing": skip_existing,
    }
    with service_errors(), open_uow(db) as uow:
        if plan.target == TARGET_TAGS:
            handle_publish_derived_tags(uow, PublishDerivedTags(**fields))
        else:
            handle_publish_derived_documents(uow, PublishDerivedDocuments(**fields))
    with open_uow(db, readonly=True) as uow:
        after = views.derived_view(uow.conn(), scope, found.id)
    typer.echo(f"published {after.published_count} records from {found.key}")
    typer.echo(f"correlation {after.published_correlation_id}")


@app.command("compensate")
def compensate(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why (kept in the history).")],
    apply: Annotated[
        bool, typer.Option("--apply", help="Roll the publication back (admin).")
    ] = False,
    actor: Actor = None,
) -> None:
    """Show what rolling back the publication in force would end; with --apply, do it.

    Lines: `compensate <key> correlation <id>`, then `<action> <record key or id>  <state>
    reversible` or `blocked: <problem>` per record, then `problem: <reason>` lines. All or nothing:
    one record that cannot be reversed stops it. Prints `compensated <n> records of <key>`.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    configure_files()
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.find_derived(uow.conn(), scope, ref)
        plan = views.compensation_preview(uow, scope, ref)
    typer.echo(f"compensate {found.key} correlation {plan.import_correlation_id or '-'}")
    for item in plan.items:
        state = "reversible" if item.reversible else f"blocked: {item.problem}"
        typer.echo(f"{item.action} {item.key or item.record_id}  {cell(item.state)}  {state}")
    for problem in plan.problems:
        typer.echo(f"problem: {problem}")
    if not apply:
        if plan.can_compensate:
            typer.echo("dry run: nothing written; add --apply to roll back")
            return
        typer.echo("cannot compensate")
        raise typer.Exit(code=1)
    require_admin(db)
    with service_errors(), open_uow(db) as uow:
        handle_compensate_publication(
            uow,
            CompensatePublication(
                actor=acting(db, actor),
                source=SOURCE,
                scope=scope,
                derived_id=found.id,
                reason=reason,
            ),
        )
    typer.echo(
        f"compensated {len([i for i in plan.items if i.action != 'retract_link'])} records of "
        f"{found.key}"
    )
