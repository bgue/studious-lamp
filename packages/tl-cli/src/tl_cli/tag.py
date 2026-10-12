"""The `tl tag` group: create, show, list and change engineering tags (brief 9 M2; P1-I1-T09b).

Each subcommand parses options, makes one call into `tl_mod_engineering` (a handler or a read) and
prints. The rules (the numbering pattern, the class, the supersession of a rename) live in the
module. Tags are named by number.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.services.psets import conformance
from tl_core.uow import UnitOfWork
from tl_mod_engineering import registry
from tl_mod_engineering.errors import InvalidTagNumberError
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    MergeTags,
    ReclassifyTag,
    RenameTag,
    SplitTag,
    handle_create_tag,
    handle_merge_tags,
    handle_reclassify_tag,
    handle_rename_tag,
    handle_split_tag,
)

from tl_cli.pset import parse_assignment

app = typer.Typer(help="Create, show and change engineering tags.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1.

    A tag number the pattern refuses prints one `  - <segment>: <message>` line per problem.
    """
    try:
        yield
    except InvalidTagNumberError as exc:
        typer.echo(f"error: {exc}", err=True)
        for issue in exc.issues:
            where = issue["segment"] or "number"
            typer.echo(f"  - {where}: {issue['message']} ({issue['level']})", err=True)
        raise typer.Exit(code=1) from exc
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _tag(uow: UnitOfWork, scope: str, project: str, number: str) -> registry.TagRow:
    found = registry.find_tag(uow.conn(), scope, number)
    if found is None:
        _fail(f"no tag {number!r} in project {project!r}")
    return found


def _segments_text(row: registry.TagRow) -> str:
    if not row.segments:
        return "-"
    return " ".join(f"{name}={value}" for name, value in row.segments.items())


def _issue_lines(uow: UnitOfWork, tag_id: str) -> list[str]:
    report = conformance(uow, tag_id)
    return [f"issue {i.level} {i.path} {i.rule}: {i.message}" for i in report.issues]


def _psets(items: list[str] | None) -> dict[str, dict[str, Any]]:
    """``["valve_data.size_in=4"]`` becomes ``{"valve_data": {"size_in": 4}}``."""
    found: dict[str, dict[str, Any]] = {}
    for item in items or []:
        path, value = parse_assignment(item)
        pset, separator, prop = path.partition(".")
        if not separator or not prop or prop.startswith("x.") or pset in ("prj", "x"):
            _fail(f"expected PSET.PROPERTY=VALUE for a standard property, got {item!r}")
        found.setdefault(pset, {})[prop] = value
    return found


def _show_created(uow: UnitOfWork, scope: str, project: str, number: str, stream_id: str) -> None:
    row = _tag(uow, scope, project, number)
    typer.echo(f"created {stream_id}")
    typer.echo(f"tag {row.number}")
    typer.echo(f"class {row.class_code or '-'}")
    typer.echo(f"segments {_segments_text(row)}")
    typer.echo(f"number_status {row.number_status}")
    typer.echo(f"conformance {row.conformance}")
    for line in _issue_lines(uow, row.id):
        typer.echo(line)


@app.command("create")
def create(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number, for example 47-FV-1001.")],
    project: _Project,
    class_code: Annotated[
        str | None, typer.Option("--class", help="Tag class code, for example ControlValve.")
    ] = None,
    service: Annotated[
        str | None, typer.Option("--service", help="Service description (the title).")
    ] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    pset: Annotated[
        list[str] | None,
        typer.Option("--pset", help="PSET.PROPERTY=VALUE (JSON when it parses); repeatable."),
    ] = None,
    allow_violation: Annotated[
        bool,
        typer.Option(
            "--allow-violation", help="Store a number that breaks the pattern, as a violation."
        ),
    ] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Create a tag. The number must fit the registry numbering pattern."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        result = handle_create_tag(
            uow,
            CreateTag(
                actor=actor,
                source="cli",
                scope=scope,
                number=number,
                class_code=class_code,
                service=service,
                description=description,
                psets=_psets(pset),
                pattern_policy="record" if allow_violation else "enforce",
            ),
        )
        _show_created(uow, scope, project, number, result.stream_id)


