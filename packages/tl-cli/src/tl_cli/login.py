"""`tl login`, `tl logout` and `tl whoami`: the CLI session of an embedded ledger (ADR-0009 sec. 4).

Thin glue over `tl_core.auth.sessions` and `tl_cli.session`. The password is read by
`tl_cli.prompts.read_password` (a hidden prompt or one line of standard input), never from an
option. The session token goes into the session file and is never printed. P1-I0-T06.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.backend import ledger_exists
from tl_adapters.db import DbTarget
from tl_core.auth import sessions

from tl_cli.admin import backend_of
from tl_cli.prompts import read_password
from tl_cli.session import (
    SessionFileError,
    StoredSession,
    db_target,
    expires_at_from,
    fail,
    forget,
    load,
    open_backend,
    require_session,
    save,
    service_errors,
)


def login(
    ctx: typer.Context,
    username: Annotated[str, typer.Argument(help="Your username.")],
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Read the password from standard input.")
    ] = False,
) -> None:
    """Sign in to the ledger (--db). The password is asked for without echo, or read from stdin."""
    db: DbTarget = ctx.obj
    backend = backend_of(ctx)
    password = read_password(from_stdin=password_stdin, prompt=f"Password for {username}")
    with service_errors():
        principal, token = sessions.sign_in(backend, username=username, password=password)
    target = db_target(db)
    try:
        earlier = load(target)
        save(
            StoredSession(
                target=target,
                username=username,
                actor=principal.actor,
                expires_at=expires_at_from(sessions.SESSION_TTL),
                token=token,
            )
        )
    except (SessionFileError, OSError) as exc:
        sessions.sign_out(backend, token=token)
        fail(str(exc))
    if earlier is not None:
        sessions.sign_out(backend, token=earlier.token)
    typer.echo(f"signed in as {principal.actor} ({', '.join(principal.roles)})")


def logout(ctx: typer.Context) -> None:
    """Sign out: end the session in the ledger and forget it. Harmless when not signed in."""
    db: DbTarget = ctx.obj
    try:
        earlier = forget(db_target(db))
    except SessionFileError as exc:
        fail(str(exc))
    if earlier is None:
        typer.echo("not signed in")
        return
    if ledger_exists(db):
        sessions.sign_out(open_backend(db), token=earlier.token)
    typer.echo(f"signed out {earlier.username}")


def whoami(ctx: typer.Context) -> None:
    """Print who you are signed in as, and your roles."""
    principal = require_session(ctx.obj)
    typer.echo(principal.actor)
    typer.echo(f"roles: {', '.join(principal.roles)}")
