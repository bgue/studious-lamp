"""`tl schema waiver request|approve|revoke|ls`: the time-limited exceptions (P1-I8-T05a3).

A waiver relaxes one property for one project until a date (at most 366 days ahead). Asking is any
signed-in person's; approving and revoking are the administrator's, and the person who asked
cannot approve (FANOUT D2, D5). The rules are the module's (`tl_mod_schemareg.handlers.waivers`);
these commands parse options, make one call and print. A refusal of the module is
`error: <message>` on stderr and exit code 1.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import registry, views
from tl_mod_schemareg.handlers.waivers import (
    ApproveWaiver,
    RequestWaiver,
    RevokeWaiver,
    handle_approve_waiver,
    handle_request_waiver,
    handle_revoke_waiver,
)

from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, acting, cell, fail, service_errors
from tl_cli.session import require_admin, require_session

app = typer.Typer(help="Ask for, approve, revoke and list waivers.", no_args_is_help=True)

_Ref = Annotated[str, typer.Argument(help="A waiver id or key, for example P123/psets.a.b@1.")]


def _waiver_id(db: DbTarget, ref: str) -> str:
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = registry.find_waiver(uow.conn(), ref)
    if found is None:
        fail(f"no waiver {ref!r}")
    return found.id


@app.command("request")
def request(
    ctx: typer.Context,
    project: Annotated[str, typer.Argument(help="The project, for example P123.")],
    path: Annotated[
        str, typer.Argument(help="The property, for example psets.valve_data.size_in.")
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why the property is relaxed.")],
    expires: Annotated[str, typer.Option("--expires", help="The last day, YYYY-MM-DD.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Ask to relax a property for a project until a date. Prints `requested <key> <id>`."""
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db) as uow:
        made = handle_request_waiver(
            uow,
            RequestWaiver(
                actor=acting(db, actor),
                source=SOURCE,
                scope=f"project:{project}",
                project=project,
                path=path,
                reason=reason,
                expires=expires,
            ),
        )
    typer.echo(f"requested {made.key} {made.stream_id}")


@app.command("approve")
def approve(
    ctx: typer.Context,
    ref: _Ref,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Approve a requested waiver (admin; never the person who asked). Prints `approved <key>`."""
    db: DbTarget = ctx.obj
    require_admin(db)
    waiver_id = _waiver_id(db, ref)
    with service_errors(), open_uow(db) as uow:
        done = handle_approve_waiver(
            uow,
            ApproveWaiver(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                waiver_id=waiver_id,
                comment=comment,
            ),
        )
    typer.echo(f"approved {done.key}")


@app.command("revoke")
def revoke(
    ctx: typer.Context,
    ref: _Ref,
    reason: Annotated[str, typer.Option("--reason", help="Why; kept in the ledger.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Revoke an approved waiver, or refuse a requested one (admin). Prints `revoked <key>`."""
    db: DbTarget = ctx.obj
    require_admin(db)
    waiver_id = _waiver_id(db, ref)
    with service_errors(), open_uow(db) as uow:
        done = handle_revoke_waiver(
            uow,
            RevokeWaiver(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                waiver_id=waiver_id,
                reason=reason,
            ),
        )
    typer.echo(f"revoked {done.key}")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: Annotated[str | None, typer.Option("--project", help="Only this project.")] = None,
    state: Annotated[
        str | None, typer.Option("--state", help="Requested, Approved or Revoked.")
    ] = None,
) -> None:
    """List waivers, one line each.

    `<key>  <state>  until <expires>  by <requester>  approver <name or ->`; an approved waiver
    whose day has passed shows `Approved (expired)` as its state. With none: `no waivers`.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        rows = views.waiver_views(uow.conn(), project, state)
    if not rows:
        typer.echo("no waivers")
        return
    for row in rows:
        shown = f"{row.state} (expired)" if row.expired else row.state
        typer.echo(
            f"{row.key}  {shown}  until {row.expires}  by {row.requested_by}  "
            f"approver {cell(row.approver)}"
        )
