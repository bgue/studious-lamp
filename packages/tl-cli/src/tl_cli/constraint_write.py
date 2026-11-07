"""`tl constraint raise|assign|clear|withdraw`: the write verbs of constraints (P2-I2-T04e2).

Each verb builds one command model of ``tl_core.constraints.commands`` and runs the handler that
``command_table()`` names for it, on one unit of work. The handler checks the edit word
(``core.constraint.edit``); this module adds no role check of its own. A constraint is named by its
key, as ``tl constraint ls`` prints it, and resolved to its id here; a record (subject, target,
resolving record) is named by its key and resolved with the lookup of ``tl_cli.link``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, cast

import typer
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.constraints import queries
from tl_core.constraints.commands import (
    AssignConstraint,
    ClearConstraint,
    RaiseConstraint,
    WithdrawConstraint,
    command_table,
)
from tl_core.services.commands import Command, CommandResult
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork

from tl_cli.awp_write import _parts
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
from tl_cli.session import session_viewer

CONSTRAINT_HELP = "Constraints: open holds on a record that block a phase."


def _handler(model: type[Command]) -> Callable[[UnitOfWork, Any], CommandResult]:
    """The handler ``command_table()`` names for this command model."""
    return next(c.handler for c in command_table() if c.model is model)


def _execute(db: DbTarget, build: Callable[[UnitOfWork], Command]) -> CommandResult:
    """Build the command on the ledger, run its handler; one write. A refusal of the edit word
    reads `error: forbidden: ...` as every CLI refusal of a role does."""
    with service_errors(), open_uow(db) as uow:
        command = build(uow)
        try:
            return _handler(type(command))(uow, command)
        except ForbiddenError as exc:
            fail(f"forbidden: {exc}")


def _record_id(uow: UnitOfWork, scope: str, key: str) -> str:
    """The id of the record with this key, visible to the reader; ``no record <key>`` else."""
    row = get_record(uow, scope, key)
    if row is None:
        fail(f"no record {key}")
    return str(row["id"])


def _constraint_id(uow: UnitOfWork, db: DbTarget, scope: str, key: str) -> str:
    """The id of the constraint with this key whose subject the reader may see.

    Hidden looks like missing: the same text as an unknown key.
    """
    conn = uow.conn()
    found = conn.execute(
        text(
            "SELECT id FROM cur_core_record "
            "WHERE key=:k AND type='core.Constraint' AND scope=:scope"
        ),
        {"k": key, "scope": scope},
    ).first()
    if (
        found is None
        or queries.get_constraint(conn, str(found.id), viewer=session_viewer(db)) is None
    ):
        fail(f"no constraint {key}")
    return str(found.id)


def raise_(
    ctx: typer.Context,
    project: Project,
    subject: Annotated[str, typer.Option("--subject", help="Key of the record it holds.")],
    phase: Annotated[str, typer.Option("--phase", help="The phase it blocks.")],
    severity: Annotated[str, typer.Option("--severity", help="blocking or advisory.")],
    category: Annotated[str, typer.Option("--category", help="The category.")],
    owner: Annotated[str | None, typer.Option("--owner", help="user:X, who owns it.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="What is held.")] = None,
    due: Annotated[str | None, typer.Option("--due", help="YYYY-MM-DD.")] = None,
    target: Annotated[
        str | None, typer.Option("--target", help="Key of the record it is about.")
    ] = None,
    target_ref: Annotated[
        str | None, typer.Option("--target-ref", help="TYPE:TEXT, a reference outside the ledger.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Raise a manual constraint on a record; prints `raised <key>  version <v>`."""
    db: DbTarget = ctx.obj
    if target is not None and target_ref is not None:
        raise typer.BadParameter("give --target or --target-ref, not both", param_hint="--target")
    ref_type: str | None = None  # the model checks the literal
    ref_text: str | None = None
    if target_ref is not None:
        with service_errors():
            ref_type, ref_text = _parts(target_ref, 2, "--target-ref", "TYPE:TEXT")
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        target_id = None if target is None else _record_id(uow, scope, target)
        with service_errors():
            return RaiseConstraint(
                actor=who,
                source=SOURCE,
                scope=scope,
                subject=_record_id(uow, scope, subject),
                phase=phase,
                severity=cast(Any, severity),
                category=cast(Any, category),
                owner=owner,
                description=description,
                due_at=due,
                target=target_id,
                target_ref_type=cast(Any, ref_type),
                target_ref_text=ref_text,
            )

    result = _execute(db, build)
    typer.echo(f"raised {result.key}  version {result.version}")


def assign(
    ctx: typer.Context,
    project: Project,
    key: Annotated[str, typer.Argument(help="Constraint key from `tl constraint ls`.")],
    owner: Annotated[str, typer.Option("--owner", help="user:X, who now owns it.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Give an open constraint to an owner; prints `assign <key>  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        constraint = _constraint_id(uow, db, scope, key)
        with service_errors():
            return AssignConstraint(
                actor=who, source=SOURCE, scope=scope, constraint=constraint, owner=owner
            )

    result = _execute(db, build)
    typer.echo(f"assign {key}  version {result.version}")


def clear(
    ctx: typer.Context,
    project: Project,
    key: Annotated[str, typer.Argument(help="Constraint key from `tl constraint ls`.")],
    reason: Annotated[str, typer.Option("--reason", help="Why it is cleared.")],
    cleared_at: Annotated[
        str | None, typer.Option("--cleared-at", help="World time: YYYY-MM-DD or a UTC stamp.")
    ] = None,
    resolved_by: Annotated[
        str | None, typer.Option("--resolved-by", help="Key of the record that resolved it.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Clear an open or assigned constraint; prints `clear <key>  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        constraint = _constraint_id(uow, db, scope, key)
        resolver = None if resolved_by is None else _record_id(uow, scope, resolved_by)
        with service_errors():
            return ClearConstraint(
                actor=who,
                source=SOURCE,
                scope=scope,
                constraint=constraint,
                reason=reason,
                cleared_at=cleared_at,
                resolved_by=resolver,
            )

    result = _execute(db, build)
    typer.echo(f"clear {key}  version {result.version}")


def withdraw(
    ctx: typer.Context,
    project: Project,
    key: Annotated[str, typer.Argument(help="Constraint key from `tl constraint ls`.")],
    reason: Annotated[str, typer.Option("--reason", help="Why it is withdrawn.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Withdraw an open or assigned constraint; prints `withdraw <key>  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        constraint = _constraint_id(uow, db, scope, key)
        with service_errors():
            return WithdrawConstraint(
                actor=who, source=SOURCE, scope=scope, constraint=constraint, reason=reason
            )

    result = _execute(db, build)
    typer.echo(f"withdraw {key}  version {result.version}")


def register(app: typer.Typer) -> None:
    """Add the four write verbs to the `constraint` group (T04g makes the group and calls this)."""
    for name, function in (
        ("raise", raise_),
        ("assign", assign),
        ("clear", clear),
        ("withdraw", withdraw),
    ):
        app.command(name)(function)
