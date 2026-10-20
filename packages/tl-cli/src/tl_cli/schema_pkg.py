"""`tl schema package ls|show|draft|revise|analyse|submit|changes|approve`: the review path (P1-I8).

A package version is drafted from a YAML file, analysed (classification and impact reports),
submitted to review, then sent back or approved by an administrator. Publishing, adopting,
waivers, the diff against git, the test on a sample and the rest are in the commands of
`tl_cli.schema_ops`. The rules are the module's (`tl_mod_schemareg`, FANOUT D2 and D4); these
commands parse options, make one call and print.

Who may: drafting, revising, analysing and submitting are any signed-in person (the module binds
them to the actor that drafted the package); sending a package back and approving it are the
administrator's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import CommandResult
from tl_mod_schemareg import views
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DraftSchemaPackage,
    RequestSchemaChanges,
    ReviseSchemaPackage,
    SubmitSchemaPackage,
    handle_analyse_schema_package,
    handle_approve_schema_package,
    handle_draft_schema_package,
    handle_request_schema_changes,
    handle_revise_schema_package,
    handle_submit_schema_package,
)
from tl_mod_schemareg.limits import MAX_CONTENT_BYTES

from tl_cli import schema_pkg_read
from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, acting, cell, fail, service_errors
from tl_cli.session import require_admin, require_session

app = typer.Typer(help="Draft, review and read schema package versions.", no_args_is_help=True)
schema_pkg_read.register(app)

_Ref = Annotated[str, typer.Argument(help="A package id or name@version, for example acme@1.1.0.")]
_File = Annotated[
    Path, typer.Argument(help="The package YAML.", exists=True, dir_okay=False, readable=True)
]
_Changelog = Annotated[
    str | None, typer.Option("--changelog", help="What this version changes, for the reviewer.")
]


def _read(path: Path) -> str:
    if path.stat().st_size > MAX_CONTENT_BYTES:
        fail(f"{path.name} is larger than {MAX_CONTENT_BYTES} bytes")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        fail(f"{path.name} is not UTF-8 text")


def _package_id(db: DbTarget, ref: str) -> str:
    with service_errors(), open_uow(db, readonly=True) as uow:
        return views.package_detail(uow.conn(), ref).id


def _report(label: str, made: CommandResult, key: str) -> None:
    typer.echo(f"{label} {key} {made.stream_id}")


@app.command("ls")
def ls(
    ctx: typer.Context,
    scope: Annotated[str | None, typer.Option("--scope", help="company or project:<id>.")] = None,
    state: Annotated[str | None, typer.Option("--state", help="For example Published.")] = None,
    name: Annotated[str | None, typer.Option("--package", help="One package name.")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 100,
) -> None:
    """List package versions, highest first: key, scope, state, class, whether analysed."""
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        rows = views.package_summaries(
            uow.conn(), scope=scope, state=state, package=name, limit=limit
        )
    for row in rows:
        typer.echo(
            "  ".join(
                [
                    row.key,
                    row.scope,
                    row.state,
                    cell(row.worst_class),
                    "analysed" if row.analysed else "not-analysed",
                    cell(row.title),
                ]
            )
        )


@app.command("show")
def show(
    ctx: typer.Context,
    ref: _Ref,
    diff: Annotated[
        bool, typer.Option("--diff", help="Print the text diff against the base.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="The whole detail as JSON.")] = False,
) -> None:
    """One package version: state, reports and lint (`--diff` the change, `--json` everything)."""
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        detail = views.package_detail(uow.conn(), ref)
    if as_json:
        typer.echo(detail.model_dump_json(indent=2))
        return
    typer.echo(f"package {detail.key}")
    typer.echo(f"id {detail.id}")
    typer.echo(f"scope {detail.scope}")
    typer.echo(f"state {detail.state}")
    typer.echo(f"drafted by {detail.drafted_by}")
    if detail.submitted_by:
        typer.echo(f"submitted by {detail.submitted_by}")
    if detail.approved_by:
        typer.echo(f"approved by {detail.approved_by}")
    typer.echo(f"base {detail.base_ref or '-'}")
    typer.echo(f"class {detail.worst_class or '-'}  ({'current' if detail.analysed else 'stale'})")
    if detail.classification is not None:
        for change in detail.classification.changes[:50]:
            typer.echo(f"  change {change.cls} {change.path}: {change.detail}")
    if detail.impact is not None:
        typer.echo(f"impact {detail.impact_sha256 or '-'} entries {len(detail.impact.entries)}")
    for issue in detail.lint[:50]:
        typer.echo(f"  lint {issue.severity} {issue.rule} {issue.path}: {issue.message}")
    if diff:
        typer.echo(detail.diff.rstrip("\n") if detail.diff else "(no base to compare with)")
        if detail.diff_truncated:
            typer.echo("(diff cut)")


@app.command("draft")
def draft(
    ctx: typer.Context, path: _File, changelog: _Changelog = None, actor: Actor = DEV_ACTOR
) -> None:
    """Draft a package version from its YAML. Prints `drafted <name@version> <id>`."""
    db: DbTarget = ctx.obj
    require_session(db)
    content = _read(path)
    with service_errors(), open_uow(db) as uow:
        made = handle_draft_schema_package(
            uow,
            DraftSchemaPackage(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                content=content,
                changelog=changelog,
            ),
        )
    _report("drafted", made, made.key or "-")


@app.command("revise")
def revise(
    ctx: typer.Context,
    ref: _Ref,
    path: _File,
    changelog: _Changelog = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Replace the content of your draft. Prints `revised <name@version> <id>`."""
    db: DbTarget = ctx.obj
    require_session(db)
    package_id = _package_id(db, ref)
    content = _read(path)
    with service_errors(), open_uow(db) as uow:
        made = handle_revise_schema_package(
            uow,
            ReviseSchemaPackage(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                package_id=package_id,
                content=content,
                changelog=changelog,
            ),
        )
    _report("revised", made, ref)


