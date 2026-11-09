"""`tl awp export progress --period YYYY-Www [--project P] [--out FILE]` (P2-I5 S3).

Reads only. The CSV comes from ``tl_mod_awp.progress.export`` (formula-safe cells, the viewer's
class filter). ``--out`` writes a new file with mode 0600 and prints ``wrote <path> rows=<n>``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality
from tl_mod_awp.progress.export import ExportError, export_progress

from tl_cli.derive_support import Project, scope_of, service_errors


def _write_private(path: Path, data: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise typer.BadParameter(f"cannot write {path}: {exc.strerror}") from None
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)


def progress(
    ctx: typer.Context,
    project: Project,
    period: Annotated[str, typer.Option("--period", help="The period, YYYY-Www (ISO week).")],
    out: Annotated[
        Path | None, typer.Option("--out", help="Write here (mode 0600) instead of the screen.")
    ] = None,
) -> None:
    """Print earned progress by cost code as CSV (computed on read; nothing is stored).

    A bad period is `error: period: expected YYYY-Www`, exit 2.
    """
    db: DbTarget = ctx.obj
    viewer = confidentiality.current_viewer()
    try:
        with service_errors(), open_uow(db, readonly=True) as uow:
            data = export_progress(uow.conn(), scope_of(project), period, viewer=viewer)
    except ExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if out is None:
        typer.echo(data, nl=False)
        return
    _write_private(out, data)
    typer.echo(f"wrote {out} rows={max(data.count(chr(10)) - 1, 0)}")


def register(app: typer.Typer) -> None:
    """Add the `export` group (one verb, `progress`) to the awp command group."""
    group = typer.Typer(help="Exports.", no_args_is_help=True)
    group.command("progress")(progress)
    app.add_typer(group, name="export")
