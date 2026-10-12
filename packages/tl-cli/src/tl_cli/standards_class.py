"""The `tl standards class` group: tag classes, the classes that bind property sets (P1-I1-T09e).

A tag class names the property sets a tag of that class must carry (brief 9 M2). Each subcommand
parses options, makes one call into `tl_mod_engineering` (a handler or a read) and prints. The rules
(a required pset must exist, a closed class takes no more tags) live in the module. Classes are
company data: define, revise and close need the admin role; ls and show are open.

STUB (P1-I1-T09e): the bodies of the commands raise NotImplementedError; their signatures, options
and docstrings and the helpers (`_service_errors`, `_class`, `_list`) are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_mod_engineering import registry
from tl_mod_engineering.handlers.tag_class import (
    REVISABLE,
    CloseTagClass,
    DefineTagClass,
    ReviseTagClass,
    handle_close_tag_class,
    handle_define_tag_class,
    handle_revise_tag_class,
)
from tl_mod_engineering.names import COMPANY

from tl_cli.session import require_admin

app = typer.Typer(help="Define, show and change tag classes.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]
_Code = Annotated[str, typer.Argument(help="The class code, for example ControlValve.")]


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


def _class(uow: Any, code: str) -> registry.TagClassRow:
    """The active class ``code``, else the newest of any lifecycle, else `error:` and exit 1."""
    rows = registry.find_tag_classes(uow.conn(), COMPANY, code=code)
    if not rows:
        _fail(f"no tag class {code!r}")
    active = [row for row in rows if row.active]
    return (active or rows)[-1]


def _list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


@app.command("define")
def define(
    ctx: typer.Context,
    code: _Code,
    label: Annotated[str, typer.Option("--label", help="What the class is called.")],
    family: Annotated[
        str,
        typer.Option("--family", help="instrument, valve, pump, line, equipment, cable, other."),
    ],
    edition: Annotated[
        str,
        typer.Option(
            "--edition", help="The standards edition, for example co.acme.standards@1.0.0."
        ),
    ],
    definition: Annotated[str | None, typer.Option("--definition")] = None,
    pset: Annotated[
        list[str] | None,
        typer.Option("--pset", help="A property set a tag of this class must carry; repeatable."),
    ] = None,
    mnemonic: Annotated[
        list[str] | None, typer.Option("--mnemonic", help="A tag prefix of this class; repeatable.")
    ] = None,
    itr: Annotated[
        list[str] | None, typer.Option("--itr", help="An ITR template of this class; repeatable.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Define a tag class (admin). Its required property sets must exist in the company schema."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` handle_define_tag_class(uow,
    #    DefineTagClass(actor=actor, source="cli", scope=COMPANY, code=code, label=label,
    #    definition=definition, family=family, required_psets=pset or [], itr_templates=itr or
    #    [], mnemonics=mnemonic or [], edition=edition)).
    # 3. After the block print f"defined class {code}" and f"psets {_list(pset or [])}".
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    include_closed: Annotated[
        bool, typer.Option("--all", help="Include superseded and retired classes.")
    ] = False,
) -> None:
    """List tag classes by code: code, family, lifecycle, required property sets, label."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` rows =
    #    registry.find_tag_classes(uow.conn(), COMPANY, active_only=not include_closed).
    # 2. One line per row, columns separated by two spaces: code, family, lifecycle,
    #    _list(row.required_psets), label.
    raise NotImplementedError


@app.command("show")
def show(ctx: typer.Context, code: _Code) -> None:
    """Show one tag class: its fields, required property sets, prefixes and ITR templates."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` row = _class(uow,
    #    code).
    # 2. Print `name: value` lines in this order: code, label, family, lifecycle, edition, key
    #    ("-" when None), superseded_by ("-" when None), psets (_list of required_psets),
    #    mnemonics (_list), itr (_list of itr_templates), version.
    raise NotImplementedError


@app.command("revise")
def revise(
    ctx: typer.Context,
    code: _Code,
    reason: _Reason,
    label: Annotated[str | None, typer.Option("--label")] = None,
    family: Annotated[str | None, typer.Option("--family")] = None,
    pset: Annotated[
        list[str] | None,
        typer.Option("--pset", help="Replace the required property sets; repeatable."),
    ] = None,
    mnemonic: Annotated[
        list[str] | None, typer.Option("--mnemonic", help="Replace the tag prefixes; repeatable.")
    ] = None,
    itr: Annotated[
        list[str] | None, typer.Option("--itr", help="Replace the ITR templates; repeatable.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change a tag class (admin). A list option replaces the whole list."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`.
    # 2. changes = {} with these entries, only for the options that were given: "label", "family",
    #    "required_psets" (from --pset), "mnemonics" (from --mnemonic), "itr_templates" (from
    #    --itr). None given: _fail("nothing to revise: give --label, --family, --pset, --mnemonic
    #    or --itr").
    # 3. Inside `with _service_errors(), open_uow(db) as uow:` row = _class(uow, code);
    #    handle_revise_tag_class(uow, ReviseTagClass(actor=actor, source="cli", scope=COMPANY,
    #    stream_id=row.id, changes=changes, reason=reason)).
    # 4. After the block print f"revised class {code}: " and the changed field names in the order
    #    of REVISABLE, joined by ", " (one line).
    raise NotImplementedError


@app.command("close")
def close(
    ctx: typer.Context,
    code: _Code,
    reason: _Reason,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="The replacing class's code; omit to retire."),
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """End the life of a tag class (admin). Tags already of that class keep it."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` row = _class(uow, code); with
    #    --superseded-by other = _class(uow, superseded_by); lifecycle = "superseded" if other
    #    else "retired"; handle_close_tag_class(uow, CloseTagClass(actor=actor, source="cli",
    #    scope=COMPANY, stream_id=row.id, lifecycle=lifecycle, superseded_by=other.id if other
    #    else None, reason=reason)).
    # 3. After the block print f"closed class {code} as {lifecycle}".
    raise NotImplementedError