@app.command("show")
def show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number.")],
    project: _Project,
) -> None:
    """Show a tag: its parts, its class, what it lacks, its values."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = _tag(uow, scope, project, number)
        issues = _issue_lines(uow, row.id)
    typer.echo(f"id: {row.id}")
    typer.echo(f"number: {row.number}")
    typer.echo(f"title: {row.title}")
    typer.echo(f"class: {row.class_code or '-'}")
    typer.echo(f"status: {row.status or '-'}")
    typer.echo(f"area: {row.area or '-'}")
    typer.echo(f"mnemonic: {row.mnemonic or '-'}")
    typer.echo(f"sequence: {'-' if row.sequence is None else row.sequence}")
    typer.echo(f"pattern: {row.pattern_code or '-'}")
    typer.echo(f"number_status: {row.number_status}")
    typer.echo(f"origin: {row.origin}")
    typer.echo(f"conformance: {row.conformance}")
    typer.echo(f"version: {row.version}")
    typer.echo(f"segments: {_segments_text(row)}")
    for violation in row.violations:
        where = violation["segment"] or "number"
        typer.echo(f"violation {violation['level']} {where}: {violation['message']}")
    for line in issues:
        typer.echo(line)
    typer.echo("psets: " + json.dumps(row.psets, sort_keys=True, separators=(",", ":")))


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    class_code: Annotated[str | None, typer.Option("--class")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    mnemonic: Annotated[str | None, typer.Option("--mnemonic")] = None,
    area: Annotated[str | None, typer.Option("--area")] = None,
    number_status: Annotated[
        str | None, typer.Option("--number-status", help="ok or violation.")
    ] = None,
    include_ended: Annotated[
        bool, typer.Option("--all", help="Include superseded and deleted tags.")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=5000)] = 1000,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON list.")] = False,
) -> None:
    """List a project's tags by number: number, class, status, conformance, title."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        rows = registry.list_tags(
            uow.conn(),
            scope,
            class_code=class_code,
            status=status,
            mnemonic=mnemonic,
            area=area,
            number_status=number_status,
            include_ended=include_ended,
            limit=limit,
        )
    if as_json:
        items = [
            {
                "number": row.number,
                "class_code": row.class_code,
                "status": row.status,
                "conformance": row.conformance,
                "title": row.title,
                "number_status": row.number_status,
            }
            for row in rows
        ]
        typer.echo(json.dumps(items, indent=2))
        return
    for row in rows:
        fields = [row.number, row.class_code or "-", row.status or "-", row.conformance, row.title]
        typer.echo("  ".join(fields))


@app.command("reclassify")
def reclassify(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number.")],
    project: _Project,
    class_code: Annotated[str, typer.Option("--class", help="The new tag class code.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Move a tag to another class; the new class binds its own property sets."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _tag(uow, scope, project, number)
        handle_reclassify_tag(
            uow,
            ReclassifyTag(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                class_code=class_code,
                reason=reason,
            ),
        )
        after = _tag(uow, scope, project, number)
    typer.echo(f"reclassified {number} {row.class_code or '-'} -> {after.class_code}")
    typer.echo(f"conformance {after.conformance}")


@app.command("rename")
def rename(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number to replace.")],
    new_number: Annotated[str, typer.Argument(help="The new tag number.")],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace a tag by a new one with another number; the old tag is superseded."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _tag(uow, scope, project, number)
        made = handle_rename_tag(
            uow,
            RenameTag(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                new_number=new_number,
                reason=reason,
            ),
        )
    typer.echo(f"renamed {number} -> {new_number}")
    typer.echo(f"created {made.stream_id}")


@app.command("split")
def split(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number to replace.")],
    new_numbers: Annotated[list[str], typer.Argument(help="Two or more new tag numbers.")],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace a tag by several; the old tag is superseded."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _tag(uow, scope, project, number)
        made_list = handle_split_tag(
            uow,
            SplitTag(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                new_numbers=new_numbers,
                reason=reason,
            ),
        )
    typer.echo(f"split {number} -> " + ", ".join(new_numbers))
    for made in made_list:
        typer.echo(f"created {made.stream_id}")


@app.command("merge")
def merge(
    ctx: typer.Context,
    numbers: Annotated[list[str], typer.Argument(help="Two or more tag numbers to replace.")],
    project: _Project,
    into: Annotated[str, typer.Option("--into", help="The new tag number.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace several tags by one; the new tag takes the values of the first number."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        rows = [_tag(uow, scope, project, n) for n in numbers]
        made = handle_merge_tags(
            uow,
            MergeTags(
                actor=actor,
                source="cli",
                scope=scope,
                stream_ids=[r.id for r in rows],
                new_number=into,
                reason=reason,
            ),
        )
    typer.echo(f"merged {', '.join(numbers)} -> {into}")
    typer.echo(f"created {made.stream_id}")
