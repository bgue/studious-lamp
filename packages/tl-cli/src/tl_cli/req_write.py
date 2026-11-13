"""`tl req` and `tl wo` write verbs: raise, edit, approve, reject, cancel; schedule, assign, start,
complete, close (P2-I4A-T04e1).

Each verb builds one command model of ``tl_mod_requisitions.commands``, gates it with
``require_command`` and runs the handler that ``REQUISITIONS_COMMANDS`` names
(``awp_write._execute`` with ``table=REQUISITIONS_COMMANDS``), on one unit of work. A requisition or
work order is named by its record key and resolved with ``get_record``, which answers an unknown and
a hidden record the same way. The CLI parses options and prints one line; the handlers decide.
No fulfil verb (roadmap 3c); the reads come with T04d.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget
from tl_core.services.commands import Command
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_awp import iwp_views
from tl_mod_requisitions.commands import (
    ApproveRequisition,
    AssignWorkOrder,
    CancelRequisition,
    CloseWorkOrder,
    CompleteWorkOrder,
    EditRequisition,
    RaiseRequisition,
    RejectRequisition,
    ScheduleWorkOrder,
    StartWorkOrder,
)
from tl_mod_requisitions.module import REQUISITIONS_COMMANDS
from tl_mod_requisitions.names import REQUISITION_TYPES, WORK_ORDER

from tl_cli.awp_write import _execute, _line
from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, Project, acting, fail, scope_of

REQUISITION = "requisition"
WORK_ORDER_KIND = "work order"
#: The record types a requisition key may name, and a work order key may name.
_REQUISITION_TYPES = REQUISITION_TYPES
_WORK_ORDER_TYPES = (WORK_ORDER,)


# --- lookups --------------------------------------------------------------------------------------


def _record(
    uow: UnitOfWork, project: str, key: str, types: tuple[str, ...], what: str
) -> dict[str, Any]:
    """The record with this key and one of these types. Unknown and hidden look alike (D-r3b)."""
    row = get_record(uow, scope_of(project), key)
    if row is None or row["type"] not in types:
        fail(f"no {what} {key}")
    return row


def _iwp_id(uow: UnitOfWork, project: str, number: str) -> str:
    found = iwp_views.iwp_detail(uow.conn(), scope_of(project), number)
    if found is None:
        fail(f"no IWP {number}")
    return found.id


def _expected(row: dict[str, Any], given: int | None) -> int:
    """``--expected-version`` when given, else the version read in this unit of work."""
    return int(row["version"]) if given is None else given


def _clean(fields: dict[str, Any]) -> dict[str, Any]:
    """The fields that were given; a model takes an omitted field, not a None for a Literal."""
    return {name: value for name, value in fields.items() if value is not None}


def _when(value: str | None) -> datetime | None:
    """``--at`` as a time; the model checks that it carries a zone and is not in the future."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        fail(f"--at {value}: expected an ISO time with its time zone")


# --- raise ----------------------------------------------------------------------------------------


def _raise(
    ctx: typer.Context,
    project: str,
    actor: str,
    make_body: Callable[[UnitOfWork], Any],
    for_number: str | None,
) -> None:
    """Raise one requisition of the kind ``make_body`` builds; prints the raised key and version."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return RaiseRequisition(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            requisition=make_body(uow),
            for_record_id=None if for_number is None else _iwp_id(uow, project, for_number),
        )

    result = _execute(db, build, table=REQUISITIONS_COMMANDS)
    typer.echo(f"raised {result.key}  version {result.version}")


def raise_labor(
    ctx: typer.Context,
    project: Project,
    subject: Annotated[str, typer.Option("--subject", help="The subject.")],
    craft: Annotated[str, typer.Option("--craft", help="The craft.")],
    headcount: Annotated[int, typer.Option("--headcount", help="How many people.")],
    start: Annotated[str, typer.Option("--start", help="YYYY-MM-DD.")],
    end: Annotated[str, typer.Option("--end", help="YYYY-MM-DD.")],
    classification: Annotated[str | None, typer.Option("--classification", help="Grade.")] = None,
    shift: Annotated[str | None, typer.Option("--shift", help="The shift.")] = None,
    requirements: Annotated[
        str | None, typer.Option("--requirements", help="What the crew must have.")
    ] = None,
    need_by: Annotated[str | None, typer.Option("--need-by", help="YYYY-MM-DD.")] = None,
    priority: Annotated[str | None, typer.Option("--priority", help="low to urgent.")] = None,
    for_number: Annotated[str | None, typer.Option("--for", help="The IWP number.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Raise a labour requisition. Prints `raised <key>  version <v>`."""
    body = _clean(
        {
            "kind": "labor",
            "subject": subject,
            "craft": craft,
            "headcount": headcount,
            "start_date": start,
            "end_date": end,
            "classification": classification,
            "shift": shift,
            "requirements": requirements,
            "need_by": need_by,
            "priority": priority,
        }
    )
    _raise(ctx, project, actor, lambda _uow: body, for_number)