@app.command("analyse")
def analyse(ctx: typer.Context, ref: _Ref, actor: Actor = DEV_ACTOR) -> None:
    """Make the classification and impact reports of your draft.

    Prints `analysed <name@version> <class>`.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    package_id = _package_id(db, ref)
    with service_errors(), open_uow(db) as uow:
        handle_analyse_schema_package(
            uow,
            AnalyseSchemaPackage(
                actor=acting(db, actor), source=SOURCE, scope="company", package_id=package_id
            ),
        )
    with service_errors(), open_uow(db, readonly=True) as uow:
        detail = views.package_detail(uow.conn(), package_id)
    typer.echo(f"analysed {detail.key} {detail.worst_class or 'none'}")


@app.command("submit")
def submit(ctx: typer.Context, ref: _Ref, actor: Actor = DEV_ACTOR) -> None:
    """Send your analysed draft to review. Refused for breaking or forbidden changes."""
    db: DbTarget = ctx.obj
    require_session(db)
    package_id = _package_id(db, ref)
    with service_errors(), open_uow(db) as uow:
        made = handle_submit_schema_package(
            uow,
            SubmitSchemaPackage(
                actor=acting(db, actor), source=SOURCE, scope="company", package_id=package_id
            ),
        )
    _report("submitted", made, ref)


@app.command("changes")
def changes(
    ctx: typer.Context,
    ref: _Ref,
    reason: Annotated[str, typer.Option("--reason", help="What the author must change.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Send a package in review back to its author (admin)."""
    db: DbTarget = ctx.obj
    require_admin(db)
    package_id = _package_id(db, ref)
    with service_errors(), open_uow(db) as uow:
        made = handle_request_schema_changes(
            uow,
            RequestSchemaChanges(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                package_id=package_id,
                reason=reason,
            ),
        )
    _report("sent-back", made, ref)


@app.command("approve")
def approve(
    ctx: typer.Context,
    ref: _Ref,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Approve a package in review (admin; never its author or submitter)."""
    db: DbTarget = ctx.obj
    require_admin(db)
    package_id = _package_id(db, ref)
    with service_errors(), open_uow(db) as uow:
        made = handle_approve_schema_package(
            uow,
            ApproveSchemaPackage(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                package_id=package_id,
                comment=comment,
            ),
        )
    _report("approved", made, ref)
