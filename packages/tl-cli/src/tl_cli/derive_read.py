"""`tl derive show|report|rows|diff|check|validate`: look at a derived document (P1-I3-T14c).

All but `validate` read and write nothing. `check` validates the stored rows against a schema now
and stores nothing; `validate` queues a job that does it and keeps the report. The reads are the
module's (`tl_mod_documents.derivation.views`); these commands parse options and print.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.derived import ValidateDerived, handle_validate_derived
from tl_mod_documents.derivation.validation import ValidationReport

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
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.derived_view(uow.conn(), f"project:{project}", ref)
    typer.echo(f"derived {d.key}")
    typer.echo(f"state {d.state}")
    typer.echo(f"source {d.source_ref}")
    typer.echo(f"schema {d.schema_code}@{d.schema_version}")
    typer.echo(f"method {d.method}")
    if d.published_count is None:
        typer.echo("published -")
    else:
        typer.echo(f"published {d.published_count} records at {d.published_at}")
    if d.active_job is not None:
        typer.echo(f"job {d.active_job.key} {d.active_job.state}")
    for c in d.contents:
        typer.echo(
            f"pass {c.content_rev}  {c.extractor}  {c.extraction_status}  rows {c.row_count}  "
            f"validation {c.validation_status}  errors {c.error_count}"
        )


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
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    configure_files()
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.find_derived(uow.conn(), scope, ref)
        made = views.derived_report(uow, scope, ref, content_rev=rev)
    _print_report("report", found.key, rev or found.content_rev, made, limit)
    if strict and made.status != "valid":
        raise typer.Exit(code=1)


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
    db: DbTarget = ctx.obj
    configure_files()
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = views.derived_rows(
            uow, f"project:{project}", ref, content_rev=rev, offset=offset, limit=limit
        )
    typer.echo("columns " + " ".join(page.columns))
    for index, row in enumerate(page.rows, start=page.offset + 1):
        typer.echo(f"{index}  " + " | ".join(cell(row.get(c), 30) for c in page.columns))
    last = page.offset + len(page.rows)
    typer.echo(f"showing {page.offset + 1 if page.rows else 0}-{last} of {page.total}")


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
    db: DbTarget = ctx.obj
    if against not in ("previous_pass", "previous_revision"):
        fail("--against must be previous_pass or previous_revision")
    configure_files()
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.derived_diff(uow, f"project:{project}", ref, against=against, content_rev=rev)
    typer.echo(
        f"added {d.added_count}  removed {d.removed_count}  changed {d.changed_count}  "
        f"unchanged {d.unchanged_count}"
    )
    for key in d.added:
        typer.echo(f"+ {key}")
    for key in d.removed:
        typer.echo(f"- {key}")
    for change in d.changed:
        fields = "; ".join(f"{f.column} {cell(f.old)} -> {cell(f.new)}" for f in change.fields)
        typer.echo(f"~ {change.key}: {fields}")


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
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    configure_files()
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.find_derived(uow.conn(), scope, ref)
        made = views.validate_stored(uow, scope, ref, schema_ref=schema, content_rev=rev)
    _print_report("check", found.key, rev or found.content_rev, made, limit)
    if strict and made.status != "valid":
        raise typer.Exit(code=1)


@app.command("validate")
def validate(
    ctx: typer.Context,
    ref: _Ref,
    project: Project,
    rev: _Rev = None,
    schema_version: Annotated[
        str | None, typer.Option("--schema-version", help="Another version of its schema.")
    ] = None,
    actor: Actor = None,
) -> None:
    """Queue a job that validates a pass again and keeps the report. `queued <job> for <key>`."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with service_errors(), open_uow(db) as uow:
        found = views.find_derived(uow.conn(), scope, ref)
        made = handle_validate_derived(
            uow,
            ValidateDerived(
                actor=acting(db, actor),
                source=SOURCE,
                scope=scope,
                derived_id=found.id,
                content_rev=rev,
                schema_semver=schema_version,
            ),
        )
    typer.echo(f"queued {made.key} for {found.key}")
