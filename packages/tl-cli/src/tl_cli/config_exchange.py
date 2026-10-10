"""`tl config diff|export|import`: compare layers and move a layer as YAML (P0-I8-T02; brief 30.4).

Each subcommand parses options, makes one call into `tl_core.settings`, and prints. The commands
join the `tl config` group (`tl_cli.config` adds this app to its own). The document format and its
rules (all or nothing, one reason for the file, locks only for the company) live in
`tl_core.settings.exchange`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core import settings
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.settings.types import SettingDiff
from tl_core.settings.values import format_value

from tl_cli.actors import refuse_agent

app = typer.Typer(help="Compare layers, export and import settings.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[
    str,
    typer.Option("--actor", help="Actor recorded on events.", callback=refuse_agent),
]
_Project = Annotated[str | None, typer.Option("--project", help="Project ID.")]
_User = Annotated[str | None, typer.Option("--user", help="User ID.")]
_Company = Annotated[bool, typer.Option("--company", help="The company layer.")]


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


def _layer(project: str | None, user: str | None, company: bool) -> str:
    if sum((bool(project), bool(user), company)) != 1:
        _fail("give exactly one of --company, --project and --user")
    if company:
        return "company"
    return f"project:{project}" if project else f"user:{user}"


def diff_line(item: SettingDiff) -> str:
    """``feed.reactions.enabled  true -> false`` (key, two spaces, left, `` -> ``, right).

    Both values are ``format_value(..., max_items=3)`` of the effective value on that side.
    """
    left = format_value(item.left.value, max_items=3)
    right = format_value(item.right.value, max_items=3)
    return f"{item.key}  {left} -> {right}"


@app.command("diff")
def diff(
    ctx: typer.Context,
    left: Annotated[str, typer.Argument(help="default, company, project:<id> or user:<id>.")],
    right: Annotated[str, typer.Argument(help="default, company, project:<id> or user:<id>.")],
) -> None:
    """Print the keys whose effective value differs between two layers, as `diff_line`s.

    Read-only unit of work inside ``_service_errors``, ``settings.diff(uow.conn(), left=left,
    right=right)``; print ``diff_line(item)`` for each (nothing when none differ).
    """
    db: Path = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        items = settings.diff(uow.conn(), left=left, right=right)
    for item in items:
        typer.echo(diff_line(item))


@app.command("export")
def export(
    ctx: typer.Context,
    project: _Project = None,
    user: _User = None,
    company: _Company = False,
    out: Annotated[Path | None, typer.Option("--out", help="Write to this file.")] = None,
) -> None:
    """Print what a layer holds as YAML, or write it to ``--out`` (then print `wrote <path>`).

    ``layer = _layer(project, user, company)`` first. Read-only unit of work inside
    ``_service_errors``, ``text = settings.export_yaml(uow.conn(), layer=layer)``. Without
    ``--out`` print ``text`` with ``typer.echo(text, nl=False)``; with it write ``text`` to the
    file (UTF-8) and print ``wrote <out>``.
    """
    db: Path = ctx.obj
    layer = _layer(project, user, company)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        text = settings.export_yaml(uow.conn(), layer=layer)
    if out is None:
        typer.echo(text, nl=False)
        return
    out.write_text(text, encoding="utf-8")
    typer.echo(f"wrote {out}")


@app.command("import")
def import_(
    ctx: typer.Context,
    file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="A YAML file.")
    ],
    project: _Project = None,
    user: _User = None,
    company: _Company = False,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Why (for keys that need it).")
    ] = None,
    accept_risk: Annotated[
        bool, typer.Option("--accept-risk", help="I accept the risk (dangerous keys).")
    ] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Apply a YAML file to a layer, all or nothing.

    ``layer = _layer(project, user, company)`` first; ``text`` is the file read as UTF-8. Write
    unit of work (``open_uow(db)``) inside ``_service_errors``, ``done = settings.import_yaml(uow,
    text, layer=layer, actor=actor, source="cli", reason=reason, accept_risk=accept_risk)``: a
    refusal raises out of the block, so nothing of the file is kept. Print ``imported
    <len(done)> keys into <layer>``.
    """
    db: Path = ctx.obj
    layer = _layer(project, user, company)
    try:
        text = file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _fail(f"{file} is not UTF-8 text")
    except OSError as exc:
        _fail(f"cannot read {file}: {exc.strerror}")
    with _service_errors(), open_uow(db) as uow:
        done = settings.import_yaml(
            uow,
            text,
            layer=layer,
            actor=actor,
            source="cli",
            reason=reason,
            accept_risk=accept_risk,
        )
    typer.echo(f"imported {len(done)} keys into {layer}")
