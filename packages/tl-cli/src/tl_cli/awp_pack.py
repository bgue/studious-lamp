"""`tl awp iwp pack NUMBER`: the work pack of one IWP as one HTML file (P2-I5-T07a).

The file is created with mode 0600 and replaces one already there. Reads go through the session's
viewer; a missing or hidden IWP is `error: no IWP <n>` and writes nothing. With `--attach` the
file is stored in the IWP's file slot `pack` (the same upload path a person's upload takes).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp.pack import build_pack_data, render_html

from tl_cli.corr import upload
from tl_cli.derive_support import (
    DEV_ACTOR,
    Actor,
    Project,
    acting,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import session_viewer

#: The file slot of an IWP that holds its pack.
PACK_SLOT = "pack"


def iwp_pack(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    out: Annotated[
        Path | None, typer.Option("--out", help="The HTML file. Default <number>.html here.")
    ] = None,
    attach: Annotated[
        bool, typer.Option("--attach", help="Also store the file in the IWP's pack slot.")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Write the work pack of an IWP as one HTML file. Prints `pack <number>  <bytes> bytes  qr
    <yes|no>`, then `note: <text>` lines, then `slot pack  file <id>` with --attach."""
    db: DbTarget = ctx.obj
    target = out if out is not None else Path(f"{number}.html")
    with service_errors(), open_uow(db, readonly=True) as uow:
        try:
            data = build_pack_data(uow.conn(), scope_of(project), number, session_viewer(db))
        except RecordNotFoundError:
            fail(f"no IWP {number}")
        page = render_html(data)
    payload = page.html.encode("utf-8")
    if target.exists() or target.is_symlink():
        target.unlink()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
    typer.echo(f"pack {number}  {len(payload)} bytes  qr {'yes' if page.qr else 'no'}")
    for note in page.notes:
        typer.echo(f"note: {note}")
    if attach:
        with service_errors():
            file_id = upload(
                db, scope_of(project), acting(db, actor), data.iwp_id, PACK_SLOT, target
            )
        typer.echo(f"slot {PACK_SLOT}  file {file_id}")


def register(iwp_app: typer.Typer) -> None:
    """Add the pack verb to the ``iwp`` group of ``tl awp``."""
    iwp_app.command("pack")(iwp_pack)
