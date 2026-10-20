"""`tl schema import-git DIR [--dry-run]`: draft the packages a directory of files holds (T05a4c).

DIR is what `tl schema export-git` writes, or a git checkout of it: files `<package>@<version>.yaml`
directly in DIR. Each becomes a Draft package version, drafted by the signed-in person, exactly as
`tl schema package draft FILE` would; nothing is analysed, submitted or published. The files are
untrusted: only regular files are read (links are not followed), at most 200 of them, each at most
`MAX_CONTENT_BYTES`, and a file name must say what the file holds. One bad file stops the import
before anything is drafted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import analysis, registry
from tl_mod_schemareg.errors import InvalidSchemaPackageError
from tl_mod_schemareg.handlers.packages import DraftSchemaPackage, handle_draft_schema_package
from tl_mod_schemareg.limits import MAX_CONTENT_BYTES
from tl_schema.packages import PackageDoc, version_tuple

from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, acting, fail, service_errors
from tl_cli.session import require_session

MAX_FILES = 200


def _files(directory: Path) -> list[Path]:
    """The `*.yaml` entries directly in `directory`, by name (a link or folder is still listed)."""
    found = sorted(p for p in directory.iterdir() if p.name.endswith(".yaml"))
    if len(found) > MAX_FILES:
        fail(f"{directory} holds more than {MAX_FILES} package files")
    return found


def _read(path: Path) -> tuple[str | None, str | None]:
    """`(text, None)` for a usable file, `(None, problem)` for one that is not."""
    if path.is_symlink() or not path.is_file():
        return None, "is not a regular file"
    if path.stat().st_size > MAX_CONTENT_BYTES:
        return None, f"is larger than {MAX_CONTENT_BYTES} bytes"
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return None, "is not UTF-8 text"


def import_git(
    ctx: typer.Context,
    directory: Annotated[
        Path,
        typer.Argument(
            help="The directory of <package>@<version>.yaml files.",
            exists=True,
            file_okay=False,
            readable=True,
        ),
    ],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Say what would be drafted; draft nothing.")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Draft every package version in DIR that the registry does not hold yet.

    First every file is checked (nothing is drafted while any file has a problem). A problem is
    the line `problem <file> <reason>`: the reason is `is not a regular file`, `is larger than
    <n> bytes`, `is not UTF-8 text`, the module's message for a package that does not parse,
    `name does not match its package and version`, or `exists with other text` (the registry holds
    that version with other text). With a problem the last line is the summary and the exit code
    is 1.

    Then one line per package, by name and version: `unchanged <key>` (the registry holds this
    very text), `skipped <key> in force already` (the schema directory or a published version
    answers for it, so a draft is refused) or `drafted <key> <id>` (`would draft <key>` with
    `--dry-run`). The last line is
    `imported <d> drafted, <u> unchanged, <s> skipped, <p> problems`, or
    `dry run <d> to draft, <u> unchanged, <s> skipped, <p> problems`.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    problems: list[tuple[str, str]] = []
    triples: list[tuple[PackageDoc, str, str]] = []
    with service_errors(), open_uow(db, readonly=True) as uow:
        held = analysis.provider()
        for path in _files(directory):
            text, reason = _read(path)
            if text is None:
                problems.append((path.name, reason or "is not readable"))
                continue
            try:
                doc = analysis.parse_content(text)
            except InvalidSchemaPackageError as exc:
                problems.append((path.name, str(exc)))
                continue
            if path.name != f"{doc.package}@{doc.version}.yaml":
                problems.append((path.name, "name does not match its package and version"))
                continue
            row = registry.find_package(uow.conn(), doc.package, doc.version)
            if row is None:
                in_force = held.registry().origin(doc.package, doc.version) is not None
                state = "skipped" if in_force else "draft"
            elif row.content == text:
                state = "unchanged"
            else:
                problems.append((path.name, "exists with other text"))
                continue
            triples.append((doc, text, state))

    def tally(drafted: int, unchanged: int, skipped: int, bad: int) -> str:
        head = "dry run" if dry_run else "imported"
        verb = "to draft" if dry_run else "drafted"
        return f"{head} {drafted} {verb}, {unchanged} unchanged, {skipped} skipped, {bad} problems"

    if problems:
        for name, why in problems:
            typer.echo(f"problem {name} {why}")
        typer.echo(tally(0, 0, 0, len(problems)))
        raise typer.Exit(code=1)

    triples.sort(key=lambda t: (t[0].package, version_tuple(t[0].version)))
    for doc, text, state in triples:
        if state == "unchanged":
            typer.echo(f"unchanged {doc.key()}")
        elif state == "skipped":
            typer.echo(f"skipped {doc.key()} in force already")
        elif dry_run:
            typer.echo(f"would draft {doc.key()}")
        else:
            with service_errors(), open_uow(db) as uow:
                made = handle_draft_schema_package(
                    uow,
                    DraftSchemaPackage(
                        actor=acting(db, actor),
                        source=SOURCE,
                        scope="company",
                        content=text,
                    ),
                )
            typer.echo(f"drafted {doc.key()} {made.stream_id}")
    states = [state for _, _, state in triples]
    typer.echo(
        tally(
            states.count("draft"),
            states.count("unchanged"),
            states.count("skipped"),
            0,
        )
    )


def register(app: typer.Typer) -> None:
    """Add the command to `tl schema`."""
    app.command("import-git")(import_git)
