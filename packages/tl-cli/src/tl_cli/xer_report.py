# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl xer unscheduled`: records that point at no schedule activity (P1-I4-T10b).

Read only. The report is the module's (`tl_mod_schedule.reports`); the command parses options and
prints one line per fact, with two spaces between fields.


STUB (P1-I4-T10b): the body of `unscheduled` is `NotImplementedError`; the options, the docstring
(the exact output) and `register` are written. The ticket fills the body by its STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schedule import reports

from tl_cli.derive_support import Project, cell, service_errors


def unscheduled(
    ctx: typer.Context,
    project: Project,
    record_type: Annotated[
        str, typer.Option("--type", help="The record type, for example awp.IWP.")
    ],
    schedule: Annotated[
        str | None,
        typer.Option(
            "--schedule", help="Only count links to this schedule's activities (default: any)."
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 200,
) -> None:
    """List the records of a type that are linked to no schedule activity.

    First `records without an activity (<type>): <n>` (or `records without an activity (<type>)
    in <schedule>: <n>` with `--schedule`), then `<key or ->  <id>  <title>` for each, by key. A
    link to an activity that left the schedule does not count. An unknown schedule is
    `error: ...` on stderr, exit 1.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error such as an unknown schedule becomes
    #    `error: ...` on stderr with exit 1), call `reports.unscheduled_records(conn,
    #    f"project:{project}", record_type, schedule_code=schedule, limit=limit)` and leave
    #    the `with` before you print.
    # 3. Print `records without an activity (<type>)` followed by ` in <schedule>` when
    #    `--schedule` was given, then `: <n>`.
    # 4. Then one line per record: `<cell(key)>  <id>  <cell(title, 60)>`.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the report command to the `tl xer` group."""
    app.command("unscheduled")(unscheduled)
