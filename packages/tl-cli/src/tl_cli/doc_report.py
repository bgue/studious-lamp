"""The `tl doc report` group: the document-control base reports (brief 15; P1-I2-T11b).

Each subcommand reads through `tl_mod_documents.reports` and prints one line per row (or JSON with
`--json`). Nothing is written. The reports are: the document register, one document's revision
history, overdue reviews, the transmittal log and stale pinned revisions.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents import reports

from tl_cli.doc import _fail, _Project, _service_errors

app = typer.Typer(help="Document control reports.", no_args_is_help=True)

_Json = Annotated[bool, typer.Option("--json", help="Print JSON.")]
_On = Annotated[
    str | None,
    typer.Option("--on", help="Judge 'overdue' on this day (YYYY-MM-DD). Default today."),
]


def _day(value: str | None) -> date | None:
    """``value`` as a date, ``None`` when it is ``None``; anything else exits `error: ...`."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail(f"--on must be a date written YYYY-MM-DD, got {value!r}")


def _dump(lines: Sequence[Any]) -> None:
    typer.echo(json.dumps([asdict(line) for line in lines], indent=2))


@app.command("register")
def register(
    ctx: typer.Context,
    project: _Project,
    doc_type: Annotated[str | None, typer.Option("--type")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    as_json: _Json = False,
) -> None:
    """The document register: number, state, current revision, type, discipline, counts, title."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        lines = reports.document_register(
            uow.conn(),
            f"project:{project}",
            doc_type=doc_type,
            discipline=discipline,
            state=state,
        )
    if as_json:
        _dump(lines)
        return
    for line in lines:
        current = (
            "-" if line.current_code is None else f"{line.current_code}({line.current_status})"
        )
        fields = [
            line.number,
            line.state,
            current,
            line.doc_type or "-",
            line.discipline or "-",
            f"revisions={line.revisions}",
            f"open={line.open_code or '-'}",
            f"stale={line.stale_links}",
            line.title,
        ]
        typer.echo("  ".join(fields))


@app.command("history")
def history(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    as_json: _Json = False,
) -> None:
    """One document's revisions, oldest first, with renditions, transmittals and review outcome."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        lines = reports.revision_history(uow.conn(), f"project:{project}", number)
    if as_json:
        _dump(lines)
        return
    for line in lines:
        fields = [
            line.code,
            line.state,
            line.issue_status or "-",
            line.status_class or "-",
            line.issued_on or "-",
            "current" if line.is_current else "-",
            f"renditions={line.renditions}",
            f"transmittals={','.join(line.transmittals) or '-'}",
            f"review={line.review_outcome or '-'}",
            f"superseded_by={line.superseded_by or '-'}",
        ]
        typer.echo("  ".join(fields))


@app.command("overdue")
def overdue(ctx: typer.Context, project: _Project, on: _On = None, as_json: _Json = False) -> None:
    """Reviews still open and unanswered after their date: the revision, the cycle, the reviewer."""
    db: DbTarget = ctx.obj
    day = _day(on)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        lines = reports.overdue_reviews(uow.conn(), f"project:{project}", on=day)
    if as_json:
        _dump(lines)
        return
    for line in lines:
        fields = [
            f"{line.document_number}@{line.revision_code}",
            line.cycle_key,
            line.reviewer,
            f"due={line.due_date}",
            f"{line.days_overdue}d overdue",
        ]
        typer.echo("  ".join(fields))


@app.command("transmittals")
def transmittals(
    ctx: typer.Context,
    project: _Project,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    direction: Annotated[
        str | None, typer.Option("--direction", help="outgoing or incoming.")
    ] = None,
    on: _On = None,
    as_json: _Json = False,
) -> None:
    """The transmittal log: number, state, direction, purpose, dates, answer, items, overdue."""
    db: DbTarget = ctx.obj
    day = _day(on)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        lines = reports.transmittal_log(
            uow.conn(),
            f"project:{project}",
            state=state,
            direction=direction,
            on=day,
        )
    if as_json:
        _dump(lines)
        return
    for line in lines:
        fields = [
            line.number,
            line.state,
            line.direction,
            line.purpose,
            f"issued={line.issued_on or '-'}",
            f"due={line.due_date or '-'}",
            f"response={line.response_code or '-'}",
            f"items={line.items}",
        ]
        if line.overdue:
            fields.append("overdue")
        typer.echo("  ".join(fields))


@app.command("stale")
def stale(ctx: typer.Context, project: _Project, as_json: _Json = False) -> None:
    """Stale pinned revisions: the document, the pin, what is current, who links, the link id."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        lines = reports.stale_pins(uow.conn(), f"project:{project}")
    if as_json:
        _dump(lines)
        return
    for line in lines:
        fields = [
            line.document_number,
            f"pinned={line.pinned_code or '-'}",
            f"current={line.current_code or '-'}",
            f"newer={','.join(line.newer_codes) or '-'}",
            line.linked_key or "-",
            line.link_id,
        ]
        typer.echo("  ".join(fields))
