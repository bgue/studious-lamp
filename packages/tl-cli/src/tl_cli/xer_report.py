"""`tl xer unscheduled`: records that point at no schedule activity (P1-I4-T10b).

Read only. The report is the module's (`tl_mod_schedule.reports`); the command parses options and
prints one line per fact, with two spaces between fields.
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
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = reports.unscheduled_records(
            uow.conn(),
            f"project:{project}",
            record_type,
            schedule_code=schedule,
            limit=limit,
        )
    scoped = "" if schedule is None else f" in {schedule}"
    typer.echo(f"records without an activity ({record_type}){scoped}: {len(found)}")
    for record in found:
        typer.echo(f"{cell(record.key)}  {record.id}  {cell(record.title, 60)}")


def register(app: typer.Typer) -> None:
    """Add the report command to the `tl xer` group."""
    app.command("unscheduled")(unscheduled)
