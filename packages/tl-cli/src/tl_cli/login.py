"""`tl login`, `tl logout` and `tl whoami`: the CLI session of an embedded ledger (ADR-0009 sec. 4).

Thin glue over `tl_core.auth.sessions` and `tl_cli.session`. The password is read by
`tl_cli.prompts.read_password` (a hidden prompt or one line of standard input), never from an
option. The session token goes into the session file and is never printed. P1-I0-T06.
"""

from __future__ import annotations

from typing import Annotated

import typer
from sqlalchemy.exc import DBAPIError
from tl_adapters.backend import BackendUnavailableError, connection_failure, ledger_exists
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
    """Sign out: end the session in the ledger and forget it. Harmless when not signed in.

    The session on the server is ended first. If the server cannot be reached the local entry is
    forgotten all the same and one warning line says the server session was not revoked (it ends
    when it expires).
    """
    db: DbTarget = ctx.obj
    key = db_target(db)
    try:
        live = load(key)  # None when absent or already expired
    except SessionFileError as exc:
        fail(str(exc))
    problem: str | None = None
    if live is not None:
        try:
            if ledger_exists(db):
                sessions.sign_out(open_backend(db), token=live.token)
        except (BackendUnavailableError, DBAPIError) as exc:
            failure = connection_failure(db, exc)
            problem = str(failure) if failure is not None else "the database refused the request"
    try:
        earlier = forget(key)
    except SessionFileError as exc:
        fail(str(exc))
    if earlier is None:
        typer.echo("not signed in")
        return
    if problem is not None:
        typer.echo(
            f"warning: the session on the server could not be revoked ({problem}); "
            "it ends when it expires",
            err=True,
        )
    typer.echo(f"signed out {earlier.username}")


def whoami(ctx: typer.Context) -> None:
    """Print who you are signed in as, and your roles."""
    principal = require_session(ctx.obj)
    typer.echo(principal.actor)
    typer.echo(f"roles: {', '.join(principal.roles)}")
