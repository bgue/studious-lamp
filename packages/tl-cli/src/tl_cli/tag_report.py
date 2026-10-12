"""The `tl tag report` group: summary, missing property sets, pattern violations (P1-I1-T11).

Each subcommand reads through `tl_mod_engineering.reports` and prints. Nothing is written.

STUB (P1-I1-T11): the three command bodies raise NotImplementedError; the signatures, options and
docstrings are final. Each body has a STEPS comment. Implement them, then delete this paragraph, the
STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

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
    # STEPS
    # 1. db: DbTarget = ctx.obj. Inside `with open_uow(db, readonly=True) as uow:` lines =
    #    reports.register_summary(uow.conn(), f"project:{project}").
    # 2. With --json print json.dumps([asdict(line) for line in lines], indent=2) and return.
    # 3. Otherwise one line per SummaryLine, fields joined with two spaces: class_code or "-",
    #    status or "-", f"tags={n}", f"ok={n}", f"warning={n}", f"nonconformant={n}".
    raise NotImplementedError


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
    # STEPS
    # 1. db: DbTarget = ctx.obj. Inside `with open_uow(db, readonly=True) as uow:` lines =
    #    reports.missing_psets(uow, f"project:{project}", level=level).
    # 2. With --json print json.dumps([asdict(line) for line in lines], indent=2) and return.
    # 3. Otherwise per MissingLine print f"{number}  {class_code or '-'}  {status or '-'}" and
    #    then, per issue, f"  {level} {path} {rule}: {message}".
    raise NotImplementedError


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
    # STEPS
    # 1. db: DbTarget = ctx.obj. Inside `with open_uow(db, readonly=True) as uow:` lines =
    #    reports.pattern_violations(uow.conn(), f"project:{project}",
    #    include_warnings=include_warnings).
    # 2. With --json print json.dumps([asdict(line) for line in lines], indent=2) and return.
    # 3. Otherwise per ViolationLine print f"{number}  {number_status}" and then, per problem,
    #    f"  {level} {segment or 'number'}: {message}".
    raise NotImplementedError
