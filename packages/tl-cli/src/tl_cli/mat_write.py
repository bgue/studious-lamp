"""The `tl mat` write verbs: receipt receive|inspect|accept|reject|void, move KIND, mto assign.

P2-I3-T05c. Each verb parses its options, builds the module's command model (scope
``project:<P>``, source ``cli``, the actor), checks the word with ``require_command``, runs the
handler in one ``open_uow(db)`` and prints one line. No rule lives here: the handlers refuse, and
``service_errors()`` prints the refusal and exits 1. Quantities stay text; the model validates them.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import Command
from tl_core.uow import UnitOfWork
from tl_mod_materials import common, views
from tl_mod_materials.handlers.movements import (
    AdjustStock,
    IssueStock,
    Movement,
    ReserveStock,
    ReturnStock,
    ScrapStock,
    TransferStock,
    UnreserveStock,
    handle_adjust_stock,
    handle_issue_stock,
    handle_reserve_stock,
    handle_return_stock,
    handle_scrap_stock,
    handle_transfer_stock,
    handle_unreserve_stock,
)
from tl_mod_materials.handlers.mto import AssignMtoLines, handle_assign_mto_lines
from tl_mod_materials.handlers.receipts import (
    AcceptReceipt,
    CreateReceipt,
    InspectReceipt,
    RejectReceipt,
    VoidReceipt,
    handle_accept_receipt,
    handle_create_receipt,
    handle_inspect_receipt,
    handle_reject_receipt,
    handle_void_receipt,
)

from tl_cli.derive_support import Actor, Project, fail, service_errors
from tl_cli.mat_read import _group
from tl_cli.session import DEV_ACTOR, require_command

SOURCE = "cli"
DEFAULT_CONDITION = "good"

Number = Annotated[str, typer.Argument(help="The receipt number, for example P123-RCPT-0001.")]


class MoveKind(StrEnum):
    """The seven stock movements of `tl mat move`."""

    issue = "issue"
    transfer = "transfer"
    return_ = "return"
    reserve = "reserve"
    unreserve = "unreserve"
    adjust = "adjust"
    scrap = "scrap"


#: Each kind's command model and handler (the `_Batch` command that carries one Movement).
MOVES: dict[MoveKind, tuple[type[Command], Callable[[UnitOfWork, Any], Any]]] = {
    MoveKind.issue: (IssueStock, handle_issue_stock),
    MoveKind.transfer: (TransferStock, handle_transfer_stock),
    MoveKind.return_: (ReturnStock, handle_return_stock),
    MoveKind.reserve: (ReserveStock, handle_reserve_stock),
    MoveKind.unreserve: (UnreserveStock, handle_unreserve_stock),
    MoveKind.adjust: (AdjustStock, handle_adjust_stock),
    MoveKind.scrap: (ScrapStock, handle_scrap_stock),
}


def _scope(project: str) -> str:
    return f"project:{project}"


def _state(uow: UnitOfWork, project: str, number: str) -> str:
    """The receipt's state, read back on the same unit of work after its handler ran."""
    return views.receipt_detail(uow.conn(), _scope(project), number).state


def _line(raw: str) -> dict[str, str | None]:
    """``ITEM:QTY[:HEAT[:CONDITION]]`` as a receipt line; a bad split is an error (exit 1)."""
    parts = raw.split(":")
    if not 2 <= len(parts) <= 4:
        fail(f"--line {raw!r} must be ITEM:QTY[:HEAT[:CONDITION]]")
    line: dict[str, str | None] = {
        "item_code": parts[0],
        "qty": parts[1],
        "heat_no": parts[2] if len(parts) > 2 and parts[2] else None,
        "condition": parts[3] if len(parts) > 3 and parts[3] else DEFAULT_CONDITION,
    }
    return line


