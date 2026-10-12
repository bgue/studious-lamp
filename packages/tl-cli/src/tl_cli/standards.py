"""The `tl standards` group: load and read the company standards registry (brief 6.4; P1-I1-T09a).

Each subcommand parses options, makes one call into `tl_mod_engineering` (the loader, a handler or
a read) and prints. The rules (code-list policies, supersession, what the registry may hold) live
in the module. The registry is company data: every command that changes it needs the admin role,
except adding a value to a code list in a project (`add-value --project`), which any signed-in user
may do when the list's policy allows it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_mod_engineering import codelists, registry
from tl_mod_engineering.document import StandardsDocError, load_standards_file
from tl_mod_engineering.handlers.standards import (
    AddCodeValue,
    CloseCodeValue,
    CloseStandard,
    handle_add_code_value,
    handle_close_code_value,
    handle_close_standard,
)
from tl_mod_engineering.loader import ItemKind, LoadReport, load_standards, plan_load
from tl_mod_engineering.names import COMPANY

from tl_cli.session import require_admin

app = typer.Typer(help="Load and read the company standards registry.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]
_Project = Annotated[
    str | None,
    typer.Option("--project", help="Project ID; the project's own values (default: company)."),
]
_Kind = Annotated[str, typer.Argument(help="code-list, mnemonic or pattern.")]

#: The kind names a person types, and the kind the registry stores.
KINDS = {"code-list": "code_list", "mnemonic": "mnemonic", "pattern": "numbering_pattern"}
#: The order in which a load summary lists the kinds of entry.
LOAD_ORDER: tuple[ItemKind, ...] = (
    "code_list",
    "code_value",
    "mnemonic",
    "numbering_pattern",
    "tag_class",
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency, document or input failure into `error:` on stderr, exit 1."""
    try:
        yield
    except StandardsDocError as exc:
        _fail(str(exc))
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _kind(value: str) -> str:
    """The stored kind for what a person typed, or `error:` and exit 1."""
    if value not in KINDS:
        _fail(f"unknown kind {value!r}: use code-list, mnemonic or pattern")
    return KINDS[value]


def _scope(project: str | None) -> str:
    return COMPANY if project is None else f"project:{project}"


def _counts(report: LoadReport) -> None:
    """One line per kind of entry: `<kind>  create=<n>  skip=<n>`."""
    for kind in LOAD_ORDER:
        typer.echo(
            f"{kind}  create={report.count(kind, 'create')}  skip={report.count(kind, 'skip')}"
        )


@app.command("load")
def load(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="A standards YAML file, one edition.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print what would be loaded; write nothing.")
    ] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Load an edition of the standards into the registry. Entries already there are skipped."""
    db: DbTarget = ctx.obj
    require_admin(db)
    with _service_errors():
        doc = load_standards_file(file)
        if dry_run:
            with open_uow(db, readonly=True) as uow:
                plan = plan_load(uow.conn(), doc)
            typer.echo(f"plan {doc.edition}")
            _counts(plan)
            return
        with open_uow(db) as uow:
            report = load_standards(uow, doc, actor=actor, source="cli")
    typer.echo(f"loaded {doc.edition}")
    _counts(report)


@app.command("ls")
def ls(
    ctx: typer.Context,
    kind: Annotated[
        str | None, typer.Option("--kind", help="code-list, mnemonic or pattern.")
    ] = None,
    include_closed: Annotated[
        bool, typer.Option("--all", help="Include superseded and retired entries.")
    ] = False,
) -> None:
    """List registry entries: kind, code, edition, lifecycle, label."""
    db: DbTarget = ctx.obj
    kinds = [_kind(kind)] if kind is not None else list(KINDS.values())
    rows: list[registry.StandardRow] = []
    with _service_errors(), open_uow(db, readonly=True) as uow:
        for stored in kinds:
            rows += registry.find_standards(
                uow.conn(), scope=COMPANY, kind=stored, active_only=not include_closed
            )
    names = {stored: name for name, stored in KINDS.items()}
    for row in rows:
        fields = [names[row.kind], row.code, row.edition, row.lifecycle, row.label]
        typer.echo("  ".join(fields))


@app.command("show")
def show(
    ctx: typer.Context,
    kind: _Kind,
    code: Annotated[str, typer.Argument(help="The entry's code, for example Area or FV.")],
) -> None:
    """Show one registry entry: its fields and, for a code list, how many values it has."""
    db: DbTarget = ctx.obj
    stored = _kind(kind)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        rows = registry.find_standards(uow.conn(), scope=COMPANY, kind=stored, code=code)
        if not rows:
            _fail(f"no {kind} {code!r} in the registry")
        row = rows[-1]
        count = 0
        if stored == "code_list":
            count = len(registry.code_values(uow.conn(), COMPANY, code))
    typer.echo(f"kind: {kind}")
    typer.echo(f"code: {row.code}")
    typer.echo(f"label: {row.label}")
    typer.echo(f"edition: {row.edition}")
    typer.echo(f"lifecycle: {row.lifecycle}")
    typer.echo(f"adoption: {row.adoption}")
    typer.echo(f"owner: {row.owner or '-'}")
    typer.echo(f"key: {row.key or '-'}")
    typer.echo(f"definition: {row.definition or '-'}")
    if stored == "code_list":
        typer.echo(f"value_list_policy: {row.value_list_policy}")
        typer.echo(f"values: {count}")
    if stored == "numbering_pattern":
        typer.echo(f"record_type: {row.data['record_type']}")
        typer.echo(f"template: {row.data['template']}")


@app.command("values")
def values(
    ctx: typer.Context,
    code_list: Annotated[str, typer.Argument(help="The code list, for example Area.")],
    project: _Project = None,
    include_all: Annotated[
        bool, typer.Option("--all", help="Include closed values and values outside their dates.")
    ] = False,
) -> None:
    """List a code list's values as a scope sees them: company values, then the project's own."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = codelists.values(
            uow.conn(), _scope(project), code_list, usable_only=not include_all
        )
    for item in found:
        fields = [item.code, item.label, item.origin, item.company_code or "-", item.lifecycle]
        typer.echo("  ".join(fields))


