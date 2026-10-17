"""`tl derive show|report|rows|diff|check|validate`: look at a derived document (P1-I3-T14c).

All but `validate` read and write nothing. `check` validates the stored rows against a schema now
and stores nothing; `validate` queues a job that does it and keeps the report. The reads are the
module's (`tl_mod_documents.derivation.views`); these commands parse options and print.

STUB (P1-I3-T14c): the bodies of check, diff, report, rows_command, show, validate raise
NotImplementedError; their signatures, options, docstrings and the helpers are final. Each body
has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the
lint-silencing lines.
"""

# ruff: noqa: F401, F841 -- STUB: these imports are used once the bodies are written
# pyright: reportUnusedImport=false, reportUnusedVariable=false

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.derived import ValidateDerived, handle_validate_derived
from tl_mod_documents.derivation.validation import ValidationReport

from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    configure_files,
    fail,
    service_errors,
)

app = typer.Typer(
    help="Show, report, diff and re-validate derived documents.", no_args_is_help=True
)

_Ref = Annotated[str, typer.Argument(help="A derived document's key or id.")]
_Rev = Annotated[int | None, typer.Option("--rev", min=1, help="A pass (default: the latest).")]


def _print_report(label: str, key: str, rev: int, report: ValidationReport, limit: int) -> None:
    """The header lines, then one line per listed issue (at most ``limit``).

    ``<label> <key> pass <rev> against <code>@<version>: <status>``, then
    ``rows checked <n>  with errors <n>  errors <n>  warnings <n>``, then
    ``<level> row <n or -> column <name or -> <code>: <message>`` per issue, and
    ``... <k> more issues not shown`` when some are cut.
    """
    typer.echo(
        f"{label} {key} pass {rev} against {report.schema_code}@{report.schema_version}: "
        f"{report.status}"
    )
    typer.echo(
        f"rows checked {report.rows_checked}  with errors {report.rows_with_errors}  "
        f"errors {report.error_count}  warnings {report.warning_count}"
    )
    for issue in report.issues[:limit]:
        typer.echo(
            f"{issue.level} row {issue.row if issue.row is not None else '-'} "
            f"column {issue.column or '-'} {issue.code}: {issue.message}"
        )
    hidden = len(report.issues) - limit
    if hidden > 0 or report.truncated:
        typer.echo(f"... {max(hidden, 0)} more issues not shown")


@app.command("show")
def show(ctx: typer.Context, ref: _Ref, project: Project) -> None:
    """Show a derived document, its passes and its running job.

    Lines: `derived <key>`, `state <state>`, `source <ref>`, `schema <code>@<version>`,
    `method <m>`, `published <n> records at <time>` (or `published -`), `job <key> <state>` when
    one is queued or running, then `pass <n>  <extractor>  <extraction status>  rows <n>
    validation <status>  errors <n>` for each pass, oldest first.
    """
    # STEPS (P1-I3-T14c)
    # 1. db = ctx.obj; inside `with service_errors(), open_uow(db, readonly=True) as uow:` d =
    #    views.derived_view(uow.conn(), f"project:{project}", ref).
    # 2. Print the lines in the docstring's order: derived, state, source, schema, method,
    #    `published <n> records at <time>` or `published -`, `job <key> <state>` only when
    #    d.active_job is set.
    # 3. Then one `pass <n>  <extractor>  <extraction_status>  rows <n>  validation <status>
    #    errors <n>` line per d.contents (two spaces between the first fields, as written).
    raise NotImplementedError


@app.command("report")
def report(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    rev: _Rev = None,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Issues to print.")] = 50,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit 1 unless the pass is valid.")
    ] = False,
) -> None:
    """Print the stored validation report of a pass (the latest by default)."""
    # STEPS (P1-I3-T14c)
    # 1. db = ctx.obj; scope = f"project:{project}"; configure_files().
    # 2. Inside `with service_errors(), open_uow(db, readonly=True) as uow:` found =
    #    views.find_derived(uow.conn(), scope, ref); made = views.derived_report(uow, scope, ref,
    #    content_rev=rev).
    # 3. _print_report("report", found.key, rev or found.content_rev, made, limit); with --strict
    #    and made.status != "valid" raise typer.Exit(code=1).
    raise NotImplementedError


