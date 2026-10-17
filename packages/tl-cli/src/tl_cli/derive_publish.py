"""`tl derive publish` and `tl derive compensate`: create records from a valid derived document
and take them back (P1-I3-T14d; ADR-0014 sections 5 and 6).

Both preview by default and write only with `--apply`. Publishing into tags needs the admin role,
into documents the document controller (or admin) role; compensating needs admin. A publication
creates records and never changes existing ones. The rules are the module's
(`tl_mod_documents.derivation.publish`); these commands parse options and print.

STUB (P1-I3-T14d): the bodies of compensate, publish raise NotImplementedError; their
signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the lint-silencing lines.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
# pyright: reportUnusedImport=false, reportUnusedVariable=false

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
    # STEPS (P1-I3-T14d)
    # 1. db = ctx.obj; scope = f"project:{project}"; configure_files().
    # 2. Readonly block: found = views.find_derived(...); plan = views.publish_preview(uow,
    #    scope, ref).
    # 3. Print the header, the counts line, one line per row (at most `limit`: `+ key` create, `=
    #    key exists|differs`, `! row n key: problems`), `... n more rows not shown` when cut,
    #    then `problem: <p>` per plan.problems (exact formats in the docstring).
    # 4. Without --apply: if plan.can_publish or plan.needs_skip_existing print `dry run: nothing
    #    written; add --apply to publish` plus ` (add --skip-existing)` when
    #    plan.needs_skip_existing and not skip_existing, and return; otherwise print `cannot
    #    publish` and raise typer.Exit(code=1).
    # 5. With --apply: if plan.target is None fail(...); require_admin(db) for tags (TARGET_TAGS)
    #    else require_controller(db).
    # 6. Inside `with service_errors(), open_uow(db) as uow:` call
    #    handle_publish_derived_tags(uow, PublishDerivedTags(**fields)) or
    #    handle_publish_derived_documents(uow, PublishDerivedDocuments(**fields)); fields = actor
    #    (acting), source, scope, derived_id=found.id, expected_content_rev=rev or
    #    plan.content_rev, skip_existing.
    # 7. Read the derived document again (views.derived_view) and print `published
    #    <published_count> records from <key>` and `correlation <published_correlation_id>`.
    raise NotImplementedError


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
    # STEPS (P1-I3-T14d)
    # 1. db = ctx.obj; scope = f"project:{project}"; configure_files().
    # 2. Readonly block: found = views.find_derived(...); plan = views.compensation_preview(uow,
    #    scope, ref).
    # 3. Print `compensate <key> correlation <id or ->`, then per item `<action> <key or
    #    record_id>  <state or ->  reversible|blocked: <problem>` (state through cell), then
    #    `problem: <p>` per plan.problems.
    # 4. Without --apply: if plan.can_compensate print `dry run: nothing written; add --apply to
    #    roll back` and return; otherwise print `cannot compensate` and raise typer.Exit(code=1).
    # 5. With --apply: require_admin(db); inside `with service_errors(), open_uow(db) as uow:`
    #    handle_compensate_publication(uow, CompensatePublication(actor=acting(db, actor),
    #    source=SOURCE, scope=scope, derived_id=found.id, reason=reason)).
    # 6. Print `compensated <n> records of <key>` where n counts the plan items whose action is
    #    not `retract_link`.
    raise NotImplementedError
