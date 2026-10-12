"""The `tl tag report` group: summary, missing property sets, pattern violations (P1-I1-T11).

Each subcommand reads through `tl_mod_engineering.reports` and prints. Nothing is written.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_engineering import reports

app = typer.Typer(help="Reports on a project's tags.", no_args_is_help=True)

_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Json = Annotated[bool, typer.Option("--json", help="Print JSON.")]


@app.command("summary")
def summary(ctx: typer.Context, project: _Project, as_json: _Json = False) -> None:
    """Tags in service by class and state: total, ok, warning, nonconformant."""
    db: DbTarget = ctx.obj
    with open_uow(db, readonly=True) as uow:
        lines = reports.register_summary(uow.conn(), f"project:{project}")
    if as_json:
        typer.echo(json.dumps([asdict(line) for line in lines], indent=2))
        return
    for line in lines:
        typer.echo(
            "  ".join(
                [
                    line.class_code or "-",
                    line.status or "-",
                    f"tags={line.tags}",
                    f"ok={line.ok}",
                    f"warning={line.warning}",
                    f"nonconformant={line.nonconformant}",
                ]
            )
        )


@app.command("missing")
def missing(
    ctx: typer.Context,
    project: _Project,
    level: Annotated[
        str | None,
        typer.Option("--level", help="Only issues of this level: warning or nonconformant."),
    ] = None,
    as_json: _Json = False,
) -> None:
    """Tags that lack a value their class or state requires, with what is missing."""
    db: DbTarget = ctx.obj
    with open_uow(db, readonly=True) as uow:
        lines = reports.missing_psets(uow, f"project:{project}", level=level)
    if as_json:
        typer.echo(json.dumps([asdict(line) for line in lines], indent=2))
        return
    for line in lines:
        typer.echo(f"{line.number}  {line.class_code or '-'}  {line.status or '-'}")
        for issue in line.issues:
            typer.echo(f"  {issue.level} {issue.path} {issue.rule}: {issue.message}")


@app.command("violations")
def violations(
    ctx: typer.Context,
    project: _Project,
    include_warnings: Annotated[
        bool, typer.Option("--warnings", help="Also list numbers that carry only a warning.")
    ] = False,
    as_json: _Json = False,
) -> None:
    """Tags whose number breaks the numbering pattern, with each problem."""
    db: DbTarget = ctx.obj
    with open_uow(db, readonly=True) as uow:
        lines = reports.pattern_violations(
            uow.conn(), f"project:{project}", include_warnings=include_warnings
        )
    if as_json:
        typer.echo(json.dumps([asdict(line) for line in lines], indent=2))
        return
    for line in lines:
        typer.echo(f"{line.number}  {line.number_status}")
        for problem in line.problems:
            typer.echo(
                f"  {problem['level']} {problem['segment'] or 'number'}: {problem['message']}"
            )