@app.command("rows")
def rows_command(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    rev: _Rev = None,
    offset: Annotated[int, typer.Option("--offset", min=0, help="Rows to skip.")] = 0,
    limit: Annotated[int, typer.Option("--limit", min=1, max=500, help="Rows to print.")] = 20,
) -> None:
    """Print rows of a pass as extracted (all text).

    `columns <name> <name> ...`, then `<row number>  <cell> | <cell> | ...` (`-` for an empty
    cell), then `showing <first>-<last> of <total>`.
    """
    # STEPS (P1-I3-T14c)
    # 1. db = ctx.obj; configure_files(); page = views.derived_rows(uow, f"project:{project}",
    #    ref, content_rev=rev, offset=offset, limit=limit) inside the usual readonly block.
    # 2. Print `columns <names joined by one space>`.
    # 3. For each row, numbered from page.offset + 1, print `<n>  ` plus the cells joined by ` |
    #    `, each through cell(row.get(c), 30).
    # 4. Print `showing <first>-<last> of <total>` where first is page.offset + 1 (0 when no
    #    rows) and last is page.offset + len(page.rows).
    raise NotImplementedError


@app.command("diff")
def diff(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    against: Annotated[
        str, typer.Option("--against", help="previous_pass or previous_revision.")
    ] = "previous_pass",
    rev: _Rev = None,
) -> None:
    """Compare a pass with the pass before it, or with the previous revision's data.

    `added <n>  removed <n>  changed <n>  unchanged <n>`, then `+ <key>` per added row, `- <key>`
    per removed row and `~ <key>: <column> <old> -> <new>; ...` per changed row.
    """
    # STEPS (P1-I3-T14c)
    # 1. If against is not previous_pass or previous_revision: fail("--against must be
    #    previous_pass or previous_revision").
    # 2. configure_files(); d = views.derived_diff(uow, f"project:{project}", ref,
    #    against=against, content_rev=rev) inside the usual readonly block.
    # 3. Print `added <n>  removed <n>  changed <n>  unchanged <n>` (the four counts), then `+
    #    <key>` per added, `- <key>` per removed, `~ <key>: <column> <old> -> <new>; ...` per
    #    changed row (old and new through cell).
    raise NotImplementedError


@app.command("check")
def check(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    schema: Annotated[
        str | None, typer.Option("--schema", help="code or code@version (default: its own).")
    ] = None,
    rev: _Rev = None,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Issues to print.")] = 50,
    strict: Annotated[bool, typer.Option("--strict", help="Exit 1 unless the rows pass.")] = False,
) -> None:
    """Check the stored rows against a schema now. Nothing is stored and no job runs."""
    # STEPS (P1-I3-T14c)
    # 1. As report, but made = views.validate_stored(uow, scope, ref, schema_ref=schema,
    #    content_rev=rev) and the label is "check". `validate_stored` runs the JSON Schema in the
    #    resource envelope (a child process); never import or call `jsonschema` here.
    # 2. _print_report("check", found.key, rev or found.content_rev, made, limit); with --strict
    #    and made.status != "valid" raise typer.Exit(code=1).
    raise NotImplementedError


@app.command("validate")
def validate(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    rev: _Rev = None,
    schema_version: Annotated[
        str | None, typer.Option("--schema-version", help="Another version of its schema.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Queue a job that validates a pass again and keeps the report. `queued <job> for <key>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)  # final: the actor is checked before anything is read or written
    # STEPS (P1-I3-T14c)
    # 1. scope = f"project:{project}" (db and `who` are set above).
    # 2. Inside `with service_errors(), open_uow(db) as uow:` found =
    #    views.find_derived(uow.conn(), scope, ref); made = handle_validate_derived(uow,
    #    ValidateDerived(actor=who, source=SOURCE, scope=scope,
    #    derived_id=found.id, content_rev=rev, schema_semver=schema_version)).
    # 3. Print `queued <made.key> for <found.key>`.
    raise NotImplementedError
