"""The `tl corr report` group: the register as CSV or JSON, responses due, and clocks (brief 9 M10).

Nothing is written to the ledger. The register export leaves out every item that is not
``internal`` unless the person names a class with ``--include-class`` (brief 18.10: a confidential
class is excluded from bulk exports unless an authorised export includes it; here the authorised
export is a document controller naming the class), and a person only ever gets what they may read
(ADR-0016), so naming a class never shows more than the signed-in person is cleared for. A cell
that a spreadsheet would run as a formula is written with a leading quote: the subject of a letter
is somebody else's text.
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_correspondence import views

from tl_cli.corr_clock import _line as clock_line
from tl_cli.doc import _fail, _Project, _service_errors
from tl_cli.session import require_controller

app = typer.Typer(help="Correspondence reports and exports.", no_args_is_help=True)

_PAGE = 500
_CLASSES = ("internal", "restricted", "privileged")
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
COLUMNS = (
    "number", "kind", "state", "direction", "domain", "subtype", "date", "counterparty",
    "response_due", "class", "subject",
)  # fmt: skip


def safe_cell(value: str | None) -> str:
    """``value`` as a spreadsheet cell: a text that starts like a formula gets a leading quote."""
    text = "" if value is None else value
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def _register(
    db: DbTarget, project: str, *, awaiting: bool, include_void: bool, domain: str | None
) -> list[views.RegisterLineView]:
    """Every line of the register the person may read, paged."""
    found: list[views.RegisterLineView] = []
    with _service_errors(), open_uow(db, readonly=True) as uow:
        while True:
            page = views.register(
                uow.conn(),
                f"project:{project}",
                domain=domain,
                awaiting_response=awaiting,
                include_void=include_void,
                limit=_PAGE,
                offset=len(found),
            )
            found.extend(page)
            if len(page) < _PAGE:
                return found


def _classes(db: DbTarget, include: Sequence[str] | None) -> set[str]:
    """The classes the export may carry; naming one above ``internal`` needs a controller."""
    wanted = {"internal", *(include or ())}
    unknown = wanted - set(_CLASSES)
    if unknown:
        _fail(f"unknown class {sorted(unknown)[0]!r}; the classes are {', '.join(_CLASSES)}")
    if wanted != {"internal"}:
        require_controller(db)
    return wanted


@app.command("register")
def register(
    ctx: typer.Context,
    project: _Project,
    out: Annotated[
        Path | None, typer.Option("--out", help="Write here instead of the screen.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="JSON instead of CSV.")] = False,
    include_class: Annotated[
        list[str] | None,
        typer.Option(
            "--include-class",
            help="Add restricted or privileged items (a document controller's export). Repeat.",
        ),
    ] = None,
    include_void: Annotated[bool, typer.Option("--all", help="Include void items.")] = False,
    domain: Annotated[str | None, typer.Option("--domain")] = None,
) -> None:
    """The master register as CSV (internal items unless --include-class says more)."""
    db: DbTarget = ctx.obj
    classes = _classes(db, include_class)
    lines = [
        line
        for line in _register(db, project, awaiting=False, include_void=include_void, domain=domain)
        if line.confidentiality in classes
    ]
    rows = [
        [
            line.number, line.kind, line.state, line.direction, line.domain, line.subtype,
            line.on, line.counterparty, line.response_due, line.confidentiality, line.subject,
        ]
        for line in lines
    ]  # fmt: skip
    handle = out.open("w", encoding="utf-8", newline="") if out is not None else sys.stdout
    try:
        if as_json:
            payload = [dict(zip(COLUMNS, row, strict=True)) for row in rows]
            handle.write(json.dumps(payload, indent=2) + "\n")
        else:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(COLUMNS)
            for row in rows:
                writer.writerow([safe_cell(cell) for cell in row])
    finally:
        if out is not None:
            handle.close()
    if out is not None:
        typer.echo(f"wrote {len(rows)} lines to {out}")


@app.command("due")
def due(
    ctx: typer.Context,
    project: _Project,
    within: Annotated[
        int | None, typer.Option("--within", min=0, help="Only answers due within N days.")
    ] = None,
) -> None:
    """Items that want an answer, earliest due first: number, due, days left, who, subject."""
    db: DbTarget = ctx.obj
    today = date.today()
    lines = _register(db, project, awaiting=True, include_void=False, domain=None)
    keyed: list[tuple[str, int | None, views.RegisterLineView]] = []
    for line in lines:
        if line.kind != "item" or line.state in ("Closed", "Void", "Responded"):
            continue
        left = (date.fromisoformat(line.response_due) - today).days if line.response_due else None
        if within is not None and (left is None or left > within):
            continue
        keyed.append((line.response_due or "9999-12-31", left, line))
    for due_on, left, line in sorted(keyed, key=lambda k: (k[0], k[2].number)):
        shown = "-" if left is None else str(left)
        typer.echo(
            f"{line.number} due {due_on if left is not None else '-'} left {shown} "
            f"{line.counterparty or '-'} {line.subject}"
        )


@app.command("clocks")
def clocks(
    ctx: typer.Context,
    project: _Project,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    all_clocks: Annotated[bool, typer.Option("--all", help="Include met and cancelled.")] = False,
) -> None:
    """The response clocks, soonest due first (the same lines as `tl corr clock ls`)."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = views.clock_views(uow.conn(), f"project:{project}", open_only=not all_clocks)
    if as_json:
        typer.echo(json.dumps([c.model_dump() for c in found], indent=2))
        return
    for clock in found:
        typer.echo(clock_line(clock))
