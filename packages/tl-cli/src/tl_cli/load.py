"""`tl load loaders|open|extract|profile|bronze|plan|load|reconcile|compensate|void|ls|show`:
legacy loader runs (P1-I8; brief 29.6).

A run takes one spreadsheet or CSV export of an incumbent system through fixed stages: open (keep
the file), extract (read it in the resource envelope), profile, plan (map the rows and count what a
load would do), load (write the new rows as one correlated batch), reconcile (compare the project
with the file) and, if needed, compensate (end the records the run made). The rules are the
module's (`tl_mod_legacy`); these commands parse options and print.

Every command is the administrator's (FANOUT D9): a source file is an untrusted upload that costs
CPU, the load writes in bulk, and the profile and report quote the file. `bronze` copies the rows
into the lake, which every lake reader can read: take that step only for a file with nothing
restricted in it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_lake import LakeConfig
from tl_mod_legacy.errors import CompensationRefusedError, LoadRefusedError
from tl_mod_legacy.model import load_loaders
from tl_mod_legacy.registry import RunRow
from tl_mod_legacy.service import MAX_SOURCE_BYTES, LoadService

from tl_cli.derive_support import (
    DEV_ACTOR,
    Actor,
    Project,
    acting,
    cell,
    fail,
    file_service,
)
from tl_cli.session import require_admin

app = typer.Typer(help="Load legacy exports (CSV, XLSX) into a project.", no_args_is_help=True)

_Run = Annotated[str, typer.Argument(help="The run: system/table#n (dms/register#1) or its id.")]
_Lake = Annotated[
    str | None,
    typer.Option(
        "--lake-dir",
        envvar="TL_LAKE_DIR",
        help="Lake directory, for bronze (default ./dev/data/lake).",
    ),
]
_SHOWN = 20


@contextmanager
def _errors() -> Iterator[None]:
    """`error:` and, for a refused load or compensation, one `  - <problem>` line per problem."""
    try:
        yield
    except (CompensationRefusedError, LoadRefusedError) as exc:
        typer.echo(f"error: {exc}", err=True)
        for problem in exc.problems[:_SHOWN]:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=1) from exc
    except (ServiceError, ConcurrencyError) as exc:
        fail(str(exc))


def _service(db: DbTarget, lake_dir: str | None = None) -> LoadService:
    return LoadService(db, file_service(), lake=LakeConfig.at(lake_dir))


def _scope(project: str) -> str:
    return f"project:{project}"


def _line(run: RunRow) -> str:
    return f"{run.key}  {run.state}  {run.loader}  {cell(run.source_name)}"


@app.command("loaders")
def loaders() -> None:
    """List the installed loaders: name, system/table, what they write, the files they read."""
    for found in sorted(load_loaders().values(), key=lambda item: item.name):
        typer.echo(
            f"{found.name}  {found.system}/{found.table}  {found.target}  "
            f"{','.join(found.file_types)}  {cell(found.description, 60)}"
        )


@app.command("open")
def open_run(
    ctx: typer.Context,
    path: Annotated[
        Path, typer.Argument(help="The export.", exists=True, dir_okay=False, readable=True)
    ],
    project: Project,
    loader: Annotated[str, typer.Option("--loader", help="A name from `tl load loaders`.")],
    confidentiality: Annotated[
        str | None,
        typer.Option(
            "--confidentiality",
            help="internal or restricted; default the loader's, else internal. A restricted run "
            "and its files are read by document controllers and administrators only.",
        ),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Keep the file and record a run for it. Prints `opened <key> <id>`."""
    db: DbTarget = ctx.obj
    require_admin(db)
    if path.stat().st_size > MAX_SOURCE_BYTES:
        fail(f"{path.name} is larger than {MAX_SOURCE_BYTES} bytes")
    with _errors():
        run = _service(db).open(
            _scope(project),
            loader,
            path.name,
            path.read_bytes(),
            actor=acting(db, actor),
            confidentiality=confidentiality,
        )
    typer.echo(f"opened {run.key} {run.id}")


@app.command("extract")
def extract(ctx: typer.Context, run: _Run, project: Project, actor: Actor = DEV_ACTOR) -> None:
    """Read the file in the resource envelope and keep its rows (prints row and column counts)."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        done = _service(db).extract(_scope(project), run, actor=acting(db, actor))
    typer.echo(f"extracted {done.key} rows {done.row_count} columns {done.column_count}")


@app.command("profile")
def profile(
    ctx: typer.Context,
    run: _Run,
    project: Project,
    show: Annotated[bool, typer.Option("--show", help="Print the stored profile.")] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Profile the rows (columns, shapes, keys, repeats); with --show, print a finished profile."""
    db: DbTarget = ctx.obj
    require_admin(db)
    service = _service(db)
    with _errors():
        if not show:
            service.profile(_scope(project), run, actor=acting(db, actor))
            typer.echo(f"profiled {service.get(_scope(project), run).key}")
            return
        body = service.profile_of(_scope(project), run)
    typer.echo(f"rows {body['rows']}  duplicate rows {body['duplicate_rows']}")
    for column in body["columns"]:
        keyish = " key-candidate" if column["key_candidate"] else ""
        typer.echo(
            f"{cell(column['name'], 30)}  non-empty {column['non_empty']}  distinct "
            f"{column['distinct']}  repeats {column['repeats']}  shape {column['shape'] or '-'}"
            f"{keyish}"
        )


