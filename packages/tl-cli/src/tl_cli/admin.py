"""The `tl admin` group: local recovery commands (ADR-0009 sec. 8 and 12).

``bootstrap``, ``unlock`` and ``audit`` need no sign-in: they are for the operator who can open the
ledger file, which is also how a locked-out sole admin gets back in. There is no API route for any
of them. The ``user`` and ``token`` sub-groups (admin session required) are added in P1-I0-T07.
"""

from __future__ import annotations

import getpass
import json
from dataclasses import asdict
from typing import Annotated

import typer
from tl_adapters.backend import ledger_exists
from tl_adapters.db import DbTarget, display_target
from tl_core.auth import audit, queries
from tl_core.auth.accounts import unlock
from tl_core.auth.seed import bootstrap_admin
from tl_core.auth.sessions import UowFactory
from tl_core.auth.types import AccountView

from tl_cli.prompts import read_password
from tl_cli.session import fail, open_backend, service_errors

app = typer.Typer(
    help="Accounts and access: recovery commands, users and agent tokens.", no_args_is_help=True
)

LOCAL_ACTOR = "svc:cli"
_Stdin = Annotated[bool, typer.Option("--password-stdin", help="Read the password from stdin.")]


def operator() -> str:
    """The OS user running the command, short and printable, for the audit row."""
    try:
        name = getpass.getuser()
    except (KeyError, OSError, ImportError):
        return "unknown"
    clean = "".join(ch for ch in name if ch.isprintable() and not ch.isspace())[:32]
    return clean or "unknown"


def backend_of(ctx: typer.Context) -> UowFactory:
    """The unit-of-work factory of the ledger ``--db`` names; exits 1 if there is no such ledger."""
    db: DbTarget = ctx.obj
    if not ledger_exists(db):
        fail(f"no ledger at {display_target(db)}: run `tl init` first")
    return open_backend(db)


def find_account(backend: UowFactory, username: str) -> AccountView:
    """The account called ``username``, or `error: no account named ...` and exit 1."""
    with backend(readonly=True) as uow:
        found = queries.find_account(uow.conn(), username=username)
    if found is None:
        fail(f"no account named {username!r}")
    return found


def account_line(view: AccountView) -> str:
    """``root  person  admin  active`` (two spaces), plus ``  locked until <time>`` while locked."""
    line = f"{view.username}  {view.kind}  {','.join(view.roles)}  {view.status}"
    return line + (f"  locked until {view.locked_until}" if view.locked_until else "")


def account_fields(view: AccountView) -> list[str]:
    """One ``name value`` line per field of an account (``tl admin user show``)."""
    return [
        f"username {view.username}",
        f"id {view.account_id}",
        f"display_name {view.display_name}",
        f"kind {view.kind}",
        f"roles {','.join(view.roles)}",
        f"status {view.status}",
        f"locked_until {view.locked_until or '-'}",
        f"created_at {view.created_at}",
    ]


@app.command("bootstrap")
def bootstrap(
    ctx: typer.Context,
    username: Annotated[str, typer.Option("--username", help="Admin username to create or reset.")],
    display_name: Annotated[str | None, typer.Option("--display-name")] = None,
    password_stdin: _Stdin = False,
) -> None:
    """Create the first admin, or reset an existing admin's password and unlock it (local only)."""
    backend = backend_of(ctx)
    password = read_password(from_stdin=password_stdin, confirm=not password_stdin)
    with service_errors():
        view = bootstrap_admin(
            backend,
            username=username,
            password=password,
            display_name=display_name,
            operator=operator(),
        )
    typer.echo(f"admin {view.username} is ready; sign in with `tl login {view.username}`")


@app.command("unlock")
def unlock_user(
    ctx: typer.Context,
    username: Annotated[str, typer.Argument(help="Name whose sign-in lock to clear.")],
) -> None:
    """Clear the sign-in lock of USERNAME (local only; there is no API route)."""
    backend = backend_of(ctx)
    with service_errors(), backend() as uow:
        cleared = unlock(uow, username=username, by=f"{LOCAL_ACTOR}:{operator()}")
    typer.echo(f"unlocked {username}" if cleared else f"{username} had no lock or failure count")


@app.command("audit")
def audit_log(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", help="Rows to show (1 to 1000).")] = 50,
    event: Annotated[str | None, typer.Option("--event", help="Only this event kind.")] = None,
    username: Annotated[str | None, typer.Option("--username", help="Only this name.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON list.")] = False,
) -> None:
    """Show the authentication audit log, newest first (local only)."""
    backend = backend_of(ctx)
    with service_errors():
        if not 1 <= limit <= 1000:
            fail("--limit must be between 1 and 1000")
        with backend(readonly=True) as uow:
            rows = audit.list_audit(uow.conn(), limit=limit, event=event, username_key=username)
    if as_json:
        typer.echo(json.dumps([asdict(row) for row in rows], indent=2))
        return
    for row in rows:
        times = f" x{row.count}" if row.count > 1 else ""
        who = row.username_key or row.account_id or "-"
        extra = f"  {row.detail}" if row.detail else ""
        typer.echo(f"{row.at}  {row.event}  {who}  by {row.actor or '-'}{times}{extra}")
