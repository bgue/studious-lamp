"""`tl qr` (P2-QR-T07): the scan-code verbs, one call into the module each.

The hook ref `tl_mod_qr.cli:qr_app` names the group `qr`. Verbs: `label` (issue a code and write its
label file), `ls` and `export` (the register rows, never a code or a hash), `revoke` and `rotate`
(by register id), `resolve` (a code from standard input, or a prompt; the card or `no such code`).
The rules live in ``service``, ``views``, ``labels`` and ``resolve``; this file parses options,
runs one unit of work and prints. No output carries a code, except the grouped print in a label
file. Reads use the signed-in viewer (``session_viewer``); writes use the actor's viewer, as
``tl punch`` does.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from sqlalchemy import Connection
from tl_adapters.db import DbTarget, open_uow
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_command, session_viewer
from tl_core import confidentiality as cf
from tl_core.confidentiality import Viewer
from tl_core.services.commands import Command
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork

from tl_mod_qr import labels, service, views
from tl_mod_qr.commands import IssueScanCode, RevokeScanCode, RotateScanCode
from tl_mod_qr.names import SCAN_CODE_ISSUED
from tl_mod_qr.resolve import resolve as resolve_code
from tl_mod_qr.views import CodeRow

qr_app = typer.Typer(no_args_is_help=True)

#: The formats of `export`.
FORMATS = ("csv", "jsonl")
#: The one text of every resolve miss (unknown, revoked, expired, hidden, no view word).
MISS = "no such code"
#: The environment variable that serves the scan web client (tl_api.settings).
WEB_VAR = "TL_WEB"
SIZE_HELP = "The label size: tag (card and sheet are not available yet)."
OUTPUT = typer.Option("-o", "--output", help="The label file to write (one HTML page).")
FORCE = typer.Option("--force", help="Replace the label file if it exists.")
REASON = typer.Option("--reason", help="Why the code is revoked or replaced.")


def _model[C: Command](model: type[C], **fields: Any) -> C:
    """The command model with ``fields``; a value the model refuses is a usage error (exit 2)."""
    try:
        return model(**fields)
    except ValidationError as exc:
        raise typer.BadParameter(str(exc.errors()[0]["msg"])) from None


def _day(value: str | None) -> date | None:
    """A ``YYYY-MM-DD`` day, or None when not given; anything else is a usage error."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter("must be YYYY-MM-DD", param_hint="'--expires'") from None


def _record_id(uow: UnitOfWork, scope: str, key: str, viewer: Viewer) -> str:
    """The id of the record ``key`` names, as ``viewer`` reads it; a hidden or absent record is
    `error: no record <key>`, the same text."""
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None:
        fail(f"no record {key}")
    return str(row["id"])


def _refuse_existing(out: Path, force: bool) -> None:
    """Refuse before anything is issued: an existing label file is kept unless ``--force``."""
    if out.exists() and not force:
        fail(f"{out} exists; give --force to replace it")


def _warn_web() -> None:
    """A label scans to the web client; say so when the variable that serves it is not set."""
    if not os.environ.get(WEB_VAR, "").strip():
        typer.echo(f"warning: {WEB_VAR} is not set; the scan page is not served", err=True)


def _label_page(
    conn: Connection,
    project: str,
    code: str,
    target_id: str,
    label_text: str | None,
    size: str,
    viewer: Viewer,
) -> tuple[str, bool]:
    """The label page for ``code`` and whether its QR was drawn (False: the note is printed).

    The printed text is ``label_text`` when given, else the record's title as ``viewer`` reads it.
    """
    # service.py reads the setting the same way (and the S2 tests patch this name).
    base = str(service.value_of(conn, service.BASE_URL, project=project) or "")  # pyright: ignore[reportPrivateImportUsage]
    url = labels.label_url(base, code)
    svg = labels.make_svg(url)
    text = label_text
    if text is None:
        text = labels.label_fields(conn, target_id, viewer).text
    page = labels.render_label(code=code, text=text, size=size, svg=svg)
    return page, svg is not None


def _write_label(out: Path, page: str, force: bool) -> None:
    """Write the label file after the unit of work committed."""
    _refuse_existing(out, force)
    out.write_text(page, encoding="utf-8")


def _echo_label(verb: str, register_id: str, out: Path, drawn: bool) -> None:
    """One output line: the register id and the file; a note when the QR could not be drawn."""
    note = "" if drawn else "  no QR drawn: the labels extra is not installed"
    typer.echo(f"{verb} {register_id}  file {out}{note}")


# --- label, rotate, revoke ------------------------------------------------------------------------


