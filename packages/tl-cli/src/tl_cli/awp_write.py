"""`tl awp cwp create|revise|allocate|move|void` and `tl awp package record|update|void`: the write
verbs of the work packaging (P2-I1-T04c).

Each verb builds one command model of ``tl_mod_awp.commands`` and runs the handler that
``AWP_COMMANDS`` names for it, after ``require_command`` has gated the command, on one unit of work.
The CLI parses options and prints one line; the handlers decide. A CWP or package is named by its
number and resolved to its id with the module's views. The WBS, CWA, path, ``rollup`` and ``worker``
verbs are not here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any, Literal

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import Command, CommandResult
from tl_core.services.queries import get_record_by_id
from tl_core.uow import UnitOfWork
from tl_mod_awp import views
from tl_mod_awp.commands import (
    AWP_COMMANDS,
    AllocateCwpToWbs,
    CloseCwp,
    CompleteCwp,
    CreateCwp,
    QuantityRow,
    RecordExternalPackage,
    ReleaseCwp,
    ReopenCwp,
    ReturnCwp,
    ReviseCwp,
    StartCwpDevelopment,
    StartCwpExecution,
    UpdateExternalPackage,
    VoidCwp,
    VoidExternalPackage,
    WbsLine,
)

from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_command

#: The actions of `tl awp cwp move`, each with its command model.
MOVES: dict[str, type[Command]] = {
    "start-development": StartCwpDevelopment,
    "start-execution": StartCwpExecution,
    "complete": CompleteCwp,
    "release": ReleaseCwp,
    "return": ReturnCwp,
    "close": CloseCwp,
    "reopen": ReopenCwp,
}
#: The actions that take a `--reason` (and need one).
REASONED_MOVES = (ReturnCwp, ReopenCwp)

CWP_HELP = "Construction work packages (CWPs)."
PACKAGE_HELP = "Engineering and procurement work packages."


def _handler(
    model: type[Command], *, table: Sequence[Any] = AWP_COMMANDS
) -> Callable[[UnitOfWork, Any], CommandResult]:
    """The handler ``table`` names for this command model (``AWP_COMMANDS`` unless told)."""
    return next(c.handler for c in table if c.model is model)


def _parts(value: str, count: int, option: str, shape: str) -> list[str]:
    """The ``:``-separated parts of an option value, exactly ``count`` of them, none empty."""
    parts = value.split(":")
    if len(parts) != count or not all(parts):
        fail(f"{option} {value}: expected {shape}")
    return parts


def _wbs_lines(values: list[str]) -> list[WbsLine]:
    """``--wbs CODE:PERCENT`` values as allocation lines; the shape is checked before the ledger."""
    lines: list[WbsLine] = []
    with service_errors():
        for value in values:
            code, percent = _parts(value, 2, "--wbs", "CODE:PERCENT")
            lines.append(WbsLine(wbs_code=code, percent=percent))
    return lines


def _quantities(values: list[str] | None) -> list[QuantityRow] | None:
    """``--qty COMMODITY:QTY:UOM`` values as quantity rows; None when no ``--qty`` is given."""
    if not values:
        return None
    rows: list[QuantityRow] = []
    with service_errors():
        for value in values:
            commodity, qty, uom = _parts(value, 3, "--qty", "COMMODITY:QTY:UOM")
            rows.append(QuantityRow(commodity=commodity, qty=qty, uom=uom))
    return rows


def _execute(
    db: DbTarget, build: Callable[[UnitOfWork], Command], *, table: Sequence[Any] = AWP_COMMANDS
) -> CommandResult:
    """Build the command on the ledger, gate it with the module role, run its handler; one write.

    ``table`` is the module's command table (``AWP_COMMANDS`` unless a module's CLI passes its own).
    """
    with service_errors(), open_uow(db) as uow:
        command = build(uow)
        require_command(uow, command)
        return _handler(type(command), table=table)(uow, command)


def _cwp_id(uow: UnitOfWork, project: str, number: str) -> str:
    found = views.cwp_detail(uow.conn(), scope_of(project), number)
    if found is None:
        fail(f"no CWP '{number}' in project {project}")
    return found.id


def _package_id(uow: UnitOfWork, project: str, number: str) -> str:
    found = [p for p in views.package_list(uow.conn(), scope_of(project)) if p.package_no == number]
    if not found:
        fail(f"no package '{number}' in project {project}")
    if len(found) > 1:
        fail(f"package '{number}' is named by {len(found)} references in project {project}")
    return found[0].id


def _line(verb: str, number: str, result: CommandResult) -> None:
    typer.echo(f"{verb} {number}  version {result.version}")


# --- cwp ------------------------------------------------------------------------------------------


def cwp_create(
    ctx: typer.Context,
    project: Project,
    discipline: Annotated[str, typer.Option("--discipline", help="The discipline code.")],
    title: Annotated[str, typer.Option("--title", help="The CWP's title.")],
    cwa: Annotated[str, typer.Option("--cwa", help="The construction work area code.")],
    planned_start: Annotated[
        str | None, typer.Option("--planned-start", help="YYYY-MM-DD.")
    ] = None,
    planned_finish: Annotated[
        str | None, typer.Option("--planned-finish", help="YYYY-MM-DD.")
    ] = None,
    budget_hours: Annotated[str | None, typer.Option("--budget-hours", help="Hours.")] = None,
    contractor: Annotated[str | None, typer.Option("--contractor", help="Contractor.")] = None,
    qty: Annotated[
        list[str] | None,
        typer.Option("--qty", help="COMMODITY:QTY:UOM; repeatable."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Create a CWP in the project; prints `created CWP <number>`."""
    db: DbTarget = ctx.obj
    quantities = _quantities(qty)
    who = acting(db, actor)
    with service_errors():
        command = CreateCwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            discipline=discipline,
            title=title,
            cwa_code=cwa,
            planned_start=planned_start,
            planned_finish=planned_finish,
            budget_hours=budget_hours,
            quantities=quantities,
            contractor_text=contractor,
        )
    result = _execute(db, lambda _uow: command)
    typer.echo(f"created CWP {result.key}")


