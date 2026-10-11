"""The `tl config` group: about:config on the command line (P0-I8-T01; brief 30.4).

Each subcommand parses options, makes one call into `tl_core.settings`, and prints. The rules (which
layer a key may be set at, locks and bounds, reasons, risk, schedules, history) live in the service.
`diff`, `export` and `import` are in `tl_cli.config_exchange`, added to this group at the bottom.
A layer is named `company`, `project:<id>` or `user:<id>`; the write commands take it as
`--company`, `--project <id>` or `--user <id>`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core import settings
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.settings.service import change_setting, lock_setting, revert_setting
from tl_core.settings.types import SettingChange
from tl_core.settings.values import format_value, normalise, parse_text
from tl_core.settings.views import SettingView, get_view, list_views

from tl_cli import config_exchange
from tl_cli.actors import refuse_agent

app = typer.Typer(
    help="about:config: read, set, reset, lock, diff, export and import settings.",
    no_args_is_help=True,
)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[
    str,
    typer.Option("--actor", help="Actor recorded on events.", callback=refuse_agent),
]
_Project = Annotated[str | None, typer.Option("--project", help="Project ID.")]
_User = Annotated[str | None, typer.Option("--user", help="User ID (UI keys only).")]
_Company = Annotated[bool, typer.Option("--company", help="The company layer.")]
_Reason = Annotated[str | None, typer.Option("--reason", help="Why (advanced and dangerous keys).")]
_Risk = Annotated[bool, typer.Option("--accept-risk", help="I accept the risk (dangerous keys).")]
_At = Annotated[
    str | None, typer.Option("--at", help="Take effect at this time (ISO 8601 with Z or offset).")
]
_MARK = "●"  # the "modified here" dot


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


def _layer(project: str | None, user: str | None, company: bool) -> str:
    chosen = [bool(project), bool(user), company]
    if sum(chosen) != 1:
        _fail("give exactly one of --company, --project and --user")
    if company:
        return "company"
    return f"project:{project}" if project else f"user:{user}"


def _when(text: str | None) -> datetime | None:
    if text is None:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        _fail("--at must be an ISO 8601 time with Z or an offset, such as 2026-11-01T08:00:00Z")
    if moment.tzinfo is None:
        _fail("--at must be an ISO 8601 time with Z or an offset, such as 2026-11-01T08:00:00Z")
    return moment


def _origin(view: SettingView) -> str:
    e = view.effective
    return f"{e.origin} {_MARK}" if e.modified_here else e.origin


def view_line(view: SettingView) -> str:
    """``feed.reactions.enabled  false  bool  project ●  locked`` (two-space columns).

    The columns are the key, the value as ``format_value(value, max_items=3)``, the definition's
    ``type``, the origin (``_origin(view)``: the layer name, followed by `` ●`` when the value is
    set at the layer being viewed) and ``locked`` or ``-``.
    """
    e = view.effective
    locked = "locked" if e.locked else "-"
    columns = (
        e.key,
        format_value(e.value, max_items=3),
        view.definition.type,
        _origin(view),
        locked,
    )
    return "  ".join(columns)


def detail_lines(view: SettingView) -> list[str]:
    """The lines `get --long` prints: ``key``, ``description``, ``value``, ``type``, ``origin``,
    ``default``, and then, only when they apply, ``risk`` (not normal), ``effect`` (not live),
    ``locked yes``, ``bounds <json>``, one ``scheduled <applies_at> <value> (seq <n>)`` per
    scheduled change and ``pending <effect>``. Each line is ``<name> <text>``.
    """
    defn = view.definition
    e = view.effective
    lines = [
        f"key {e.key}",
        f"description {defn.description}",
        f"value {format_value(e.value)}",
        f"type {defn.type}",
        f"origin {_origin(view)}",
        f"default {format_value(defn.default)}",
    ]
    if defn.risk != "normal":
        lines.append(f"risk {defn.risk}")
    if defn.effect != "live":
        lines.append(f"effect {defn.effect}")
    if e.locked:
        lines.append("locked yes")
    if e.bounds:
        lines.append(f"bounds {json.dumps(e.bounds, sort_keys=True, ensure_ascii=False)}")
    for change in e.scheduled:
        value = format_value(change.new_value)
        lines.append(f"scheduled {change.applies_at} {value} (seq {change.seq})")
    if e.pending_effect is not None:
        lines.append(f"pending {e.pending_effect}")
    return lines


def history_line(change: SettingChange) -> str:
    """``3  2026-10-10T09:00:00.000000Z  project:P1  30 -> 40  user:dev  field pilot``.

    Columns are separated by two spaces: ``seq``, ``recorded_at``, ``layer``, ``<old> -> <new>``
    (``format_value`` of each; the new side reads ``(reset)`` for a reset), ``actor`` and the reason
    or ``-``; a scheduled change ends with ``  applies <applies_at>``.
    """
    old = format_value(change.old_value)
    new = "(reset)" if change.reset else format_value(change.new_value)
    columns = (
        str(change.seq),
        change.recorded_at,
        change.layer,
        f"{old} -> {new}",
        change.actor,
        change.reason or "-",
    )
    line = "  ".join(columns)
    if change.applies_at is not None:
        line += f"  applies {change.applies_at}"
    return line


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project = None,
    user: _User = None,
    prefix: Annotated[
        str | None, typer.Option("--prefix", help="Only keys starting with this.")
    ] = None,
    modified: Annotated[
        bool, typer.Option("--modified", help="Only keys set at the layer being viewed.")
    ] = False,
) -> None:
    """List settings, sorted by key, as the project (and user) sees them.

    One line per setting: key, value, type, origin (` ●` after it when the
    value is set at the layer being viewed) and `locked` when the company
    locked the key.
    """
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        views = list_views(
            uow.conn(), project=project, user=user, prefix=prefix, modified_only=modified
        )
    for view in views:
        typer.echo(view_line(view))


@app.command("get")
def get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Setting key, e.g. feed.reactions.enabled.")],
    project: _Project = None,
    user: _User = None,
    long: Annotated[bool, typer.Option("--long", help="Origin, lock, schedule and more.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the value as JSON.")] = False,
) -> None:
    """Print the effective value of one key.

    --long adds the definition and state (origin, default, risk, lock,
    schedule, pending effect); --json prints the value as JSON.
    """
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        view = get_view(uow.conn(), key, project=project, user=user)
    if long:
        for line in detail_lines(view):
            typer.echo(line)
    elif as_json:
        typer.echo(json.dumps(view.effective.value, sort_keys=True, ensure_ascii=False))
    else:
        typer.echo(format_value(view.effective.value))


@app.command("history")
def history(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Setting key.")],
    layer: Annotated[
        str | None, typer.Option("--layer", help="company, project:<id> or user:<id>.")
    ] = None,
) -> None:
    """Print every change of a key, oldest first.

    One line per change: number, layer, time, actor, old and new value,
    reason. --layer narrows it to one layer.
    """
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        changes = settings.history(uow.conn(), key, layer=layer)
    for change in changes:
        typer.echo(history_line(change))


@app.command("set")
def set_(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Setting key.")],
    value: Annotated[str, typer.Argument(help="The new value, as text (lists: a,b or JSON).")],
    project: _Project = None,
    user: _User = None,
    company: _Company = False,
    reason: _Reason = None,
    accept_risk: _Risk = False,
    at: _At = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Set a key at a layer.

    Give exactly one of --company, --project and --user. Advanced and
    dangerous keys need --reason; dangerous keys also need --accept-risk.
    --at schedules the change for later. Prints `set`, `scheduled` or
    `unchanged` with the key, the layer and the value.
    """
    db: DbTarget = ctx.obj
    layer = _layer(project, user, company)
    applies_at = _when(at)
    with _service_errors(), open_uow(db) as uow:
        defn = settings.get_definition(key)
        typed = normalise(defn, parse_text(defn, value))
        outcome = change_setting(
            uow,
            key=key,
            layer=layer,
            value=typed,
            actor=actor,
            source="cli",
            reason=reason,
            accept_risk=accept_risk,
            applies_at=applies_at,
        )
    shown = json.dumps(typed, sort_keys=True, ensure_ascii=False)
    if not outcome.events:
        typer.echo(f"unchanged {key} {layer}")
    elif applies_at is not None:
        when = outcome.events[0].payload["applies_at"]
        typer.echo(f"scheduled {key} {layer} {shown} at {when}")
    else:
        typer.echo(f"set {key} {layer} {shown}")