def receipt_receive(
    ctx: typer.Context,
    project: Project,
    location: Annotated[str, typer.Option("--location", help="The receiving location code.")],
    received_on: Annotated[str, typer.Option("--received-on", help="YYYY-MM-DD.")],
    lines: Annotated[
        list[str],
        typer.Option("--line", help="ITEM:QTY[:HEAT[:CONDITION]]; repeat for each line (1 to 50)."),
    ],
    po_line: Annotated[str | None, typer.Option("--po-line", help="The PO line key.")] = None,
    supplier: Annotated[str | None, typer.Option("--supplier", help="The supplier text.")] = None,
    delivery_ref: Annotated[
        str | None, typer.Option("--delivery-ref", help="The delivery note reference.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """File a receipt of materials at a location. It stays Received until it is inspected."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db) as uow:
        command = CreateReceipt.model_validate(
            {
                "actor": actor,
                "source": SOURCE,
                "scope": _scope(project),
                "po_line": po_line,
                "supplier_text": supplier or "",
                "delivery_ref": delivery_ref,
                "received_on": received_on,
                "location_code": location,
                "lines": [_line(raw) for raw in lines],
            }
        )
        require_command(uow, command)
        made = handle_create_receipt(uow, command)
    typer.echo(f"received {made.key}  {len(lines)} lines")


def receipt_inspect(
    ctx: typer.Context,
    number: Number,
    project: Project,
    notes: Annotated[str | None, typer.Option("--notes", help="What the inspection found.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Record that a Received receipt was inspected."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db) as uow:
        receipt = views.receipt_detail(uow.conn(), _scope(project), number)
        command = InspectReceipt.model_validate(
            {
                "actor": actor,
                "source": SOURCE,
                "scope": _scope(project),
                "stream_id": receipt.id,
                "notes": notes,
            }
        )
        require_command(uow, command)
        handle_inspect_receipt(uow, command)
        state = _state(uow, project, number)
    typer.echo(f"{number} is {state}")


def receipt_accept(
    ctx: typer.Context,
    number: Number,
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Accept an Inspected receipt into stock: one lot per line."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db) as uow:
        receipt = views.receipt_detail(uow.conn(), _scope(project), number)
        command = AcceptReceipt.model_validate(
            {
                "actor": actor,
                "source": SOURCE,
                "scope": _scope(project),
                "stream_id": receipt.id,
                "expected_version": common.version_of(uow, receipt.id),
            }
        )
        require_command(uow, command)
        handle_accept_receipt(uow, command)
        state = _state(uow, project, number)
    typer.echo(f"{number} is {state}")


def receipt_reject(
    ctx: typer.Context,
    number: Number,
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the receipt is rejected.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Reject a receipt that is not accepted: no stock is made from it."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db) as uow:
        receipt = views.receipt_detail(uow.conn(), _scope(project), number)
        command = RejectReceipt.model_validate(
            {
                "actor": actor,
                "source": SOURCE,
                "scope": _scope(project),
                "stream_id": receipt.id,
                "reason": reason,
            }
        )
        require_command(uow, command)
        handle_reject_receipt(uow, command)
        state = _state(uow, project, number)
    typer.echo(f"{number} is {state}")


def receipt_void(
    ctx: typer.Context,
    number: Number,
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the receipt is void.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Void a receipt entered in error."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db) as uow:
        receipt = views.receipt_detail(uow.conn(), _scope(project), number)
        command = VoidReceipt.model_validate(
            {
                "actor": actor,
                "source": SOURCE,
                "scope": _scope(project),
                "stream_id": receipt.id,
                "reason": reason,
            }
        )
        require_command(uow, command)
        handle_void_receipt(uow, command)
        state = _state(uow, project, number)
    typer.echo(f"{number} is {state}")


def move_cmd(
    ctx: typer.Context,
    kind: Annotated[MoveKind, typer.Argument(help="The movement kind.")],
    project: Project,
    lot: Annotated[str, typer.Option("--lot", help="The lot key, for example P123-RCPT-0001@1.")],
    qty: Annotated[str, typer.Option("--qty", help="The quantity, as text.")],
    uom: Annotated[str, typer.Option("--uom", help="The unit of measure.")],
    from_: Annotated[str | None, typer.Option("--from", help="The location stock leaves.")] = None,
    to: Annotated[str | None, typer.Option("--to", help="The location stock goes to.")] = None,
    for_cost_code: Annotated[
        str | None, typer.Option("--for-cost-code", help="The cost code id (issue).")
    ] = None,
    for_line: Annotated[
        str | None, typer.Option("--for-line", help="The take-off line record id.")
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Why (adjust, scrap).")] = None,
    person: Annotated[str | None, typer.Option("--person", help="Who receives the issue.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Post one stock movement of a lot; KIND is one of the seven movement kinds."""
    db: DbTarget = ctx.obj
    model, handler = MOVES[kind]
    with service_errors(), open_uow(db) as uow:
        movement = Movement(
            lot_key=lot,
            qty=qty,
            uom=uom,
            from_location=from_,
            to_location=to,
            cost_code_id=for_cost_code,
            mto_line_id=for_line,
            reason=reason,
            person=person,
        )
        command = model.model_validate(
            {
                "actor": actor,
                "source": SOURCE,
                "scope": _scope(project),
                "movements": [movement],
            }
        )
        require_command(uow, command)
        handler(uow, command)
    typer.echo(f"{kind.value} {qty} {uom} lot {lot}")


def mto_assign(
    ctx: typer.Context,
    keys: Annotated[list[str], typer.Argument(help="One or more take-off line keys.")],
    project: Project,
    work_package: Annotated[str, typer.Option("--work-package", help="The work package number.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Assign take-off lines to a work package. A line with stock against it is refused."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db) as uow:
        command = AssignMtoLines.model_validate(
            {
                "actor": actor,
                "source": SOURCE,
                "scope": _scope(project),
                "mto_lines": keys,
                "work_package_number": work_package,
            }
        )
        require_command(uow, command)
        handle_assign_mto_lines(uow, command)
    typer.echo(f"assigned {len(keys)} lines to {work_package}")


def register(app: typer.Typer) -> None:
    """Add the write verbs to the `tl mat` group and its `receipt` and `mto` sub-groups."""
    receipt = _group(app, "receipt")
    mto = _group(app, "mto")
    for name, function in (
        ("receive", receipt_receive),
        ("inspect", receipt_inspect),
        ("accept", receipt_accept),
        ("reject", receipt_reject),
        ("void", receipt_void),
    ):
        receipt.command(name)(function)
    app.command("move")(move_cmd)
    mto.command("assign")(mto_assign)
