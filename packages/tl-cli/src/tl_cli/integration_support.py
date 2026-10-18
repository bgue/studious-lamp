"""Shared helpers of the integration commands (`tl rule`, `tl endpoint`, `tl delivery`,
`tl enrich`, `tl enricher`, `tl action`; P1-I7 WS-A). Final: no ticket changes this file.

A command parses its options, makes one call into `tl_core.integration`, and prints. The rules
live in the services. Every write command declares ``--actor`` (the actor hook gives it the
signed-in user as its default, ADR-0009 section 7). A secret is printed once, by the command that
made it, and never again; no helper here prints one.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, make_uow_factory
from tl_core.integration.errors import IntegrationNotFoundError
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_core.webhooks.base import UowFactory
from tl_core.webhooks.rows import load_json

from tl_cli.session import DEV_ACTOR, current_principal

SOURCE = "cli"
ActorOption = Annotated[
    str, typer.Option("--actor", help="The admin or person acting (user:<id>).")
]
ProjectOption = Annotated[
    str | None, typer.Option("--project", help="Project ID; scope project:<ID>.")
]
CompanyOption = Annotated[bool, typer.Option("--company", help="The company scope.")]
DEFAULT_ACTOR = DEV_ACTOR


def fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def factory(ctx: typer.Context) -> Generator[UowFactory]:
    """A unit-of-work factory on the ledger from ``--db`` / ``TL_DB``, disposed afterwards."""
    db: DbTarget = ctx.obj
    opened = make_uow_factory(db)
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
    except (ServiceError, ConcurrencyError, LookupError, ValueError, OSError) as exc:
        fail(str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc))


def scope_of(project: str | None, company: bool) -> str:
    """``project:<ID>`` or ``company``; exactly one of the two must be given."""
    if company == (project is not None):
        fail("give exactly one of --project <ID> and --company")
    return "company" if company else f"project:{project}"


def read_json_file(path: str) -> Any:
    """The JSON in a file (``-`` is standard input); bad JSON or a missing file is an error."""
    try:
        raw = typer.get_text_stream("stdin").read() if path == "-" else open(path).read()  # noqa: SIM115
        return json.loads(raw)
    except (OSError, ValueError) as exc:
        fail(f"cannot read JSON from {path}: {exc}")


def rows(uow: UnitOfWork, sql: str, **params: Any) -> list[dict[str, Any]]:
    """Rows as dicts; a ``*_json`` column is parsed and named without the suffix."""
    out: list[dict[str, Any]] = []
    for row in uow.conn().execute(text(sql), params).mappings():
        item: dict[str, Any] = {}
        for name, value in row.items():
            if name.endswith("_json") and isinstance(value, (str, bytes)):
                item[name.removesuffix("_json")] = load_json(value)
            else:
                item[name] = value
        out.append(item)
    return out


def one(uow: UnitOfWork, what: str, sql: str, **params: Any) -> dict[str, Any]:
    """The one row of ``sql`` or ``IntegrationNotFoundError`` naming ``what``."""
    found = rows(uow, sql, **params)
    if not found:
        raise IntegrationNotFoundError(f"no {what}")
    return found[0]


def line(*columns: object) -> str:
    """Columns joined by two spaces; ``None`` prints as ``-``."""
    return "  ".join("-" if c is None else str(c) for c in columns)


def pairs(values: Sequence[str], what: str) -> dict[str, str]:
    """``["a=1", "b=2"]`` as a dict; an item without ``=`` is an error."""
    found: dict[str, str] = {}
    for item in values:
        name, sep, value = item.partition("=")
        if not sep or not name:
            fail(f"{what} must be name=value, not {item!r}")
        found[name] = value
    return found


def admin_gate(ctx: typer.Context) -> None:
    """Refuse a signed-in person who is not an admin (`error: forbidden: ...`, exit 1).

    A command that authors or switches integration records is the admin's (FANOUT D12). On a dev,
    test or ci ledger file with no session the actor hook has already allowed the caller, who owns
    the file; with a session, the session's roles decide.
    """
    principal = current_principal(ctx.obj)
    if principal is not None and not principal.is_admin:
        fail("forbidden: this command needs the admin role")


def record_id_of(uow: UnitOfWork, key: str, scope: str) -> str:
    """The id of the live record with this key in this scope, or `error: no record <key>`."""
    found = one(
        uow,
        f"record {key}",
        "SELECT id FROM cur_core_record WHERE key = :key AND scope = :scope AND voided = :voided",
        key=key, scope=scope, voided=False,
    )  # fmt: skip
    return str(found["id"])
