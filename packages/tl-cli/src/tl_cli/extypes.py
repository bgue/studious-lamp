"""The `tl types` group: register, list, show and retire extension record types (brief 31).

Each subcommand parses options, makes one call into `tl_core.extypes`, and prints. The rules
(what a valid package is, what a conflict is, idempotence) live in the registry. A type is named
by its ref, `co.acme.LiftPlan@1.0.0`, which `ls` prints. Packages are directories
`<root>/<namespace>/<Name>/<version>/`; `sync` and `watch` read them, nothing here edits them
except `lock`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Annotated, NoReturn, cast

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core.extypes import registry
from tl_core.extypes.lock import write_lock
from tl_core.extypes.service import TypeDetail, type_detail
from tl_core.extypes.types import TypeIssue, TypeStatus, TypeView
from tl_core.extypes.validate import validate_package
from tl_core.extypes.watch import Change, watch
from tl_core.ledger import ConcurrencyError
from tl_core.schema_provider import get_provider
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork

app = typer.Typer(
    help="Extension record types: sync packages, list, show, validate, lock, deprecate.",
    no_args_is_help=True,
)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_STATUSES = ("active", "quarantined", "deprecated")


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _factory(db: Path) -> registry.UowFactory:
    """``factory(readonly)`` for the registry functions that open their own units of work."""

    def open_one(readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        return open_uow(db, readonly=readonly)

    return open_one


def issue_line(issue: TypeIssue) -> str:
    """``  example examples/bad.json: 'crane' is a required property``.

    Two spaces, ``issue.kind``, a space, ``issue.path`` (``-`` when ``None``), a colon, a space,
    ``issue.detail``.
    """
    path = "-" if issue.path is None else issue.path
    return f"  {issue.kind} {path}: {issue.detail}"


def type_line(view: TypeView) -> str:
    """``co.acme.LiftPlan@1.0.0  active  object-backed  lift_date,crane`` (two-space columns).

    The columns are the type ref, the status, the storage mode and the index fields joined by a
    comma. A quarantined type has no storage mode or index fields yet: both columns read ``-``,
    as does an empty index field list.
    """
    reg = view.registration
    if reg.status == "quarantined":
        mode, fields = "-", "-"
    else:
        mode = reg.storage_mode
        fields = ",".join(reg.index_fields) or "-"
    return f"{reg.type_ref}  {reg.status}  {mode}  {fields}"


def detail_lines(detail: TypeDetail) -> list[str]:
    """The lines `show` prints, in this order.

    ``type <type_ref>``, ``status <status>``, ``storage <storage_mode>`` (only when the status is
    not quarantined), ``owner <owner>`` (only when it is not empty), ``location <location_uri>``,
    ``content_hash <content_hash>``, ``schema_hash <schema_hash>`` (only when it is not empty);
    ``unavailable <reason>`` when ``detail.unavailable`` is set; then, when ``detail.form`` is not
    ``None``, a line ``fields`` followed by one line per field of ``form.fields()`` in order:
    ``  <name> <kind>`` plus `` required`` when required, `` multiple`` when multivalued and
    `` indexed`` when indexed (in that order); then, when ``detail.report`` is not empty, a line
    ``issues`` followed by ``issue_line(issue)`` for each.
    """
    reg = detail.registration
    lines = [f"type {reg.type_ref}", f"status {reg.status}"]
    if reg.status != "quarantined":
        lines.append(f"storage {reg.storage_mode}")
    if reg.owner:
        lines.append(f"owner {reg.owner}")
    lines.append(f"location {reg.location_uri}")
    lines.append(f"content_hash {reg.content_hash}")
    if reg.schema_hash:
        lines.append(f"schema_hash {reg.schema_hash}")
    if detail.unavailable is not None:
        lines.append(f"unavailable {detail.unavailable}")
    if detail.form is not None:
        lines.append("fields")
        for field in detail.form.fields():
            parts = [f"  {field.name} {field.kind}"]
            if field.required:
                parts.append("required")
            if field.multivalued:
                parts.append("multiple")
            if field.indexed:
                parts.append("indexed")
            lines.append(" ".join(parts))
    if detail.report:
        lines.append("issues")
        lines.extend(issue_line(issue) for issue in detail.report)
    return lines


def sync_lines(db: Path, root: Path, actor: str) -> list[str]:
    """Run ``registry.sync`` over ``root`` and return the lines to print.

    ``root`` must be a directory (``_fail`` with ``no such directory: <root>`` otherwise). Call
    ``registry.sync(_factory(db), root, actor=actor, source="cli")`` inside ``_service_errors``.
    For each returned view, in order: ``registered <type_ref>`` when its status is ``active`` and
    nothing was refused; ``conflict <type_ref> (kept <12 characters of the registered hash>)``
    followed by ``issue_line`` for each issue when the version is registered but its files changed
    (its entry in ``list_quarantined`` has a ``registered_hash``); otherwise ``quarantined
    <type_ref>`` followed by ``issue_line`` for each issue of that
    version's entry in ``registry.list_quarantined`` (read in a read-only unit of work). When
    nothing changed the only line is ``up to date (<n> packages)``, ``n = len(scan(root))``.
    """
    if not root.is_dir():
        _fail(f"no such directory: {root}")
    with _service_errors():
        views = registry.sync(_factory(db), root, actor=actor, source="cli")
        with open_uow(db, readonly=True) as uow:
            entries = {entry.type_ref: entry for entry in registry.list_quarantined(uow.conn())}
    if not views:
        return [f"up to date ({len(registry.scan(root))} packages)"]
    lines: list[str] = []
    for view in views:
        ref = view.registration.type_ref
        entry = entries.get(ref)
        if entry is not None and entry.registered_hash is not None:
            lines.append(f"conflict {ref} (kept {entry.registered_hash[:12]})")
        elif view.registration.status == "active":
            lines.append(f"registered {ref}")
            continue
        else:
            lines.append(f"quarantined {ref}")
        if entry is not None:
            lines.extend(issue_line(issue) for issue in entry.report)
    return lines


@app.command("sync")
def sync(
    ctx: typer.Context,
    root: Annotated[Path, typer.Argument(help="Directory of type packages.")],
    actor: _Actor = _DEFAULT_ACTOR,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit 1 when any registration is quarantined.")
    ] = False,
) -> None:
    """Register new or changed packages, quarantine invalid ones. Running it again is harmless.

    Print ``sync_lines(db, root, actor)``. With ``--strict``, afterwards read
    ``registry.list_quarantined`` (read-only unit of work); when there are entries print
    ``<n> quarantined`` to stderr and exit 1.
    """
    db: Path = ctx.obj
    for line in sync_lines(db, root, actor):
        typer.echo(line)
    if strict:
        with _service_errors(), open_uow(db, readonly=True) as uow:
            quarantined = len(registry.list_quarantined(uow.conn()))
        if quarantined:
            typer.echo(f"{quarantined} quarantined", err=True)
            raise typer.Exit(code=1)


@app.command("ls")
def ls(
    ctx: typer.Context,
    status: Annotated[
        str, typer.Option("--status", help="active, quarantined, deprecated or all.")
    ] = "all",
) -> None:
    """List registered types, by type ref. Nothing is printed when there are none.

    A ``status`` that is not ``all`` and not in ``_STATUSES``: ``_fail`` with ``--status must be
    active, quarantined, deprecated or all, not 'x'``. Read with ``registry.list_types(uow.conn(),
    status=...)`` in a read-only unit of work inside ``_service_errors`` (``status=None`` for
    ``all``) and print ``type_line(view)`` for each.
    """
    db: Path = ctx.obj
    if status != "all" and status not in _STATUSES:
        _fail(f"--status must be active, quarantined, deprecated or all, not {status!r}")
    chosen = None if status == "all" else cast(TypeStatus, status)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        views = registry.list_types(uow.conn(), status=chosen)
    for view in views:
        typer.echo(type_line(view))


@app.command("show")
def show(
    ctx: typer.Context,
    type_ref: Annotated[str, typer.Argument(help="For example co.acme.LiftPlan@1.0.0.")],
) -> None:
    """Show one registered version: its state, its fields, and why it was refused if it was."""
    db: Path = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        detail = type_detail(uow, type_ref)
    for line in detail_lines(detail):
        typer.echo(line)


@app.command("validate")
def validate(
    path: Annotated[
        Path, typer.Argument(help="A package directory.", exists=True, file_okay=False)
    ],
    root: Annotated[
        Path | None,
        typer.Option("--root", help="The type root, when PATH is not three levels below it."),
    ] = None,
) -> None:
    """Validate a package without registering it.

    ``validate_package(path, provider=get_provider(), root=root)``. When it is valid print
    ``ok <type_ref> <storage_mode> <n> index fields`` (``n`` = the number of index fields).
    Otherwise print ``issue_line(issue)`` for each issue and exit 1.
    """
    registration, issues = validate_package(path, provider=get_provider(), root=root)
    if registration is not None and not issues:
        typer.echo(
            f"ok {registration.type_ref} {registration.storage_mode} "
            f"{len(registration.index_fields)} index fields"
        )
        return
    for issue in issues:
        typer.echo(issue_line(issue))
    raise typer.Exit(code=1)


@app.command("lock")
def lock(
    path: Annotated[
        Path, typer.Argument(help="A package directory.", exists=True, file_okay=False)
    ],
) -> None:
    """Write `type.lock` for the files now in the package and print `content_hash <sha256>`.

    ``write_lock(path)``; a ``ValueError`` (a link or an oversized file in the package) is
    ``_fail`` with its message.
    """
    try:
        content_hash = write_lock(path)
    except ValueError as exc:
        _fail(str(exc))
    typer.echo(f"content_hash {content_hash}")


@app.command("deprecate")
def deprecate(
    ctx: typer.Context,
    type_ref: Annotated[str, typer.Argument(help="For example co.acme.LiftPlan@1.0.0.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the version is retired.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Retire a version: existing records stay, no new ones. Prints `deprecated <type_ref>`."""
    db: Path = ctx.obj
    with _service_errors():
        # registry.deprecate tells the schema provider after the commit (deprecate_type cannot)
        registry.deprecate(
            _factory(db), type_ref=type_ref, reason=reason, actor=actor, source="cli"
        )
    typer.echo(f"deprecated {type_ref}")