@app.command("reset")
def reset(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Setting key.")],
    project: _Project = None,
    user: _User = None,
    company: _Company = False,
    reason: _Reason = None,
    accept_risk: _Risk = False,
    at: _At = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Reset a key at a layer so it inherits again.

    The layer, reason, risk and --at options are those of `set`.
    """
    db: DbTarget = ctx.obj
    layer = _layer(project, user, company)
    applies_at = _when(at)
    with _service_errors(), open_uow(db) as uow:
        outcome = change_setting(
            uow,
            key=key,
            layer=layer,
            reset=True,
            actor=actor,
            source="cli",
            reason=reason,
            accept_risk=accept_risk,
            applies_at=applies_at,
        )
    if not outcome.events:
        typer.echo(f"unchanged {key} {layer}")
    elif applies_at is not None:
        when = outcome.events[0].payload["applies_at"]
        typer.echo(f"scheduled reset {key} {layer} at {when}")
    else:
        typer.echo(f"reset {key} {layer}")


@app.command("lock")
def lock(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Setting key.")],
    reason: Annotated[str, typer.Option("--reason", help="Why; always required.")],
    unlock: Annotated[bool, typer.Option("--unlock", help="Remove the lock.")] = False,
    minimum: Annotated[
        str | None, typer.Option("--min", help="Smallest value for projects.")
    ] = None,
    maximum: Annotated[
        str | None, typer.Option("--max", help="Largest value for projects.")
    ] = None,
    choices: Annotated[
        str | None, typer.Option("--choices", help="Comma-separated values projects may use.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Lock a key for projects, or bound the values they may use.

    --unlock removes the lock; --min, --max and --choices bound project
    values. A reason is always required.
    """
    db: DbTarget = ctx.obj
    bounds: dict[str, Any] = {}
    with _service_errors(), open_uow(db) as uow:
        defn = settings.get_definition(key)
        if minimum is not None:
            bounds["minimum"] = parse_text(defn, minimum)
        if maximum is not None:
            bounds["maximum"] = parse_text(defn, maximum)
        if choices is not None:
            bounds["choices"] = [part.strip() for part in choices.split(",") if part.strip()]
        done = lock_setting(
            uow,
            key=key,
            locked=not unlock,
            bounds=bounds or None,
            actor=actor,
            source="cli",
            reason=reason,
        )
    line = f"locked {key}" if done.locked else f"unlocked {key}"
    if done.bounds:
        line += f" bounds {json.dumps(done.bounds, sort_keys=True)}"
    typer.echo(line)


@app.command("revert")
def revert(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Setting key.")],
    layer: Annotated[str, typer.Option("--layer", help="company, project:<id> or user:<id>.")],
    seq: Annotated[int, typer.Option("--seq", min=1, help="Change number from `history`.")],
    reason: _Reason = None,
    accept_risk: _Risk = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Undo the latest change of a key at a layer.

    --seq is the change number from `history`. Only the latest change at
    that layer can be undone; to go further back, set the value again.
    """
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db) as uow:
        done = revert_setting(
            uow,
            key=key,
            layer=layer,
            seq=seq,
            actor=actor,
            source="cli",
            reason=reason,
            accept_risk=accept_risk,
        )
    typer.echo(f"reverted {key} {layer} to {format_value(done.value)}")


app.add_typer(config_exchange.app)
