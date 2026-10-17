"""What every `tl derive` command shares: options, the file service, errors, the scope (P1-I3).

The commands are thin: parse options, make one call into `tl_mod_documents.derivation` and print.
The rules live in the module (ADR-0014). Each command that reads or writes rows calls
:func:`configure_files` first, so the module's file reads use this process's object store.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, is_postgres
from tl_adapters.objectstore import make_object_store, object_secret
from tl_core.files.service import FileService
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_mod_documents.derivation import store
from tl_mod_documents.errors import PublishRefusedError

from tl_cli.session import DEV_ACTOR as DEV_ACTOR
from tl_cli.session import check_actor

Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
OptProject = Annotated[
    str | None, typer.Option("--project", help="A project (scope project:<ID>).")
]
SOURCE = "cli"


def fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1.

    A refused publication prints one `  - <problem>` line per problem after the message.
    """
    try:
        yield
    except PublishRefusedError as exc:
        typer.echo(f"error: {exc}", err=True)
        for problem in exc.problems[:20]:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=1) from exc
    except (ServiceError, ConcurrencyError) as exc:
        fail(str(exc))
    except ValidationError as exc:
        fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def file_service() -> FileService:
    """The file service on the configured object store, or `error:` when none is configured."""
    try:
        return FileService(make_object_store(), secret=object_secret())
    except ValueError as exc:
        fail(str(exc))


def configure_files() -> FileService:
    """Tell the module which file service this process reads and writes rows with."""
    service = file_service()
    store.configure(service)
    return service


def scope_of(project: str | None, company: bool = False) -> str:
    """``company`` or ``project:<id>``; exactly one of the two must be given."""
    if company == (project is not None):
        fail("give --project ID or --company, and not both")
    return "company" if company else f"project:{project}"


def acting(db: DbTarget, actor: str) -> str:
    """The actor to record: the session's own, or anyone only in a dev setup on a ledger file.

    ``--actor`` is declared like every other command's (default ``user:dev``), which installs the
    hook of ``tl_cli.actor_hook`` (the default becomes the session's actor and every value is
    checked); this checks again, so a command that reaches the handler without the hook cannot
    act as someone else.
    """
    return check_actor(db, actor, local=not is_postgres(db))


def cell(value: object, width: int = 40) -> str:
    """One value for a table line: ``-`` for none, cut to ``width`` characters."""
    text = "-" if value is None or value == "" else str(value)
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"