@app.command("watch")
def watch_command(
    ctx: typer.Context,
    root: Annotated[Path, typer.Argument(help="Directory of type packages.")],
    interval: Annotated[
        float, typer.Option("--interval", min=0.0, help="Seconds between polls.")
    ] = 2.0,
    actor: _Actor = _DEFAULT_ACTOR,
    max_cycles: Annotated[
        int | None, typer.Option("--max-cycles", min=1, help="Stop after this many polls.")
    ] = None,
) -> None:
    """Poll the root and sync whenever a package is added, edited or removed (Ctrl+C stops).

    ``root`` must be a directory (``_fail`` as in ``sync_lines``). Call
    ``watch(root, interval=interval, on_change=..., max_cycles=max_cycles)`` from
    ``tl_core.extypes.watch``. ``on_change(changes)`` prints ``changed <path> (<kind>)`` for each
    change, then every line of ``sync_lines(db, root, actor)``. A ``KeyboardInterrupt`` prints
    ``stopped`` and returns normally.
    """
    db: Path = ctx.obj
    if not root.is_dir():
        _fail(f"no such directory: {root}")

    def on_change(changes: list[Change]) -> None:
        for change in changes:
            typer.echo(f"changed {change.path} ({change.kind})")
        for line in sync_lines(db, root, actor):
            typer.echo(line)

    try:
        watch(root, interval=interval, on_change=on_change, max_cycles=max_cycles)
    except KeyboardInterrupt:
        typer.echo("stopped")
