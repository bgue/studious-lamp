"""Shared helpers of the `tl webhook` commands: the unit-of-work factory, scope and error output."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError

ACTOR = "user:dev"
SOURCE = "cli"


def fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def factory(ctx: typer.Context) -> Generator[SqliteUowFactory]:
    """A unit-of-work factory on the ledger file from ``--db`` / ``TL_DB``, disposed afterwards."""
    db: Path = ctx.obj
    opened = SqliteUowFactory(db)
    try:
        yield opened
    finally:
        opened.dispose()


@contextmanager
def service_errors() -> Iterator[None]:
    """Turn a refused command or bad input into ``error: <message>`` on stderr and exit code 1."""
    try:
        yield
    except ValidationError as exc:
        fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))
    except (ServiceError, ConcurrencyError, LookupError, ValueError) as exc:
        fail(str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc))


def scope_of(project: str | None, company: bool) -> str:
    """``project:<ID>`` or ``company``; exactly one of the two must be given."""
    if company == (project is not None):
        fail("give exactly one of --project <ID> and --company")
    return "company" if company else f"project:{project}"
