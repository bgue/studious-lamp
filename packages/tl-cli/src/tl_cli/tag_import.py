"""`tl tag import`: preview and apply a legacy tag list (brief 9 M2, 29.6; P1-I1-T10c).

The command reads a CSV file with a mapping template, compares it with the project's tags and
prints what would change; with `--apply` it writes the plan. Reading, comparing and writing are the
module's (`tl_mod_engineering.imports`); this command parses options and prints. It is registered
by `tl_cli.main` as `tl tag import`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_mod_engineering.errors import ImportApplyError
from tl_mod_engineering.imports.apply import apply_plan, ended_numbers, existing_tags
from tl_mod_engineering.imports.diff import plan_import
from tl_mod_engineering.imports.mapping import MappingError, load_mapping, read_rows
from tl_mod_engineering.imports.model import ImportPlan

from tl_cli.session import require_admin

_DEFAULT_ACTOR = "user:dev"


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a mapping, import, service or input failure into `error:` on stderr, exit 1.

    An import that cannot be applied prints one `  - <problem>` line per row problem.
    """
    try:
        yield
    except ImportApplyError as exc:
        typer.echo(f"error: {exc}", err=True)
        for problem in exc.problems:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=1) from exc
    except MappingError as exc:
        _fail(str(exc))
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _show(value: Any) -> str:
    """A value as a person reads it in a diff: ``-`` for none, JSON for the rest (4.0 as 4)."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "-" if value is None else json.dumps(value, sort_keys=True)


def _preview(plan: ImportPlan) -> None:
    """The counts line and one line per new, changed, removed and invalid row.

    ``new=2  changed=1  unchanged=2  removed=1  invalid=1`` and then, in this order:
    ``+ <number>  <class or ->  <service or ->`` for each new row,
    ``~ <number>  <field>: <old> -> <new>`` joined by ``; `` for each changed row,
    ``- <number>`` for each tag not in the file, and ``! line <n>: <problems joined by "; ">``
    for each invalid row.
    """
    counts = plan.counts()
    typer.echo("  ".join(f"{name}={counts[name]}" for name in counts))
    for row in plan.new:
        typer.echo(f"+ {row.number}  {row.class_code or '-'}  {row.service or '-'}")
    for change in plan.changed:
        fields = "; ".join(f"{c.field}: {_show(c.old)} -> {_show(c.new)}" for c in change.changes)
        typer.echo(f"~ {change.number}  {fields}")
    for tag in plan.removed:
        typer.echo(f"- {tag.number}")
    for row in plan.invalid:
        typer.echo(f"! line {row.line}: {'; '.join(row.problems)}")


def import_tags(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="The CSV file to import.")],
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    mapping: Annotated[
        Path, typer.Option("--mapping", help="The mapping template (YAML) for this file.")
    ],
    apply: Annotated[
        bool, typer.Option("--apply", help="Write the changes. Without it nothing is written.")
    ] = False,
    skip_invalid: Annotated[
        bool, typer.Option("--skip-invalid", help="Import the valid rows and leave the others out.")
    ] = False,
    job: Annotated[
        str | None, typer.Option("--job", help="Names the import in the history (default: file).")
    ] = None,
    actor: Annotated[
        str, typer.Option("--actor", help="Actor recorded on events.")
    ] = _DEFAULT_ACTOR,
) -> None:
    """Compare a tag list with the project's tags; with --apply, create and update them."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    job = job or file.stem
    if apply:
        require_admin(db)  # an import keeps numbers that break the pattern: an admin's decision
    with _service_errors():
        template = load_mapping(mapping)
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _fail(f"{file.name}: cannot read file: {exc}")
        rows = read_rows(text, template)
        typer.echo(f"import {template.name} {file.name} into project {project}")
        with open_uow(db, readonly=not apply) as uow:
            plan = plan_import(
                rows,
                existing_tags(uow.conn(), scope),
                ended=ended_numbers(uow.conn(), scope),
            )
            _preview(plan)
            if not apply:
                typer.echo("dry run: nothing written; add --apply to write")
                return
            result = apply_plan(
                uow,
                scope,
                plan,
                actor=actor,
                source=f"import:{job}",
                reason=f"import {job}",
                skip_invalid=skip_invalid,
            )
    typer.echo(
        f"applied {job}: created={result.created}  changed={result.changed}"
        f"  skipped={result.skipped}"
    )
