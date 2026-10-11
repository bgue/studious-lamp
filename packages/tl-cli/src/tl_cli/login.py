"""`tl login`, `tl logout` and `tl whoami`: the CLI session of an embedded ledger (ADR-0009 sec. 4).

Thin glue over `tl_core.auth.sessions` and `tl_cli.session`. The password is read by
`tl_cli.prompts.read_password` (a hidden prompt or one line of standard input), never from an
option. The session token goes into the session file and is never printed. P1-I0-T06.

STUB (P1-I0-T06): the function bodies raise NotImplementedError; their signatures, annotations and
docstrings are final (they make the `--help` text). Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
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
    # STEPS
    # 1. db: Path = ctx.obj; backend = backend_of(ctx)  (exits 1 with `error: no ledger ...`).
    # 2. password = read_password(from_stdin=password_stdin, prompt=f"Password for {username}").
    # 3. Inside `with service_errors():` call
    #    `principal, token = sessions.sign_in(backend, username=username, password=password)`.
    #    A wrong password, an unknown name, a lock and a disabled account all end here as
    #    `error: ...` (exit 1) and nothing is stored.
    # 4. target = db_target(db). In a `try` that catches (SessionFileError, OSError) as exc:
    #    earlier = load(target); then save(StoredSession(target=target, username=username,
    #    actor=principal.actor, expires_at=expires_at_from(sessions.SESSION_TTL), token=token)).
    #    In the `except`: end the session just made, `sessions.sign_out(backend, token=token)`,
    #    then `fail(str(exc))`.
    # 5. If `earlier` is not None, end it: `sessions.sign_out(backend, token=earlier.token)`.
    # 6. typer.echo(f"signed in as {principal.actor} ({', '.join(principal.roles)})").
    #    Print nothing else: never the token, never the password.
    raise NotImplementedError


def logout(ctx: typer.Context) -> None:
    """Sign out: end the session in the ledger and forget it. Harmless when not signed in."""
    # STEPS
    # 1. db: Path = ctx.obj. earlier = forget(db_target(db)); a SessionFileError is
    #    `fail(str(exc))`.
    # 2. If earlier is None: typer.echo("not signed in") and return (exit 0).
    # 3. If db.is_file(): sessions.sign_out(open_backend(db), token=earlier.token).
    # 4. typer.echo(f"signed out {earlier.username}").
    raise NotImplementedError


def whoami(ctx: typer.Context) -> None:
    """Print who you are signed in as, and your roles."""
    # STEPS
    # 1. principal = require_session(ctx.obj)  (exits 1 with `error: not signed in: ...`).
    # 2. typer.echo(principal.actor), then typer.echo(f"roles: {', '.join(principal.roles)}").
    raise NotImplementedError
