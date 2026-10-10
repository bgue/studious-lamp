"""The `tl config` group: about:config on the command line (P0-I8-T01; brief 30.4).

Each subcommand parses options, makes one call into `tl_core.settings`, and prints. The rules (which
layer a key may be set at, locks and bounds, reasons, risk, schedules, history) live in the service.
`diff`, `export` and `import` are in `tl_cli.config_exchange`, added to this group at the bottom.
A layer is named `company`, `project:<id>` or `user:<id>`; the write commands take it as
`--company`, `--project <id>` or `--user <id>`.

STUB (P0-I8-T01): `view_line`, `detail_lines`, `history_line` and the seven commands raise
NotImplementedError. Names, signatures and docstrings are final; implement the bodies, then delete
this paragraph.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.settings.types import SettingChange
from tl_core.settings.views import SettingView

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

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


def detail_lines(view: SettingView) -> list[str]:
    """The lines `get --long` prints: ``key``, ``description``, ``value``, ``type``, ``origin``,
    ``default``, and then, only when they apply, ``risk`` (not normal), ``effect`` (not live),
    ``locked yes``, ``bounds <json>``, one ``scheduled <applies_at> <value> (seq <n>)`` per
    scheduled change and ``pending <effect>``. Each line is ``<name> <text>``.

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


def history_line(change: SettingChange) -> str:
    """``3  2026-10-10T09:00:00.000000Z  project:P1  30 -> 40  user:dev  field pilot``.

    Columns are separated by two spaces: ``seq``, ``recorded_at``, ``layer``, ``<old> -> <new>``
    (``format_value`` of each; the new side reads ``(reset)`` for a reset), ``actor`` and the reason
    or ``-``; a scheduled change ends with ``  applies <applies_at>``.

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


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
    """List settings, sorted by key, as the project (and user) sees them. Prints `view_line`s.

    In a read-only unit of work (``open_uow(db, readonly=True)`` inside ``_service_errors``) call
    ``list_views(uow.conn(), project=project, user=user, prefix=prefix, modified_only=modified)``
    and print ``view_line(view)`` for each result (nothing for an empty list).

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


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

    Read-only unit of work inside ``_service_errors``, ``get_view(uow.conn(), key, project=project,
    user=user)``. Then print: with ``--long`` each of ``detail_lines(view)``; else with ``--json``
    ``json.dumps(view.effective.value, sort_keys=True, ensure_ascii=False)``; else
    ``format_value(view.effective.value)``.

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


@app.command("history")
def history(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Setting key.")],
    layer: Annotated[
        str | None, typer.Option("--layer", help="company, project:<id> or user:<id>.")
    ] = None,
) -> None:
    """Print every change of a key, oldest first, as `history_line`s.

    Read-only unit of work inside ``_service_errors``, ``settings.history(uow.conn(), key,
    layer=layer)``; print ``history_line(change)`` for each (nothing when there are none).

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


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

    ``layer = _layer(project, user, company)`` and ``applies_at = _when(at)`` first. Then, in a
    write unit of work (``open_uow(db)``) inside ``_service_errors``: ``defn =
    settings.get_definition(key)``, ``typed = normalise(defn, parse_text(defn, value))`` and
    ``outcome = change_setting(uow, key=key, layer=layer, value=typed, actor=actor,
    source="cli", reason=reason, accept_risk=accept_risk, applies_at=applies_at)``.
    ``shown = json.dumps(typed, sort_keys=True, ensure_ascii=False)``. Print
    ``unchanged <key> <layer>`` when ``outcome.events`` is empty; else when ``applies_at`` was
    given ``scheduled <key> <layer> <shown> at <outcome.events[0].payload["applies_at"]>``;
    else ``set <key> <layer> <shown>``.

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


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

    ``layer`` and ``applies_at`` as for ``set``. Write unit of work inside ``_service_errors``,
    ``outcome = change_setting(uow, key=key, layer=layer, reset=True, actor=actor, source="cli",
    reason=reason, accept_risk=accept_risk, applies_at=applies_at)``. Print
    ``unchanged <key> <layer>`` when ``outcome.events`` is empty; else when ``applies_at`` was
    given ``scheduled reset <key> <layer> at <outcome.events[0].payload["applies_at"]>``; else
    ``reset <key> <layer>``.

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


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
    """Lock a key for projects (``--unlock`` removes it) and/or bound their values.

    Write unit of work inside ``_service_errors``. ``defn = settings.get_definition(key)``;
    ``bounds`` is a dict that gets ``"minimum": parse_text(defn, minimum)`` and ``"maximum":
    parse_text(defn, maximum)`` when those options are given and ``"choices"`` (the
    comma-separated words, stripped, empty ones dropped) when ``--choices`` is given. Then
    ``done = lock_setting(uow, key=key, locked=not unlock, bounds=bounds or None, actor=actor,
    source="cli", reason=reason)``. Print ``locked <key>`` (``unlocked <key>`` when
    ``done.locked`` is false) followed, only when ``done.bounds`` is set, by `` bounds `` and
    ``json.dumps(done.bounds, sort_keys=True)``.

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


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
    """Undo one change of the key's history.

    Write unit of work inside ``_service_errors``, ``done = revert_setting(uow, key=key,
    layer=layer, seq=seq, actor=actor, source="cli", reason=reason, accept_risk=accept_risk)``.
    Print ``reverted <key> <layer> to <format_value(done.value)>``.

    STUB (P0-I8-T01): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T01)")


app.add_typer(config_exchange.app)