@qr_app.command("label")
def qr_label(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The record key the label is for.")],
    project: Project,
    out: Annotated[Path, OUTPUT],
    label_text: Annotated[
        str | None, typer.Option("--label", help="The text under the code (at most 40 characters).")
    ] = None,
    size: Annotated[str, typer.Option("--size", help=SIZE_HELP)] = "tag",
    expires: Annotated[
        str | None, typer.Option("--expires", help="The last day the code scans, YYYY-MM-DD.")
    ] = None,
    force: Annotated[bool, FORCE] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Issue a scan code for a record and write its label file. Prints `label <id>  file <path>`.

    The code is printed only in the file. Without `--label` the record's title is the text.
    """
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)
    _refuse_existing(out, force)
    _warn_web()
    expiry = _day(expires)
    try:
        with service_errors(), open_uow(db) as uow:
            conn = uow.conn()
            viewer = cf.viewer_for_actor(conn, who)
            target = _record_id(uow, scope, key, viewer)
            cmd = _model(
                IssueScanCode,
                actor=who,
                source=SOURCE,
                scope=scope,
                target_id=target,
                label_text=label_text,
                size=size,
                expires_on=expiry,
            )
            require_command(uow, cmd)
            issued = service.issue(uow, cmd)
            page, drawn = _label_page(conn, project, issued.code, target, label_text, size, viewer)
    except labels.LabelError as exc:
        fail(str(exc))
    _write_label(out, page, force)
    _echo_label("label", issued.result.stream_id, out, drawn)


@qr_app.command("rotate")
def qr_rotate(
    ctx: typer.Context,
    code_id: Annotated[str, typer.Argument(help="The register id of the code (from `ls`).")],
    project: Project,
    reason: Annotated[str, REASON],
    out: Annotated[Path, OUTPUT],
    force: Annotated[bool, FORCE] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Revoke a code and issue its replacement (same record, label, size and expiry).

    Writes the new label file and prints `rotated <new id>  file <path>`.
    """
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)
    _refuse_existing(out, force)
    _warn_web()
    try:
        with service_errors(), open_uow(db) as uow:
            conn = uow.conn()
            cmd = _model(
                RotateScanCode,
                actor=who,
                source=SOURCE,
                scope=scope,
                code_id=code_id,
                reason=reason,
            )
            require_command(uow, cmd)
            issued = service.rotate(uow, cmd)
            made = next(e for e in issued.result.events if e.event_type == SCAN_CODE_ISSUED)
            target = str(made.payload["target_id"])
            kept = made.payload["label_text"]
            page, drawn = _label_page(
                conn,
                project,
                issued.code,
                target,
                None if kept is None else str(kept),
                str(made.payload["size"]),
                cf.viewer_for_actor(conn, who),
            )
    except labels.LabelError as exc:
        fail(str(exc))
    _write_label(out, page, force)
    _echo_label("rotated", issued.result.stream_id, out, drawn)


@qr_app.command("revoke")
def qr_revoke(
    ctx: typer.Context,
    code_id: Annotated[str, typer.Argument(help="The register id of the code (from `ls`).")],
    project: Project,
    reason: Annotated[str, REASON],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Revoke a code. Prints `revoked <id>`; the code then answers `no such code`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)
    with service_errors(), open_uow(db) as uow:
        cmd = _model(
            RevokeScanCode, actor=who, source=SOURCE, scope=scope, code_id=code_id, reason=reason
        )
        require_command(uow, cmd)
        result = service.revoke(uow, cmd)
    typer.echo(f"revoked {result.stream_id}")


# --- ls, export, resolve --------------------------------------------------------------------------


def _rows(db: DbTarget, project: str, key: str, actor: str) -> list[CodeRow]:
    """The register rows of the record ``key``, as the signed-in viewer reads it."""
    acting(db, actor)
    viewer = session_viewer(db)
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        target = _record_id(uow, scope, key, viewer)
        return views.codes_for_record(uow.conn(), target, viewer=viewer)


@qr_app.command("ls")
def qr_ls(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The record key.")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """List the scan codes of a record: id, label, size, state, issued by and at, expires.

    `scan codes: <n>`, then one line per code. A code is never printed.
    """
    rows = _rows(ctx.obj, project, key, actor)
    typer.echo(f"scan codes: {len(rows)}")
    for r in rows:
        typer.echo(
            f"{r.id}  {cell(r.label_text, 40)}  {r.size}  {r.state}  {cell(r.issued_by, 120)}  "
            f"{cell(r.issued_at)}  {cell(r.expires_on)}"
        )


@qr_app.command("export")
def qr_export(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The record key.")],
    project: Project,
    fmt: Annotated[str, typer.Option("--format", help="csv or jsonl.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Export the rows `ls` shows, as CSV or JSON lines. Never a code or a hash."""
    if fmt not in FORMATS:
        raise typer.BadParameter(f"must be one of {', '.join(FORMATS)}", param_hint="'--format'")
    rows = _rows(ctx.obj, project, key, actor)
    kind = "csv" if fmt == "csv" else "jsonl"
    typer.echo(views.export_rows(rows, kind), nl=False)


def _read_code() -> str:
    """The code from standard input when it is not a terminal, else a hidden prompt."""
    if sys.stdin.isatty():
        return typer.prompt("Code", hide_input=True).strip()
    return sys.stdin.readline().strip()


@qr_app.command("resolve")
def qr_resolve(
    ctx: typer.Context,
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Resolve a code (from standard input) to its status card, as the signed-in viewer reads it.

    Prints the banner, the key, the title, the lines and `as of <time>`. Every miss prints
    `no such code` and exits 1.
    """
    db: DbTarget = ctx.obj
    acting(db, actor)
    scope_of(project)
    code = _read_code()
    viewer = session_viewer(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        card = resolve_code(uow.conn(), code, viewer)
    if card is None:
        typer.echo(MISS)
        raise typer.Exit(code=1)
    typer.echo(card.banner)
    typer.echo(f"key  {card.key}")
    typer.echo(card.title)
    for line in card.lines:
        typer.echo(f"{line.label}  {line.value}")
    typer.echo(f"as of {card.as_of.isoformat()}")