def cwp_revise(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The CWP number.")],
    project: Project,
    title: Annotated[str | None, typer.Option("--title", help="A new title.")] = None,
    cwa: Annotated[str | None, typer.Option("--cwa", help="A new area code.")] = None,
    planned_start: Annotated[
        str | None, typer.Option("--planned-start", help="YYYY-MM-DD.")
    ] = None,
    planned_finish: Annotated[
        str | None, typer.Option("--planned-finish", help="YYYY-MM-DD.")
    ] = None,
    budget_hours: Annotated[str | None, typer.Option("--budget-hours", help="Hours.")] = None,
    contractor: Annotated[str | None, typer.Option("--contractor", help="Contractor.")] = None,
    qty: Annotated[
        list[str] | None,
        typer.Option("--qty", help="COMMODITY:QTY:UOM; repeatable; replaces the quantities."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Change the fields given; the others stay. Prints `revise <number>  version <n>`."""
    db: DbTarget = ctx.obj
    quantities = _quantities(qty)
    who = acting(db, actor)
    # only the options given are passed: a field left out stays, the model's null would clear it
    given: dict[str, Any] = {
        name: value
        for name, value in (
            ("title", title),
            ("cwa_code", cwa),
            ("planned_start", planned_start),
            ("planned_finish", planned_finish),
            ("budget_hours", budget_hours),
            ("contractor_text", contractor),
            ("quantities", quantities),
        )
        if value is not None
    }

    def build(uow: UnitOfWork) -> Command:
        return ReviseCwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            cwp=_cwp_id(uow, project, number),
            **given,
        )

    _line("revise", number, _execute(db, build))


def cwp_allocate(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The CWP number.")],
    project: Project,
    wbs: Annotated[
        list[str] | None,
        typer.Option(
            "--wbs", help="CODE:PERCENT of a WBS leaf; repeatable; replaces the allocation."
        ),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Replace the CWP's WBS allocation. Prints `allocate <number>  version <n>`."""
    db: DbTarget = ctx.obj
    lines = _wbs_lines(wbs or [])
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return AllocateCwpToWbs(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            cwp=_cwp_id(uow, project, number),
            allocations=lines,
        )

    _line("allocate", number, _execute(db, build))


def cwp_move(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The CWP number.")],
    action: Annotated[
        str,
        typer.Argument(
            help="start-development, start-execution, complete, release, return, close or reopen."
        ),
    ],
    project: Project,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Why; needed for return and reopen.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Move the CWP along its life cycle. Prints `move <number>  version <n>`."""
    db: DbTarget = ctx.obj
    model = MOVES.get(action)
    if model is None:
        fail(f"unknown ACTION {action!r}; the actions are {', '.join(MOVES)}")
    if model in REASONED_MOVES and not reason:
        fail(f"{action} needs --reason")
    takes_reason = model in REASONED_MOVES
    if reason is not None and not takes_reason:
        fail(f"{action} takes no --reason")
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        fields: dict[str, Any] = {
            "actor": who,
            "source": SOURCE,
            "scope": scope_of(project),
            "cwp": _cwp_id(uow, project, number),
        }
        if model is ReleaseCwp:
            # the version the caller read: the release refuses if the CWP has moved on since
            record = get_record_by_id(uow, fields["cwp"])
            if record is None:
                fail(f"no CWP '{number}' in project {project}")
            fields["expected_version"] = record["version"]
        elif takes_reason:
            fields["reason"] = reason
        return model(**fields)

    _line("move", number, _execute(db, build))


def cwp_void(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The CWP number.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the CWP is voided.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Void the CWP. Prints `void <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return VoidCwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            id=_cwp_id(uow, project, number),
            reason=reason,
        )

    _line("void", number, _execute(db, build))


# --- package --------------------------------------------------------------------------------------


def package_record(
    ctx: typer.Context,
    project: Project,
    package_type: Annotated[Literal["ewp", "pwp"], typer.Option("--type", help="ewp or pwp.")],
    number: Annotated[str, typer.Option("--number", help="The package number.")],
    title: Annotated[str, typer.Option("--title", help="The package's title.")],
    constraint_source: Annotated[
        bool, typer.Option("--constraint-source/--no-constraint-source", help="A constraint.")
    ],
    status: Annotated[str | None, typer.Option("--status", help="Status words.")] = None,
    forecast: Annotated[str | None, typer.Option("--forecast", help="YYYY-MM-DD.")] = None,
    actual: Annotated[str | None, typer.Option("--actual", help="YYYY-MM-DD.")] = None,
    source_system: Annotated[
        str | None, typer.Option("--source-system", help="The system it comes from.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Record an EWP or PWP reference. Prints `record <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        command = RecordExternalPackage(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            package_type=package_type,
            package_no=number,
            title=title,
            status_text=status,
            forecast_date=forecast,
            actual_date=actual,
            constraint_source=constraint_source,
            source_system=source_system,
        )
    _line("record", number, _execute(db, lambda _uow: command))


def package_update(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The package number.")],
    project: Project,
    status: Annotated[str | None, typer.Option("--status", help="Status words.")] = None,
    forecast: Annotated[str | None, typer.Option("--forecast", help="YYYY-MM-DD.")] = None,
    actual: Annotated[str | None, typer.Option("--actual", help="YYYY-MM-DD.")] = None,
    constraint_source: Annotated[
        bool | None,
        typer.Option("--constraint-source/--no-constraint-source", help="A constraint."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Change the fields given of a package reference. Prints `update <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    # only the options given are passed: a field left out stays, the model's null would clear it
    given: dict[str, Any] = {
        name: value
        for name, value in (
            ("status_text", status),
            ("forecast_date", forecast),
            ("actual_date", actual),
            ("constraint_source", constraint_source),
        )
        if value is not None
    }

    def build(uow: UnitOfWork) -> Command:
        return UpdateExternalPackage(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            id=_package_id(uow, project, number),
            **given,
        )

    _line("update", number, _execute(db, build))


def package_void(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The package number.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the reference is voided.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Void a package reference. Prints `void <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return VoidExternalPackage(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            id=_package_id(uow, project, number),
            reason=reason,
        )

    _line("void", number, _execute(db, build))


# --- registration ---------------------------------------------------------------------------------


def _group(app: typer.Typer, name: str, help_text: str) -> typer.Typer:
    """The sub-group ``name`` of the awp app: the one ``awp_read.register`` added, else a new one.

    Typer replaces a sub-group of the same name, so a second ``add_typer`` would hide the reads;
    the write verbs join the group that is already there.
    """
    for info in app.registered_groups:
        if info.name == name and info.typer_instance is not None:
            return info.typer_instance
    group = typer.Typer(help=help_text, no_args_is_help=True)
    app.add_typer(group, name=name)
    return group


def register(app: typer.Typer) -> None:
    """Add the write verbs to the `cwp` and `package` groups of the ``tl awp`` group.

    Call it after ``tl_cli.awp_read.register`` so the read verbs stay in the same groups.
    """
    cwp = _group(app, "cwp", CWP_HELP)
    package = _group(app, "package", PACKAGE_HELP)
    for group, name, function in (
        (cwp, "create", cwp_create),
        (cwp, "revise", cwp_revise),
        (cwp, "allocate", cwp_allocate),
        (cwp, "move", cwp_move),
        (cwp, "void", cwp_void),
        (package, "record", package_record),
        (package, "update", package_update),
        (package, "void", package_void),
    ):
        group.command(name)(function)
