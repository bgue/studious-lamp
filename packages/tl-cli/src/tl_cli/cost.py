"""`tl cost import`: preview and apply one period of figures from the cost system (P1-I4).

The command reads a CSV export (`tl_mod_cost.imports.reader`: bounded, strict, no clock), compares
it with the project's cost codes (the plan, `tl_mod_cost.imports.plan`) and prints what would
change; with `--apply` the admin imports it as one correlated batch (`ImportCostSnapshot`; the
figures are money, ADR-0015). The preview writes nothing. Reads (`snapshots`, `codes`, `show`) are
in `tl_cli.cost_read`. This command parses options and prints.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_cost.errors import CostImportRefusedError
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot, handle_import_cost_snapshot
from tl_mod_cost.imports.plan import plan_import
from tl_mod_cost.imports.reader import read_cost_csv
from tl_mod_cost.limits import MAX_IMPORT_BYTES

from tl_cli import cost_read
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    fail,
    service_errors,
)
from tl_cli.session import require_admin

app = typer.Typer(help="Cost codes and period snapshots.", no_args_is_help=True)
cost_read.register(app)

MAX_SHOWN = 50


@app.command("import")
def import_snapshot(
    ctx: typer.Context,
    path: Annotated[
        Path, typer.Argument(help="The CSV export.", exists=True, dir_okay=False, readable=True)
    ],
    project: Project,
    period: Annotated[str, typer.Option("--period", help="The period, YYYY-MM.")],
    as_of: Annotated[
        str, typer.Option("--as-of", help="The date the figures are as of, YYYY-MM-DD.")
    ],
    currency: Annotated[
        str | None,
        typer.Option("--currency", help="ISO 4217 code of the amounts, for example USD."),
    ] = None,
    apply: Annotated[
        bool, typer.Option("--apply", help="Import it (admin). Without it nothing is written.")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Compare a cost export with the project's cost codes; with --apply, import it (admin).

    The preview prints `new=<n>  revised=<n>  unchanged=<n>` and then `+ <code>  level <n>  <title>`
    for each new code, `~ <code>  <field>: <old> -> <new>` for each changed title or unit, and
    `! <problem>` for each reason the file cannot be imported (exit 1). A corrected file for a
    period already imported becomes the next revision (`2026-07@2`).
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    if apply:
        require_admin(db)
    size = path.stat().st_size
    if size > MAX_IMPORT_BYTES:
        fail(f"{path.name} is {size} bytes; a cost export may be at most {MAX_IMPORT_BYTES}")
    data = path.read_bytes()
    with service_errors():
        parsed = read_cost_csv(data)
        command = ImportCostSnapshot(
            actor=acting(db, actor),
            source=SOURCE,
            scope=scope,
            period=period,
            as_of=as_of,
            currency=currency,
            source_name=path.name,
            source_sha256=hashlib.sha256(data).hexdigest(),
            rows=list(parsed.rows),
        )
        typer.echo(f"import {path.name} into project {project} as {period} (as of {as_of})")
        if parsed.ignored_columns:
            typer.echo(f"ignored columns: {', '.join(parsed.ignored_columns)}")
        with open_uow(db, readonly=not apply) as uow:
            plan = plan_import(uow.conn(), scope, command.rows)
            typer.echo(
                f"new={len(plan.new)}  revised={len(plan.revised)}  unchanged={plan.unchanged}"
            )
            for planned in plan.new[:MAX_SHOWN]:
                typer.echo(
                    f"+ {planned.row.code}  level {planned.level}  {cell(planned.row.description)}"
                )
            for planned in plan.revised[:MAX_SHOWN]:
                changes = "; ".join(
                    f"{name}: {cell(old)} -> {cell(new)}"
                    for name, (old, new) in planned.changes.items()
                )
                typer.echo(f"~ {planned.row.code}  {changes}")
            for problem in plan.issues:
                typer.echo(f"! {problem}")
            if plan.issues:
                raise CostImportRefusedError(
                    f"the cost snapshot cannot be imported ({len(plan.issues)} problem(s))",
                    list(plan.issues),
                )
            if not apply:
                typer.echo("dry run: nothing written; add --apply to write")
                return
            made = handle_import_cost_snapshot(uow, command)
    counts = f"codes={len(plan.codes)}  new={len(plan.new)}  revised={len(plan.revised)}"
    typer.echo(f"applied {made.key}: {counts}")
