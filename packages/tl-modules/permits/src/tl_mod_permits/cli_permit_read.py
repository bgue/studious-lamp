"""`tl permit ls|show|board|export`: the permit register reads (P2-PTW-T05).

None of these writes anything. Every verb first checks the access word `permits.view` on the
project for the invoking actor (`--actor`, default the dev actor), before any permit is read; a
refusal is `error: forbidden: ...`. The reads go through ``tl_mod_permits.views`` with the
session's viewer, so a hidden permit is absent from a list, its total, a board and a show, and
answers the same as a missing key. The CLI prints the fields the views return and queries nothing
itself. Each command reads the clock once (``tl_core.util.utcnow``) and passes it to the views.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer
from sqlalchemy import Connection
from tl_adapters.db import DbTarget, open_uow
from tl_cli.derive_support import DEV_ACTOR, acting, cell, fail, scope_of, service_errors
from tl_cli.session import session_viewer
from tl_core import util
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.confidentiality import Viewer
from tl_core.uow import UnitOfWork

from tl_mod_permits import MODULE, views
from tl_mod_permits.cli import permit_app
from tl_mod_permits.iso_views import GasRow, gas_export_rows, gas_tests_for
from tl_mod_permits.names import PERMIT_TYPES, VIEW

#: The most rows `ls` prints by default.
LIST_LIMIT = 200
#: The widest label column of a `show` block (tui-layout: longest label plus two, at most 24).
LABEL_WIDTH = 24

Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
Actor = Annotated[
    str,
    typer.Option("--actor", help="The actor whose access words gate the read (default dev)."),
]
State = Annotated[
    str | None, typer.Option("--state", help="A shown state, for example Active or Lapsed.")
]
PermitType = Annotated[
    str | None, typer.Option("--type", help="A permit type, for example hot_work.")
]
Area = Annotated[str | None, typer.Option("--area", help="Only this area.")]
Holder = Annotated[str | None, typer.Option("--holder", help="Only this holder.")]


def require_view(uow: UnitOfWork, scope: str, actor: str) -> None:
    """The entry check of every permit read: ``actor`` holds ``permits.view`` on the project.

    The word is a role gate, so a refusal is `error: forbidden: ...` and does not hide anything.
    """
    try:
        require_word(
            uow.conn(),
            holder_for_actor(uow.conn(), actor),
            scope=scope,
            module=MODULE,
            word=normalise_word(VIEW),
            what=VIEW,
        )
    except ForbiddenError as exc:
        fail(f"forbidden: {exc}")


def enter(db: DbTarget, scope: str, actor: str) -> Viewer:
    """Check the actor (``acting``) and the view word, then return the viewer the reads use."""
    checked = acting(db, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        require_view(uow, scope, checked)
    return session_viewer(db)


def _choice(value: str | None, choices: tuple[str, ...], param: str) -> None:
    if value is not None and value not in choices:
        raise typer.BadParameter(f"must be one of {', '.join(choices)}", param_hint=f"'{param}'")


def _when(value: datetime | None) -> str | None:
    """A time as `YYYY-MM-DD HH:MM UTC`, or None."""
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _every_row(
    conn: Connection,
    scope: str,
    *,
    now: datetime,
    viewer: Viewer,
    filters: dict[str, str | None],
) -> list[views.PermitRow]:
    """Every permit the filters and the viewer leave, read a page at a time (no silent cut)."""
    rows: list[views.PermitRow] = []
    while True:
        page = views.permit_list(
            conn,
            scope,
            now=now,
            state=filters["state"],
            permit_type=filters["permit_type"],
            area=filters["area"],
            holder=filters["holder"],
            limit=views.MAX_LIMIT,
            offset=len(rows),
            viewer=viewer,
        )
        rows.extend(page.rows)
        if not page.rows or len(rows) >= page.total:
            return rows


def permit_ls(
    ctx: typer.Context,
    project: Project,
    actor: Actor = DEV_ACTOR,
    state: State = None,
    permit_type: PermitType = None,
    area: Area = None,
    holder: Holder = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=views.MAX_LIMIT, help="The most rows to list."),
    ] = LIST_LIMIT,
) -> None:
    """List the permits of the project by key, then `n of total`.

    Columns: key, subject, state, type, area, holder, valid until, for. `-` for none.
    """
    _choice(state, views.SHOWN_STATES, "--state")
    _choice(permit_type, PERMIT_TYPES, "--type")
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    now = util.utcnow()
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = views.permit_list(
            uow.conn(),
            scope,
            now=now,
            state=state,
            permit_type=permit_type,
            area=area,
            holder=holder,
            limit=limit,
            viewer=viewer,
        )
    typer.echo("key  subject  state  type  area  holder  valid until  for")
    for r in page.rows:
        typer.echo(
            f"{r.key}  {cell(r.subject, 50)}  {r.state}  {r.permit_type}  {cell(r.area, 64)}  "
            f"{cell(r.holder, 120)}  {cell(_when(r.valid_until))}  {cell(r.for_key)}"
        )
    typer.echo(f"{len(page.rows)} of {page.total}")


def _detail_lines(found: views.PermitDetail) -> list[tuple[str, str | None]]:
    """The labelled values of a `show`; the caller leaves out the None and empty ones."""
    r = found.row
    return [
        ("Subject", r.subject),
        ("State", r.state),
        ("Type", r.permit_type),
        ("Area", r.area),
        ("Location", found.location_text),
        ("Holder", r.holder),
        ("Description", found.description),
        ("For", r.for_key),
        ("Requested by", found.requested_by),
        ("Needed from", found.needed_from),
        ("Needed until", found.needed_until),
        ("Approved by", found.approved_by),
        ("Issued by", found.issued_by),
        ("Issued", _when(r.issued_at)),
        ("Valid until", _when(r.valid_until)),
        ("Revalidations", str(r.revalidation_count)),
        ("Closed by", r.closed_by),
        ("Precautions", ", ".join(found.precautions) or None),
        ("Suspend reason", found.suspend_reason),
        ("Handback note", found.handback_note),
        ("Reject reason", found.reject_reason),
        ("Cancel reason", found.cancel_reason),
        ("Version", str(found.version)),
    ]


def permit_show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The permit key, for example P123-PTW-0001.")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show one permit. An absent, hidden or other-project permit is `error: no permit <KEY>`."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    now = util.utcnow()
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.permit_detail(uow.conn(), scope, key, now=now, viewer=viewer)
    if found is None:
        fail(f"no permit {key}")
    shown = [(label, value) for label, value in _detail_lines(found) if value not in (None, "")]
    width = min(max(len(label) for label, _ in shown) + 2, LABEL_WIDTH)
    typer.echo(f"permit {found.row.key}")
    for label, value in shown:
        typer.echo(f"{label.ljust(width)}{cell(value, 300)}")


def permit_board(
    ctx: typer.Context,
    project: Project,
    actor: Actor = DEV_ACTOR,
    area: Area = None,
) -> None:
    """The live permits by area: the counts by shown state, then one block per area.

    A block is `area <name>` (no area last, as `-`), then one row per permit: key, type, holder,
    valid until, state.
    """
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    now = util.utcnow()
    with service_errors(), open_uow(db, readonly=True) as uow:
        board = views.permit_board(uow.conn(), scope, area, now=now, viewer=viewer)
    typer.echo("  ".join(f"{name} {count}" for name, count in board.counts.items()))
    for block in board.areas:
        typer.echo(f"area {cell(block.area)}")
        for r in block.rows:
            typer.echo(
                f"{r.key}  {r.permit_type}  {cell(r.holder, 120)}  "
                f"{cell(_when(r.valid_until))}  {r.state}"
            )


def permit_export(
    ctx: typer.Context,
    project: Project,
    fmt: Annotated[str, typer.Option("--format", help="csv or jsonl.")],
    actor: Actor = DEV_ACTOR,
    state: State = None,
    permit_type: PermitType = None,
    area: Area = None,
    holder: Holder = None,
    gas_tests: Annotated[
        bool,
        typer.Option(
            "--gas-tests", help="Export the gas tests of those permits, one row per test."
        ),
    ] = False,
) -> None:
    """Export the permits of the project, with the filters of `ls`, as csv or jsonl to stdout."""
    if fmt not in views.EXPORT_FORMATS:
        raise typer.BadParameter("must be csv or jsonl", param_hint="'--format'")
    _choice(state, views.SHOWN_STATES, "--state")
    _choice(permit_type, PERMIT_TYPES, "--type")
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    now = util.utcnow()
    filters: dict[str, str | None] = {
        "state": state,
        "permit_type": permit_type,
        "area": area,
        "holder": holder,
    }
    with service_errors(), open_uow(db, readonly=True) as uow:
        rows = _every_row(uow.conn(), scope, now=now, viewer=viewer, filters=filters)
        tests: list[GasRow] = []
        if gas_tests:
            for row in rows:
                tests.extend(gas_tests_for(uow.conn(), row.id, viewer=viewer))
    if gas_tests:
        typer.echo(gas_export_rows(tests, fmt), nl=False)
        return
    typer.echo(views.export_rows(rows, fmt), nl=False)


permit_app.command("ls")(permit_ls)
permit_app.command("show")(permit_show)
permit_app.command("board")(permit_board)
permit_app.command("export")(permit_export)
