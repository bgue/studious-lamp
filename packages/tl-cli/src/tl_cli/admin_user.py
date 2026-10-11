"""`tl admin user ...`: list, show, add, roles, disable, enable, reset-password (P1-I0-T07).

Needs a signed-in admin (`tl login`). Each command is one call into `tl_core.auth`. A password is
read by `read_password` (hidden prompt or stdin), checked and hashed **before** the write
transaction opens, and never printed.

STUB (P1-I0-T07): the function bodies raise NotImplementedError; their signatures, annotations and
docstrings are final (they make the `--help` text). Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
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
    # STEPS
    # 1. require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. `with service_errors(), backend(readonly=True) as uow:`
    #    views = queries.list_accounts(uow.conn()).
    # 3. With --json: typer.echo(json.dumps([view.model_dump() for view in views], indent=2)) and
    #    return.
    # 4. Else one typer.echo(account_line(view)) per view.
    raise NotImplementedError


@app.command("show")
def show(ctx: typer.Context, username: _Name) -> None:
    """Show one account, one field per line."""
    # STEPS
    # 1. require_admin(ctx.obj). With service_errors():
    #    view = find_account(backend_of(ctx), username).
    # 2. One typer.echo(line) per line of account_fields(view).
    raise NotImplementedError


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
        typer.Option("--role", help="admin or user; repeat for both. Default user."),
    ] = None,
    password_stdin: _Stdin = False,
) -> None:
    """Create an account. People and sim accounts get a password; agents get tokens instead."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. Inside `with service_errors():` and BEFORE any write transaction:
    #    prepared = None; if kind != "agent": password = read_password(from_stdin=password_stdin,
    #    confirm=not password_stdin); prepared = prepare_password(password, username=username).
    #    (The policy check and the slow hash must not run inside a write transaction.)
    # 3. Still inside service_errors(): `with backend() as uow:` view = accounts.create_account(uow,
    #    username=username, display_name=display_name or username, kind=cast(AccountKind, kind),
    #    roles=role or ["user"], password=prepared, by=admin.actor).
    # 4. typer.echo(f"created {account_line(view)}"). For an agent also
    #    typer.echo(f"next: tl admin token issue {view.username} --label <what it is for>").
    #    Never print the password.
    raise NotImplementedError


@app.command("roles")
def roles(
    ctx: typer.Context,
    username: _Name,
    role: Annotated[list[str], typer.Option("--role", help="admin or user; repeat for both.")],
    reason: _Reason = None,
) -> None:
    """Replace an account's roles. The last active admin cannot be demoted."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. With service_errors(): target = find_account(backend, username); then
    #    `with backend() as uow:` view = accounts.set_roles(uow, account_id=target.account_id,
    #    roles=role, by=admin.actor, reason=reason).
    # 3. typer.echo(account_line(view)).
    raise NotImplementedError


@app.command("disable")
def disable(ctx: typer.Context, username: _Name, reason: _Reason = None) -> None:
    """Disable an account: it cannot sign in and its sessions and tokens stop working."""
    # STEPS
    # Like `roles`, with accounts.disable(uow, account_id=..., by=admin.actor, reason=reason).
    # Print typer.echo(account_line(view)).
    raise NotImplementedError


@app.command("enable")
def enable(ctx: typer.Context, username: _Name, reason: _Reason = None) -> None:
    """Enable a disabled account again."""
    # STEPS
    # Like `disable`, with accounts.enable(...).
    raise NotImplementedError


@app.command("reset-password")
def reset_password(ctx: typer.Context, username: _Name, password_stdin: _Stdin = False) -> None:
    """Set a new password without the old one. Ends the account's sessions and clears any lock."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. Inside `with service_errors():` target = find_account(backend, username);
    #    password = read_password(from_stdin=password_stdin, confirm=not password_stdin);
    #    prepared = prepare_password(password, username=target.username)  (before any write).
    # 3. Then `with backend() as uow:` accounts.change_password(uow, account_id=target.account_id,
    #    new_password=prepared, by=admin.actor).
    # 4. typer.echo(f"password reset for {target.username}; their sessions ended and any lock is "
    #    "cleared").
    raise NotImplementedError