@app.command("bronze")
def bronze(
    ctx: typer.Context,
    run: _Run,
    project: Project,
    lake_dir: _Lake = None,
    include_confidential: Annotated[
        bool,
        typer.Option(
            "--include-confidential",
            help="Say that the file may hold rows of records that are not open to every reader "
            "and copy it all the same. Needed for every copy; refused for a restricted run.",
        ),
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Copy the rows as they are into the lake table legacy_<system>_<table>.

    Every reader of the lake can read the copy, so a restricted run is never copied and an
    internal one needs `--include-confidential`. Prints `bronze <key> rows <n>`.
    """
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        service = _service(db, lake_dir)
        written = service.bronze(
            _scope(project),
            run,
            actor=acting(db, actor),
            include_confidential=include_confidential,
        )
        key = service.get(_scope(project), run).key
    typer.echo(f"bronze {key} rows {written}")


@app.command("plan")
def plan(ctx: typer.Context, run: _Run, project: Project, actor: Actor = DEV_ACTOR) -> None:
    """Map the rows and count what a load would do (new, existing, invalid); writes nothing else."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        done, planned = _service(db).plan(_scope(project), run, actor=acting(db, actor))
    typer.echo(
        f"planned {done.key} new {done.plan_new} existing {done.plan_existing} "
        f"invalid {done.plan_invalid}"
    )
    for line, problem in planned.invalid[:_SHOWN]:
        typer.echo(f"  line {line}: {problem}")
    if len(planned.invalid) > _SHOWN:
        typer.echo(f"  ... and {len(planned.invalid) - _SHOWN} more")


@app.command("load")
def load(
    ctx: typer.Context,
    run: _Run,
    project: Project,
    expect_new: Annotated[
        int | None, typer.Option("--expect-new", min=0, help="The new rows you saw in the plan.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Write the new rows as one correlated batch (create-only; rows that exist are left alone)."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        service = _service(db)
        outcome = service.load(_scope(project), run, actor=acting(db, actor), expect_new=expect_new)
        key = service.get(_scope(project), run).key
    typer.echo(
        f"loaded {key} created {outcome.created} existing {outcome.skipped_existing} "
        f"invalid {outcome.skipped_invalid} correlation {outcome.correlation_id}"
    )


@app.command("reconcile")
def reconcile(
    ctx: typer.Context,
    run: _Run,
    project: Project,
    show: Annotated[bool, typer.Option("--show", help="Print the problems of the report.")] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Compare the project with the file and keep the report. Prints the mismatch count."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        done, report = _service(db).reconcile(_scope(project), run, actor=acting(db, actor))
    typer.echo(
        f"reconciled {done.key} matched {report['matched']} mismatches {report['mismatches']} "
        f"left-alone-that-differ {report['left_alone_that_differ']}"
    )
    if show or report["mismatches"]:
        for problem in report["problems"][:_SHOWN]:
            typer.echo(f"  {problem}")


@app.command("compensate")
def compensate(
    ctx: typer.Context,
    run: _Run,
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the batch is taken back.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """End the records this run created, all or nothing, by the ids the run recorded."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        service = _service(db)
        outcome = service.compensate(_scope(project), run, actor=acting(db, actor), reason=reason)
        key = service.get(_scope(project), run).key
    typer.echo(f"compensated {key} reversed {outcome.reversed}")


@app.command("void")
def void(
    ctx: typer.Context,
    run: _Run,
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the run is abandoned.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Abandon a run that has not loaded anything."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        done = _service(db).void(_scope(project), run, actor=acting(db, actor), reason=reason)
    typer.echo(f"voided {done.key}")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: Project,
    state: Annotated[str | None, typer.Option("--state")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 100,
) -> None:
    """List the runs of a project, newest first: key, state, loader, file."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        runs = _service(db).runs(_scope(project), state=state, limit=limit)
    for run in runs:
        typer.echo(_line(run))


@app.command("show")
def show(
    ctx: typer.Context,
    run: _Run,
    project: Project,
    report: Annotated[bool, typer.Option("--report", help="Print the stored report.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """One run: its state, counts and files (`--report` the reconciliation report as JSON)."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _errors():
        service = _service(db)
        if report:
            typer.echo(
                json.dumps(service.report_of(_scope(project), run), indent=2, sort_keys=True)
            )
            return
        found = service.get(_scope(project), run)
    fields = {
        "run": found.key,
        "id": found.id,
        "state": found.state,
        "loader": found.loader,
        "file": found.source_name,
        "rows": found.row_count,
        "columns": found.column_count,
        "bronze rows": found.bronze_rows,
        "plan new": found.plan_new,
        "plan existing": found.plan_existing,
        "plan invalid": found.plan_invalid,
        "loaded": found.loaded_count,
        "correlation": found.correlation_id,
        "mismatches": found.mismatches,
        "last error": found.last_error,
        "confidentiality": found.confidentiality,
        "opened by": found.opened_by,
    }
    if as_json:
        typer.echo(json.dumps(fields, indent=2, sort_keys=True))
        return
    for name, value in fields.items():
        if value is not None:
            typer.echo(f"{name} {value}")
