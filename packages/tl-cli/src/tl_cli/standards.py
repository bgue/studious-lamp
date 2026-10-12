"""The `tl standards` group: load and read the company standards registry (brief 6.4; P1-I1-T09a).

Each subcommand parses options, makes one call into `tl_mod_engineering` (the loader, a handler or
a read) and prints. The rules (code-list policies, supersession, what the registry may hold) live
in the module. The registry is company data: every command that changes it needs the admin role,
except adding a value to a code list in a project (`add-value --project`), which any signed-in user
may do when the list's policy allows it.

STUB (P1-I1-T09a): the bodies of the commands raise NotImplementedError; their signatures, options
and docstrings and the helpers (`_service_errors`, `_kind`, `_scope`, `_counts`) are final. Each
body has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the
`ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)` (it exits with its own error line).
    # 2. Inside `with _service_errors():` doc = load_standards_file(file).
    # 3. With --dry-run: `with open_uow(db, readonly=True) as uow:` report = plan_load(uow.conn(),
    #    doc); print f"plan {doc.edition}"; call _counts(report); return.
    # 4. Otherwise `with open_uow(db) as uow:` report = load_standards(uow, doc, actor=actor,
    #    source="cli"); after the block print f"loaded {doc.edition}" and call _counts(report).
    raise NotImplementedError


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
    # STEPS
    # 1. kinds = [_kind(kind)] when --kind is given, else all three values of KINDS in the order
    #    code_list, mnemonic, numbering_pattern.
    # 2. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` for each kind
    #    rows += registry.find_standards(uow.conn(), scope=COMPANY, kind=k,
    #    active_only=not include_closed).
    # 3. Print one line per row with two spaces between the columns: the *CLI* kind name (the key
    #    of KINDS whose value is row.kind), row.code, row.edition, row.lifecycle, row.label.
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    kind: _Kind,
    code: Annotated[str, typer.Argument(help="The entry's code, for example Area or FV.")],
) -> None:
    """Show one registry entry: its fields and, for a code list, how many values it has."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` rows =
    #    registry.find_standards(uow.conn(), scope=COMPANY, kind=_kind(kind), code=code); if none,
    #    _fail(f"no {kind} {code!r} in the registry"). row = the last one (the newest edition).
    #    For a code list also count = len(registry.code_values(uow.conn(), COMPANY, code)).
    # 2. Print `name: value` lines in this order: kind (the CLI name as typed), code, label,
    #    edition, lifecycle, adoption, owner ("-" when None), key ("-" when None), definition
    #    ("-" when None).
    # 3. A code list also prints `value_list_policy: <policy>` and `values: <count>`; a numbering
    #    pattern prints `record_type: <data["record_type"]>` and `template: <data["template"]>`.
    raise NotImplementedError


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
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` found =
    #    codelists.values(uow.conn(), _scope(project), code_list, usable_only=not include_all).
    # 2. Print one line per value, columns separated by two spaces: code, label, origin,
    #    company_code ("-" when None), lifecycle.
    raise NotImplementedError


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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; scope = _scope(project); without --project call
    #    `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` handle_add_code_value(uow,
    #    AddCodeValue(actor=actor, source="cli", scope=scope, code_list=code_list, code=code,
    #    label=label, crosswalk=crosswalk, meaning=meaning)); then row =
    #    registry.find_code_value(uow.conn(), scope, code_list, code).
    # 3. Print f"added {code_list}.{code} origin={row.origin} crosswalk={row.crosswalk or '-'}".
    raise NotImplementedError


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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`; stored = _kind(kind).
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` active = registry.find_standards(
    #    uow.conn(), scope=COMPANY, kind=stored, code=code, active_only=True); with --edition keep
    #    the rows whose edition equals it. None left: _fail(f"no active {kind} {code!r}"); more than
    #    one: _fail(f"{kind} {code!r} has several active editions: use --edition"). row = the one.
    # 3. successor = None; with --superseded-by find the row among
    #    registry.find_standards(uow.conn(), scope=COMPANY, kind=stored) whose key equals it and
    #    use its id; no such row: _fail(f"no {kind} with key {superseded_by!r}").
    # 4. handle_close_standard(uow, CloseStandard(actor=actor, source="cli", scope=COMPANY,
    #    stream_id=row.id, lifecycle="superseded" if successor else "retired",
    #    superseded_by=successor, reason=reason)).
    # 5. After the block print f"closed {kind} {row.code} {row.edition} as {lifecycle}".
    raise NotImplementedError


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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; scope = _scope(project); without --project call
    #    `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` row = registry.find_code_value(
    #    uow.conn(), scope, code_list, code); none: _fail(f"no value {code_list}.{code} in
    #    {scope}"). With --superseded-by other = registry.find_code_value(uow.conn(), scope,
    #    code_list, superseded_by); none: _fail(f"no value {code_list}.{superseded_by} in
    #    {scope}").
    # 3. handle_close_code_value(uow, CloseCodeValue(actor=actor, source="cli", scope=scope,
    #    stream_id=row.id, lifecycle="superseded" if other else "retired",
    #    superseded_by=other.id if other else None, reason=reason)).
    # 4. After the block print f"closed value {code_list}.{code} as {lifecycle}".
    raise NotImplementedError
