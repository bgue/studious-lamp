# P0-I8-T01 — `tl config ls|get|history|set|reset|lock|revert`

Status: ready
Tier: haiku
Labels: cli
Depends on: — (the settings service is on the base)
Branch: `p0/i8a-t01-cli-config`

## Goal
The `tl config` command group exists for reading and changing settings: `ls` lists every setting as a project sees it, `get` prints one effective value, `history` lists a key's changes, `set` and `reset` change a key at a layer (optionally scheduled), `lock` locks a key for projects or bounds their values, and `revert` undoes a change. Each subcommand parses options, makes one call into `tl_core.settings`, and prints. The module has the option declarations, the helpers and the wiring in `main.py`; `view_line`, `detail_lines`, `history_line` and the seven commands raise `NotImplementedError`. A provided test file (26 tests) must pass.

## Brief references (pasted)
> **30.2 Layers and resolution.** `platform default -> company -> project -> user (UI keys only)`. The **effective value** shows its origin. Values set at the current scope are marked ● (like about:config's "modified"). A company can **lock** a key, so projects cannot override it, or constrain the range projects may use.
> **30.3 Change control.** Every change is a `Setting.Changed` event: old value, new value, actor, reason (required for `advanced` and `dangerous` keys), and effective time. **Scheduled changes** take effect at a future time. **Dangerous keys** need explicit confirmation ("I accept the risk"). Changes apply live. Full per-key history, with revert.
> **30.4 Interfaces.** CLI: `tl config get | set | reset | lock | diff | export | import`. API: `/settings` endpoints. MCP: `get_settings` (read), `propose_setting_change` (draft for human approval). Export/import as YAML for templates and reviews.

### Specification
The stub's docstrings give the exact steps and output of each command; `view_line`, `detail_lines` and `history_line` format the lines. The provided test checks all of it. `ctx.obj` is the ledger path (`Path`), set by the root callback. A layer is `company`, `project:<id>` or `user:<id>`; the write commands take it as exactly one of `--company`, `--project`, `--user` (`_layer` checks that). The default actor is `user:dev`, the source is `cli`. The service does the checking (types, ranges, layers, locks, bounds, reasons, risk, secrets); the CLI prints its message after `error: ` and exits 1 (`_service_errors` does that). The ● is the character U+25CF (`_MARK`).

`tl config diff|export|import` are ticket T02 (`config_exchange.py`, already wired in at the bottom of `config.py`); do not touch them.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails on this base (four extension-type event types are not catalogued yet; workstream B owns that). It is the only expected failure of a whole-repo run. Do not touch it.
- `typer.testing.CliRunner` catches exceptions and returns them on the result: a CLI test that only checks "nothing changed" passes against a crash. The provided tests assert `exit_code` and `exception`.
- ruff's autofix removed the imports the stub does not use; add back the ones listed under *Imports to add* below.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/config.py` (the stub you complete):
```python
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
```
```python
# imports to add to config.py (the stub's autofix removed them):
import json
from pathlib import Path
from tl_adapters.sqlite.uow import open_uow
from tl_core import settings
from tl_core.settings.service import change_setting, lock_setting, revert_setting
from tl_core.settings.values import format_value, normalise, parse_text
from tl_core.settings.views import SettingView, get_view, list_views
```
```python
# tl_core.settings (already implemented; read-only for you)
# types:   EffectiveSetting(key, value, origin, modified_here, locked, bounds, scheduled[ScheduledChange(applies_at, new_value, seq)], pending_effect)
#          SettingDefinition(key, type, default, description, docs, scopes, lockable, validation, effect, sensitivity, risk, since, deprecated, owner)
#          SettingChange(seq, key, layer, old_value, new_value, reset, actor, reason, recorded_at, applies_at)
# views:   SettingView(definition, effective); list_views(conn, *, project=None, user=None, prefix=None, modified_only=False) -> list[SettingView]
#          get_view(conn, key, *, project=None, user=None) -> SettingView            # UnknownSettingError
# service: change_setting(uow, *, key, layer, value=None, reset=False, actor, source, reason=None, accept_risk=False, applies_at=None) -> Outcome(effective, events, version)
#          lock_setting(uow, *, key, locked, bounds, actor, source, reason) -> EffectiveSetting
#          revert_setting(uow, *, key, layer, seq, actor, source, reason=None, accept_risk=False) -> EffectiveSetting
#          settings.history(conn, key, *, layer=None) -> list[SettingChange];  settings.get_definition(key) -> SettingDefinition
# values:  parse_text(defn, text) -> value;  normalise(defn, value) -> value (InvalidSettingValueError);  format_value(value, *, max_items=None) -> str
# Errors (all ServiceError, the message is for people): UnknownSettingError, InvalidSettingValueError, SettingScopeError, SettingLockedError,
#   SettingOutOfBoundsError, ReasonRequiredError, RiskNotAcceptedError, SettingNotLockableError, SettingChangeNotFoundError
# tl_adapters.sqlite.uow.open_uow(path, *, readonly=False) -> context manager yielding a UnitOfWork (uow.conn() is the connection)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/config.py`
- `packages/tl-cli/src/tl_cli/proposal.py` (style: `_service_errors`, `_fail`, `open_uow`, options)
- `docs/tickets/P0-I8/provided/t01-test_cli_config.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/config.py` (edit)
- `packages/tl-cli/tests/test_cli_config.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T01.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t01-test_cli_config.py.txt packages/tl-cli/tests/test_cli_config.py`
2. Implement `view_line`, `detail_lines`, `history_line`, then `ls`, `get`, `history`, `set_`, `reset`, `lock`, `revert`; delete the STUB paragraphs and add the imports you use.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_config.py -q
just check
uv run pytest packages/tl-cli -q
```
Expected: the provided file passes; `just check` is clean; the CLI package is green (the `test_cli_config_exchange.py` of T02 is not in your tree).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste the output of `uv run tl --db /tmp/x.db init`, then `uv run tl --db /tmp/x.db config set feed.reactions.enabled false --project P1`, `... config ls --project P1 --prefix feed.` and `... config get feed.reactions.enabled --long --project P1`.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo, or an expected output in the provided test cannot be produced by the pasted service calls.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
