"""The `tl pset` group: set and read pset values of a record (brief 6.3).

Each subcommand parses options, makes one call into `tl_core.services`, and prints. Validation,
layer rules and conformance live in the services.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import ConcurrencyError, canonical_json
from tl_core.services.errors import ServiceError
from tl_core.services.psets import SetPsetValues, conformance, handle_set_pset_values
from tl_core.services.queries import get_record

app = typer.Typer(help="Set and read pset values.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
Layer = Literal["standard", "custom", "project"]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def parse_assignment(text: str) -> tuple[str, Any]:
    """``size_in=4`` becomes ``("size_in", 4)``. The value is JSON when it parses, else a string."""
    name, separator, raw = text.partition("=")
    if not separator or not name:
        _fail(f"expected NAME=VALUE, got {text!r}")
    try:
        return name, json.loads(raw)
    except json.JSONDecodeError:
        return name, raw


@app.command("set")
def set_values(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    key: Annotated[str, typer.Argument(help="Record key.")],
    pset: Annotated[str, typer.Argument(help="Pset name, e.g. valve_data or prj.shutdown_tie_in.")],
    assignments: Annotated[list[str], typer.Argument(help="NAME=VALUE; custom keys start x.")],
    layer: Annotated[
        str, typer.Option("--layer", help="standard, custom or project.")
    ] = "standard",
    actor: Annotated[str, typer.Option("--actor", help="Actor recorded on events.")] = (
        _DEFAULT_ACTOR
    ),
) -> None:
    """Set values of one pset on a record."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    values = dict(parse_assignment(a) for a in assignments)
    with _service_errors(), open_uow(db) as uow:
        current = get_record(uow, scope, key)
        if current is None:
            _fail(f"no record with key {key!r} in project {project!r}")
        result = handle_set_pset_values(
            uow,
            SetPsetValues(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=current["id"],
                expected_version=current["version"],
                pset=pset,
                layer=layer,  # pyright: ignore[reportArgumentType]
                values=values,
            ),
        )
    typer.echo(f"set {result.stream_id}")
    typer.echo(f"version {result.version}")
    typer.echo(f"conformance {result.events[0].payload['conformance']}")


def _section(psets: dict[str, Any], pset: str) -> Any:
    node: Any = psets
    for segment in pset.split("."):
        node = node.get(segment) if isinstance(node, dict) else None
        if node is None:
            return {}
    return node


@app.command("get")
def get_values(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    key: Annotated[str, typer.Argument(help="Record key.")],
    pset: Annotated[str | None, typer.Argument(help="Show only this pset.")] = None,
) -> None:
    """Show a record's pset values, stored schema hash and live conformance."""
    db: Path = ctx.obj
    with open_uow(db, readonly=True) as uow:
        row = get_record(uow, f"project:{project}", key)
        if row is None:
            _fail(f"no record with key {key!r} in project {project!r}")
        report = conformance(uow, row["id"])
    typer.echo(f"key: {row['key']}")
    typer.echo(f"version: {row['version']}")
    typer.echo(f"effective_schema_hash: {row['effective_schema_hash'] or '-'}")
    typer.echo(f"conformance: {report.status}")
    for issue in report.issues:
        typer.echo(f"issue {issue.level} {issue.rule} {issue.path} {issue.message}")
    shown = row["psets"] if pset is None else _section(row["psets"], pset)
    typer.echo(f"psets: {canonical_json(shown)}")
