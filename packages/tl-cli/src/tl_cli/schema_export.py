"""`tl schema export-git DIR [--package NAME]`: the published packages as files (P1-I8-T05a4b).

The files are what a git repository of the company's schema holds (company scope only; a
project's own packages are not exported): one `<package>@<version>.yaml`
per version in force (Published or Deprecated), the text exactly as it was drafted. Nothing else
is written: no report, no impact, no record text (the impact report names mappings and rules,
which are for administrators; FANOUT F9). It writes files on the host, so it is the
administrator's. Importing is `tl schema import-git` (P1-I8-T05a4c).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import registry
from tl_mod_schemareg.names import IN_FORCE
from tl_schema.packages import version_tuple

from tl_cli.derive_support import fail, service_errors
from tl_cli.session import require_admin

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def _file_name(row: registry.PackageRow) -> str:
    """The file name of a version; a name that could leave the directory is an error."""
    if _NAME.fullmatch(row.package) is None or _VERSION.fullmatch(row.version) is None:
        fail(f"{row.package}@{row.version} cannot be a file name")
    return f"{row.package}@{row.version}.yaml"


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file in the same directory."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")  # O_EXCL: no link
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o644)  # mkstemp makes 0600; a git checkout wants 0644
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def export_git(
    ctx: typer.Context,
    directory: Annotated[
        Path, typer.Argument(help="The directory to write to; made when missing.", file_okay=False)
    ],
    package: Annotated[
        str | None, typer.Option("--package", help="Only the versions of this package.")
    ] = None,
) -> None:
    """Write every published company-scope version as `<package>@<version>.yaml` into DIR (admin).

    Lines: `wrote <file>` or `unchanged <file>` (the file already holds the same text), in the
    order package name then version, then `exported <w> written, <u> unchanged to <DIR>`. With
    nothing to export: `nothing to export` (and DIR is not made). A file that exists with other
    text, or is a symbolic link, is `error: ...` (exit 1) and nothing is written.
    """
    db: DbTarget = ctx.obj
    require_admin(db)
    rows: list[registry.PackageRow] = []
    with service_errors(), open_uow(db, readonly=True) as uow:
        for state in IN_FORCE:
            offset = 0
            while True:
                page = registry.list_packages(
                    uow.conn(),
                    scope="company",
                    state=state,
                    package=package,
                    limit=registry.MAX_PAGE,
                    offset=offset,
                )
                rows.extend(page)
                if len(page) < registry.MAX_PAGE:
                    break
                offset += len(page)
        try:
            rows.sort(key=lambda row: (row.package, version_tuple(row.version)))
        except ValueError as exc:
            fail(str(exc))
    if not rows:
        typer.echo("nothing to export")
        return
    planned: list[tuple[registry.PackageRow, Path, bool]] = []
    texts: dict[str, str] = {}
    for row in rows:
        target = directory / _file_name(row)
        if target.name in texts:
            if texts[target.name] != row.content:
                fail(f"{target.name} would be written with two different texts")
            continue
        texts[target.name] = row.content
        if target.is_symlink():
            fail(f"{target.name} is a link")
        same = False
        if target.exists():
            if not target.is_file() or target.read_bytes() != row.content.encode("utf-8"):
                fail(f"{target.name} exists with other text")
            same = True
        planned.append((row, target, same))
    directory.mkdir(parents=True, exist_ok=True)
    written = 0
    unchanged = 0
    for row, target, same in planned:
        if same:
            unchanged += 1
            typer.echo(f"unchanged {target.name}")
            continue
        _write_atomic(target, row.content)
        written += 1
        typer.echo(f"wrote {target.name}")
    typer.echo(f"exported {written} written, {unchanged} unchanged to {directory}")


def register(app: typer.Typer) -> None:
    """Add the command to `tl schema`."""
    app.command("export-git")(export_git)