@app.command("add-value")
def add_value(
    ctx: typer.Context,
    code_list: Annotated[str, typer.Argument(help="The code list, for example Area.")],
    code: Annotated[str, typer.Argument(help="The new value's code.")],
    label: Annotated[str, typer.Option("--label", help="What the value is called.")],
    crosswalk: Annotated[
        str | None,
        typer.Option("--crosswalk", help="For a project value: the company value it maps to."),
    ] = None,
    meaning: Annotated[
        str | None, typer.Option("--meaning", help="IRI of the value's meaning.")
    ] = None,
    project: _Project = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Add a value to a code list: a company value (admin) or a project's own (any user)."""
    db: DbTarget = ctx.obj
    scope = _scope(project)
    if project is None:
        require_admin(db)
    with _service_errors(), open_uow(db) as uow:
        handle_add_code_value(
            uow,
            AddCodeValue(
                actor=actor,
                source="cli",
                scope=scope,
                code_list=code_list,
                code=code,
                label=label,
                crosswalk=crosswalk,
                meaning=meaning,
            ),
        )
        row = registry.find_code_value(uow.conn(), scope, code_list, code)
    if row is None:
        _fail(f"no value {code_list}.{code} in {scope}")
    typer.echo(f"added {code_list}.{code} origin={row.origin} crosswalk={row.crosswalk or '-'}")


@app.command("close")
def close(
    ctx: typer.Context,
    kind: _Kind,
    code: Annotated[str, typer.Argument(help="The entry's code.")],
    reason: _Reason,
    edition: Annotated[
        str | None, typer.Option("--edition", help="Which edition, when several are active.")
    ] = None,
    superseded_by: Annotated[
        str | None,
        typer.Option(
            "--superseded-by", help="The replacing entry's key, for example CL:Area@2.0.0."
        ),
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """End the life of a code list, mnemonic or numbering pattern (admin)."""
    db: DbTarget = ctx.obj
    require_admin(db)
    stored = _kind(kind)
    with _service_errors(), open_uow(db) as uow:
        active = registry.find_standards(
            uow.conn(), scope=COMPANY, kind=stored, code=code, active_only=True
        )
        if edition is not None:
            active = [r for r in active if r.edition == edition]
        if not active:
            _fail(f"no active {kind} {code!r}")
        if len(active) > 1:
            _fail(f"{kind} {code!r} has several active editions: use --edition")
        row = active[0]
        successor: str | None = None
        if superseded_by is not None:
            replacing = [
                r
                for r in registry.find_standards(uow.conn(), scope=COMPANY, kind=stored)
                if r.key == superseded_by
            ]
            if not replacing:
                _fail(f"no {kind} with key {superseded_by!r}")
            successor = replacing[0].id
        lifecycle = "superseded" if successor is not None else "retired"
        handle_close_standard(
            uow,
            CloseStandard(
                actor=actor,
                source="cli",
                scope=COMPANY,
                stream_id=row.id,
                lifecycle=lifecycle,
                superseded_by=successor,
                reason=reason,
            ),
        )
    typer.echo(f"closed {kind} {row.code} {row.edition} as {lifecycle}")


@app.command("close-value")
def close_value(
    ctx: typer.Context,
    code_list: Annotated[str, typer.Argument(help="The code list, for example Area.")],
    code: Annotated[str, typer.Argument(help="The value's code.")],
    reason: _Reason,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="The replacing value's code in the same list."),
    ] = None,
    project: _Project = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """End the life of a value of a code list: a company value (admin) or a project's own."""
    db: DbTarget = ctx.obj
    scope = _scope(project)
    if project is None:
        require_admin(db)
    with _service_errors(), open_uow(db) as uow:
        row = registry.find_code_value(uow.conn(), scope, code_list, code)
        if row is None:
            _fail(f"no value {code_list}.{code} in {scope}")
        other = None
        if superseded_by is not None:
            other = registry.find_code_value(uow.conn(), scope, code_list, superseded_by)
            if other is None:
                _fail(f"no value {code_list}.{superseded_by} in {scope}")
        lifecycle = "superseded" if other is not None else "retired"
        handle_close_code_value(
            uow,
            CloseCodeValue(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                lifecycle=lifecycle,
                superseded_by=other.id if other is not None else None,
                reason=reason,
            ),
        )
    typer.echo(f"closed value {code_list}.{code} as {lifecycle}")
