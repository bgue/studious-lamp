"""The `tl new` group: scaffolders for modules, record types and projectors (brief 25.2).

Each subcommand parses the name, asks a planner in ``tl_cli.scaffold`` for the files, and writes
them without overwriting anything. Rules about what a module or record type contains live in the
planners and their templates. Output: one ``created <path>`` line per file, then ``next:`` lines
on stderr. ``--dry-run`` prints ``would create <path>`` and writes nothing. Not yet built, and
recorded as follow-ups: correspondence-domain, action, rule, enricher, connector, report, extractor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from tl_cli.scaffold.engine import (
    Plan,
    ScaffoldError,
    check_plan,
    require_module,
    use_root,
    write_plan,
)
from tl_cli.scaffold.module import plan_module
from tl_cli.scaffold.names import (
    NameError_,
    check_event_type,
    parse_module,
    parse_projector,
    parse_record_type,
)
from tl_cli.scaffold.projector import plan_projector
from tl_cli.scaffold.record_type import plan_record_type

app = typer.Typer(
    help="Create a module, a record type or a projector from templates.", no_args_is_help=True
)

RootOption = Annotated[
    Path | None,
    typer.Option("--root", help="Repository root (default: the one around the current directory)."),
]
DryRun = Annotated[bool, typer.Option("--dry-run", help="Print the files; write nothing.")]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def _finish(root: Path, plan: Plan, dry_run: bool) -> None:
    try:
        if dry_run:
            check_plan(root, plan)
            for item in plan.files:
                typer.echo(f"would create {item.path}")
            return
        for path in write_plan(root, plan):
            typer.echo(f"created {path}")
    except ScaffoldError as exc:
        _fail(str(exc))
    for step in plan.next_steps:
        typer.echo(f"next: {step}", err=True)


@app.command("module")
def new_module(
    name: Annotated[
        str, typer.Argument(help="Module name, lower_snake_case (for example inspection).")
    ],
    root: RootOption = None,
    dry_run: DryRun = False,
) -> None:
    """Create packages/tl-mod-NAME, schema/modules/NAME/module.yaml and docs/modules/NAME/."""
    try:
        module = parse_module(name)
        base = use_root(root)
        plan = plan_module(module)
    except (NameError_, ScaffoldError) as exc:
        _fail(str(exc))
    _finish(base, plan, dry_run)


@app.command("record-type")
def new_record_type(
    name: Annotated[str, typer.Argument(help="<module>.<Class>, for example inspection.Weld.")],
    root: RootOption = None,
    dry_run: DryRun = False,
) -> None:
    """Add a record type to an existing module: schema stub, handler, tests and a spec page."""
    try:
        record_type = parse_record_type(name)
        base = use_root(root)
        require_module(base, record_type.module.directory, record_type.module.name)
        plan = plan_record_type(record_type)
    except (NameError_, ScaffoldError) as exc:
        _fail(str(exc))
    _finish(base, plan, dry_run)


@app.command("projector")
def new_projector(
    name: Annotated[
        str, typer.Argument(help="<module>.<name>, for example inspection.weld_counts.")
    ],
    event: Annotated[
        list[str] | None,
        typer.Option("--event", help="Event type the projector handles; repeat for several."),
    ] = None,
    root: RootOption = None,
    dry_run: DryRun = False,
) -> None:
    """Add a projector for a derived table to an existing module: projector, tests, docs."""
    try:
        projector = parse_projector(name)
        events = [check_event_type(item) for item in (event or ["Record.Created"])]
        base = use_root(root)
        require_module(base, projector.module.directory, projector.module.name)
        plan = plan_projector(projector, events)
    except (NameError_, ScaffoldError) as exc:
        _fail(str(exc))
    _finish(base, plan, dry_run)
