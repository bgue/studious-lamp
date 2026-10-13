"""The `tl doc report` group: the document-control base reports (brief 15; P1-I2-T11b).

Each subcommand reads through `tl_mod_documents.reports` and prints one line per row (or JSON with
`--json`). Nothing is written. The reports are: the document register, one document's revision
history, overdue reviews, the transmittal log and stale pinned revisions.

STUB (P1-I2-T11b): the bodies of the five commands raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

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
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.document_register(uow.conn(), f"project:{project}", doc_type=doc_type,
    #    discipline=discipline, state=state).
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: number, state, current (`<code>(<status>)` from
    #    current_code and current_status, or "-"), doc_type or "-", discipline or "-",
    #    f"revisions={revisions}", f"open={open_code or '-'}", f"stale={stale_links}", title.
    raise NotImplementedError


@app.command("history")
def history(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    as_json: _Json = False,
) -> None:
    """One document's revisions, oldest first, with renditions, transmittals and review outcome."""
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.revision_history(uow.conn(), f"project:{project}", number). An unknown number
    #    raises a ServiceError that _service_errors prints as `error: ...`.
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: code, state, issue_status or "-", status_class or
    #    "-", issued_on or "-", "current" or "-" (is_current), f"renditions={renditions}",
    #    f"transmittals={','.join(transmittals) or '-'}", f"review={review_outcome or '-'}",
    #    f"superseded_by={superseded_by or '-'}".
    raise NotImplementedError


@app.command("overdue")
def overdue(ctx: typer.Context, project: _Project, on: _On = None, as_json: _Json = False) -> None:
    """Reviews still open and unanswered after their date: the revision, the cycle, the reviewer."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; day = _day(on) (final helper).
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.overdue_reviews(uow.conn(), f"project:{project}", on=day).
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: f"{document_number}@{revision_code}", cycle_key,
    #    reviewer, f"due={due_date}", f"{days_overdue}d overdue".
    raise NotImplementedError


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
    # STEPS
    # 1. db: DbTarget = ctx.obj; day = _day(on).
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.transmittal_log(uow.conn(), f"project:{project}", state=state,
    #    direction=direction, on=day).
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: number, state, direction, purpose,
    #    f"issued={issued_on or '-'}", f"due={due_date or '-'}", f"response={response_code or
    #    '-'}", f"items={items}", and the word "overdue" last only when `overdue` is true.
    raise NotImplementedError


@app.command("stale")
def stale(ctx: typer.Context, project: _Project, as_json: _Json = False) -> None:
    """Stale pinned revisions: the document, the pin, what is current, who links, the link id."""
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.stale_pins(uow.conn(), f"project:{project}").
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: document_number, f"pinned={pinned_code or '-'}",
    #    f"current={current_code or '-'}", f"newer={','.join(newer_codes) or '-'}",
    #    f"{linked_key or '-'}", link_id.
    raise NotImplementedError