def raise_material(
    ctx: typer.Context,
    project: Project,
    subject: Annotated[str, typer.Option("--subject", help="The subject.")],
    line: Annotated[
        list[str] | None,
        typer.Option("--line", help="ITEMKEY:QTY:UOM, repeatable (1 to 200)."),
    ] = None,
    from_location: Annotated[
        str | None, typer.Option("--from-location", help="The location id.")
    ] = None,
    need_by: Annotated[str | None, typer.Option("--need-by", help="YYYY-MM-DD.")] = None,
    priority: Annotated[str | None, typer.Option("--priority", help="low to urgent.")] = None,
    for_number: Annotated[str | None, typer.Option("--for", help="The IWP number.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Raise a material requisition. Prints `raised <key>  version <v>`."""
    if not line:
        raise typer.BadParameter("give at least one --line ITEMKEY:QTY:UOM")

    def make_body(uow: UnitOfWork) -> Any:
        lines = [_item_line(uow, project, value) for value in line]
        return _clean(
            {
                "kind": "material",
                "subject": subject,
                "lines": lines,
                "from_location_id": from_location,
                "need_by": need_by,
                "priority": priority,
            }
        )

    _raise(ctx, project, actor, make_body, for_number)


def _item_line(uow: UnitOfWork, project: str, value: str) -> dict[str, str]:
    """``ITEMKEY:QTY:UOM`` as a requisition line; the item is named by its key."""
    parts = value.split(":")
    if len(parts) != 3 or not all(parts):
        fail(f"--line {value}: expected ITEMKEY:QTY:UOM")
    item_key, qty, uom = parts
    row = get_record(uow, scope_of(project), item_key)
    if row is None:
        fail(f"no item {item_key}")
    return {"item_id": str(row["id"]), "qty": qty, "uom": uom}


def raise_general(
    ctx: typer.Context,
    project: Project,
    subject: Annotated[str, typer.Option("--subject", help="The subject.")],
    type_code: Annotated[str, typer.Option("--type", help="The general requisition type.")],
    need_by: Annotated[str | None, typer.Option("--need-by", help="YYYY-MM-DD.")] = None,
    priority: Annotated[str | None, typer.Option("--priority", help="low to urgent.")] = None,
    for_number: Annotated[str | None, typer.Option("--for", help="The IWP number.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Raise a general requisition. Prints `raised <key>  version <v>`."""
    body = _clean(
        {
            "kind": "general",
            "subject": subject,
            "general_type": type_code,
            "need_by": need_by,
            "priority": priority,
        }
    )
    _raise(ctx, project, actor, lambda _uow: body, for_number)


def raise_scaffold(
    ctx: typer.Context,
    project: Project,
    subject: Annotated[str, typer.Option("--subject", help="The subject.")],
    purpose: Annotated[str, typer.Option("--purpose", help="What the scaffold is for.")],
    days: Annotated[int, typer.Option("--days", help="How many days it stands.")],
    need_by: Annotated[str | None, typer.Option("--need-by", help="YYYY-MM-DD.")] = None,
    priority: Annotated[str | None, typer.Option("--priority", help="low to urgent.")] = None,
    for_number: Annotated[str | None, typer.Option("--for", help="The IWP number.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Raise a scaffold request. Prints `raised <key>  version <v>`."""
    body = _clean(
        {
            "kind": "scaffold",
            "subject": subject,
            "purpose": purpose,
            "duration_days": days,
            "need_by": need_by,
            "priority": priority,
        }
    )
    _raise(ctx, project, actor, lambda _uow: body, for_number)


# --- requisition state verbs ----------------------------------------------------------------------


def _requisition_verb(
    ctx: typer.Context,
    verb: str,
    number: str,
    project: str,
    actor: str,
    expected_version: int | None,
    model: Callable[..., Command],
    fields: dict[str, Any],
) -> None:
    """One command on one requisition: ``model`` with its ``fields`` and the expected version."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        row = _record(uow, project, number, _REQUISITION_TYPES, REQUISITION)
        return model(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            requisition=str(row["id"]),
            expected_version=_expected(row, expected_version),
            **fields,
        )

    _line(verb, number, _execute(db, build, table=REQUISITIONS_COMMANDS))


def edit(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The requisition key.")],
    project: Project,
    subject: Annotated[str | None, typer.Option("--subject", help="The subject.")] = None,
    need_by: Annotated[str | None, typer.Option("--need-by", help="YYYY-MM-DD.")] = None,
    priority: Annotated[str | None, typer.Option("--priority", help="low to urgent.")] = None,
    craft: Annotated[str | None, typer.Option("--craft", help="The craft (labour).")] = None,
    headcount: Annotated[int | None, typer.Option("--headcount", help="Labour.")] = None,
    start: Annotated[str | None, typer.Option("--start", help="YYYY-MM-DD (labour).")] = None,
    end: Annotated[str | None, typer.Option("--end", help="YYYY-MM-DD (labour).")] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Change fields of a Requested requisition. Prints `edit <key>  version <v>`."""
    fields = _clean(
        {
            "subject": subject,
            "need_by": need_by,
            "priority": priority,
            "craft": craft,
            "headcount": headcount,
            "start_date": start,
            "end_date": end,
        }
    )
    if not fields:
        raise typer.BadParameter(
            "give at least one field: --subject, --need-by, --priority, --craft, "
            "--headcount, --start or --end"
        )
    _requisition_verb(
        ctx, "edit", number, project, actor, expected_version, EditRequisition, fields
    )


def approve(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The requisition key.")],
    project: Project,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Approve a requisition; this opens its work order. Prints `approve <key>  version <v>`."""
    _requisition_verb(
        ctx, "approve", number, project, actor, expected_version, ApproveRequisition, {}
    )


def reject(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The requisition key.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is rejected.")],
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Reject a requisition. Prints `reject <key>  version <v>`."""
    _requisition_verb(
        ctx,
        "reject",
        number,
        project,
        actor,
        expected_version,
        RejectRequisition,
        {"reason": reason},
    )


def cancel(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The requisition key.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is cancelled.")],
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Cancel a requisition. Prints `cancel <key>  version <v>`."""
    _requisition_verb(
        ctx,
        "cancel",
        number,
        project,
        actor,
        expected_version,
        CancelRequisition,
        {"reason": reason},
    )


# --- work order verbs -----------------------------------------------------------------------------


def _work_order_verb(
    ctx: typer.Context,
    verb: str,
    number: str,
    project: str,
    actor: str,
    expected_version: int | None,
    model: Callable[..., Command],
    fields: dict[str, Any],
) -> None:
    """One command on one work order: ``model`` with its ``fields`` and the expected version."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        row = _record(uow, project, number, _WORK_ORDER_TYPES, WORK_ORDER_KIND)
        return model(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            work_order=str(row["id"]),
            expected_version=_expected(row, expected_version),
            **fields,
        )

    _line(verb, number, _execute(db, build, table=REQUISITIONS_COMMANDS))


def schedule(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The work order key.")],
    project: Project,
    start: Annotated[str, typer.Option("--start", help="YYYY-MM-DD.")],
    finish: Annotated[str, typer.Option("--finish", help="YYYY-MM-DD.")],
    hours: Annotated[str | None, typer.Option("--hours", help="Planned hours.")] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Schedule an Open work order. Prints `schedule <key>  version <v>`."""
    _work_order_verb(
        ctx,
        "schedule",
        number,
        project,
        actor,
        expected_version,
        ScheduleWorkOrder,
        _clean({"planned_start": start, "planned_finish": finish, "hours_planned": hours}),
    )


def assign(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The work order key.")],
    project: Project,
    to: Annotated[str, typer.Option("--to", help="user:X, or free text.")],
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Set who does the work. Prints `assign <key>  version <v>`."""
    _work_order_verb(
        ctx,
        "assign",
        number,
        project,
        actor,
        expected_version,
        AssignWorkOrder,
        {"assigned_to": to},
    )


def start(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The work order key.")],
    project: Project,
    at: Annotated[str | None, typer.Option("--at", help="When the work started (ISO).")] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Start a scheduled work order. Prints `start <key>  version <v>`."""
    _work_order_verb(
        ctx,
        "start",
        number,
        project,
        actor,
        expected_version,
        StartWorkOrder,
        {"at": _when(at)},
    )


def complete(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The work order key.")],
    project: Project,
    hours: Annotated[str | None, typer.Option("--hours", help="Actual hours.")] = None,
    at: Annotated[str | None, typer.Option("--at", help="When the work finished (ISO).")] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Complete an In progress work order. Prints `complete <key>  version <v>`."""
    _work_order_verb(
        ctx,
        "complete",
        number,
        project,
        actor,
        expected_version,
        CompleteWorkOrder,
        _clean({"hours_actual": hours, "at": _when(at)}),
    )


def close(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The work order key.")],
    project: Project,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", help="The version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Close a Done work order. Prints `close <key>  version <v>`."""
    _work_order_verb(ctx, "close", number, project, actor, expected_version, CloseWorkOrder, {})


# --- registration ---------------------------------------------------------------------------------


def register(req_app: typer.Typer, wo_app: typer.Typer) -> None:
    """Add the write verbs to the ``req`` and ``wo`` groups (``tl_cli.req`` makes the groups)."""
    requisition_verbs: tuple[tuple[str, Callable[..., None]], ...] = (
        ("raise-labor", raise_labor),
        ("raise-material", raise_material),
        ("raise-general", raise_general),
        ("raise-scaffold", raise_scaffold),
        ("edit", edit),
        ("approve", approve),
        ("reject", reject),
        ("cancel", cancel),
    )
    work_order_verbs: tuple[tuple[str, Callable[..., None]], ...] = (
        ("schedule", schedule),
        ("assign", assign),
        ("start", start),
        ("complete", complete),
        ("close", close),
    )
    for name, function in requisition_verbs:
        req_app.command(name)(function)
    for name, function in work_order_verbs:
        wo_app.command(name)(function)
