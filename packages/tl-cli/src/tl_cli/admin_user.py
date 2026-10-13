"""`tl admin user ...`: list, show, add, roles, disable, enable, reset-password (P1-I0-T07).

Needs a signed-in admin (`tl login`). Each command is one call into `tl_core.auth`. A password is
read by `read_password` (hidden prompt or stdin), checked and hashed **before** the write
transaction opens, and never printed.
"""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer
from tl_core.auth import accounts, queries
from tl_core.auth.password import prepare_password
from tl_core.auth.types import AccountKind

from tl_cli.admin import account_fields, account_line, backend_of, find_account
from tl_cli.prompts import read_password
from tl_cli.session import require_admin, service_errors

app = typer.Typer(
    help="Accounts: list, add, roles, disable, enable, reset passwords.", no_args_is_help=True
)

_Name = Annotated[str, typer.Argument(help="The account's username.")]
_Reason = Annotated[str | None, typer.Option("--reason", help="Why (kept in the history).")]
_Stdin = Annotated[bool, typer.Option("--password-stdin", help="Read the password from stdin.")]

# Every command starts the same way, in this order:
#   admin = require_admin(ctx.obj)    # exits 1: `error: not signed in ...` / `error: forbidden ...`
#   backend = backend_of(ctx)         # exits 1: `error: no ledger at ...`
# and runs the service calls inside `with service_errors():`, which turns every service failure
# into `error: <message>` (exit 1) and lists the broken rules of a weak password. `admin.actor` is
# `by=` in every write. Do not catch exceptions yourself.


@app.command("ls")
def ls(
    ctx: typer.Context,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON list.")] = False,
) -> None:
    """List every account: name, kind, roles, status, and any lock."""
    require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors(), backend(readonly=True) as uow:
        views = queries.list_accounts(uow.conn())
    if as_json:
        typer.echo(json.dumps([view.model_dump() for view in views], indent=2))
        return
    for view in views:
        typer.echo(account_line(view))


@app.command("show")
def show(ctx: typer.Context, username: _Name) -> None:
    """Show one account, one field per line."""
    require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors():
        view = find_account(backend, username)
    for line in account_fields(view):
        typer.echo(line)


@app.command("add")
def add(
    ctx: typer.Context,
    username: _Name,
    display_name: Annotated[
        str | None, typer.Option("--display-name", help="Shown name; default: the username.")
    ] = None,
    kind: Annotated[
        str,
        typer.Option("--kind", help="person, sim or agent (an agent has a token, no password)."),
    ] = "person",
    role: Annotated[
        list[str] | None,
        typer.Option(
            "--role",
            help="admin, user or document_controller; repeat for several. Default user.",
        ),
    ] = None,
    password_stdin: _Stdin = False,
) -> None:
    """Create an account. People and sim accounts get a password; agents get tokens instead."""
    admin = require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors():
        prepared = None
        if kind != "agent":
            password = read_password(from_stdin=password_stdin, confirm=not password_stdin)
            prepared = prepare_password(password, username=username)
        with backend() as uow:
            view = accounts.create_account(
                uow,
                username=username,
                display_name=display_name or username,
                kind=cast(AccountKind, kind),
                roles=role or ["user"],
                password=prepared,
                by=admin.actor,
            )
    typer.echo(f"created {account_line(view)}")
    if kind == "agent":
        typer.echo(f"next: tl admin token issue {view.username} --label <what it is for>")


@app.command("roles")
def roles(
    ctx: typer.Context,
    username: _Name,
    role: Annotated[
        list[str] | None,
        typer.Option(
            "--role",
            help="Replace the roles with these: admin, user or document_controller; repeat.",
        ),
    ] = None,
    add: Annotated[
        list[str] | None, typer.Option("--add", help="Add this role to the ones it has; repeat.")
    ] = None,
    remove: Annotated[
        list[str] | None, typer.Option("--remove", help="Take this role away; repeat.")
    ] = None,
    reason: _Reason = None,
) -> None:
    """Change an account's roles: replace them (--role) or add and remove (--add, --remove).

    The last active admin cannot be demoted; an agent account cannot hold admin or
    document_controller.
    """
    admin = require_admin(ctx.obj)
    if role and (add or remove):
        raise typer.BadParameter("give --role (replace) or --add and --remove, not both")
    if not (role or add or remove):
        raise typer.BadParameter("give --role, --add or --remove")
    backend = backend_of(ctx)
    with service_errors():
        target = find_account(backend, username)
        wanted = (
            list(role) if role else sorted((set(target.roles) | set(add or [])) - set(remove or []))
        )
        with backend() as uow:
            view = accounts.set_roles(
                uow, account_id=target.account_id, roles=wanted, by=admin.actor, reason=reason
            )
    typer.echo(account_line(view))


@app.command("disable")
def disable(ctx: typer.Context, username: _Name, reason: _Reason = None) -> None:
    """Disable an account: it cannot sign in and its sessions and tokens stop working."""
    admin = require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors():
        target = find_account(backend, username)
        with backend() as uow:
            view = accounts.disable(
                uow, account_id=target.account_id, by=admin.actor, reason=reason
            )
    typer.echo(account_line(view))


@app.command("enable")
def enable(ctx: typer.Context, username: _Name, reason: _Reason = None) -> None:
    """Enable a disabled account again."""
    admin = require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors():
        target = find_account(backend, username)
        with backend() as uow:
            view = accounts.enable(uow, account_id=target.account_id, by=admin.actor, reason=reason)
    typer.echo(account_line(view))


@app.command("reset-password")
def reset_password(ctx: typer.Context, username: _Name, password_stdin: _Stdin = False) -> None:
    """Set a new password without the old one. Ends the account's sessions and clears any lock."""
    admin = require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors():
        target = find_account(backend, username)
        password = read_password(from_stdin=password_stdin, confirm=not password_stdin)
        prepared = prepare_password(password, username=target.username)
        with backend() as uow:
            accounts.change_password(
                uow, account_id=target.account_id, new_password=prepared, by=admin.actor
            )
    typer.echo(
        f"password reset for {target.username}; their sessions ended and any lock is cleared"
    )
