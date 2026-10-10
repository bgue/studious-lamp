# P0-I8-T02 — `tl config diff|export|import`

Status: ready
Tier: haiku
Labels: cli
Depends on: — (the settings service is on the base)
Branch: `p0/i8a-t02-cli-config-exchange`

## Goal
`tl config diff` lists the keys whose effective value differs between two layers, `tl config export` prints (or writes) what a layer holds as a YAML document, and `tl config import` applies such a document to a layer, all or nothing. The module `config_exchange.py` has its own Typer app (`tl_cli.config` already adds it to the `config` group), the option declarations and helpers; `diff_line` and the three commands raise `NotImplementedError`. A provided test file (14 tests) must pass.

## Brief references (pasted)
> **30.2 Layers and resolution.** `platform default -> company -> project -> user (UI keys only)`. The **effective value** shows its origin. Values set at the current scope are marked ● (like about:config's "modified"). A company can **lock** a key, so projects cannot override it, or constrain the range projects may use.
> **30.3 Change control.** Every change is a `Setting.Changed` event: old value, new value, actor, reason (required for `advanced` and `dangerous` keys), and effective time. **Scheduled changes** take effect at a future time. **Dangerous keys** need explicit confirmation ("I accept the risk"). Changes apply live. Full per-key history, with revert.
> **30.4 Interfaces.** CLI: `tl config get | set | reset | lock | diff | export | import`. API: `/settings` endpoints. MCP: `get_settings` (read), `propose_setting_change` (draft for human approval). Export/import as YAML for templates and reviews.

### Specification
The stub's docstrings give the exact steps and output. The YAML document and its rules live in `tl_core.settings.exchange` (already implemented): one `reason` and one `accept_risk` apply to every key that needs them, locks are accepted for the company layer only, a key that already holds the value is left alone, and a file with any refused key changes nothing because the unit of work rolls back. A layer for `diff` is `default`, `company`, `project:<id>` or `user:<id>`; for `export` and `import` it is exactly one of `--company`, `--project`, `--user`. `ctx.obj` is the ledger path (`Path`). Default actor `user:dev`, source `cli`. Errors print `error: <message>` on stderr and exit 1 (`_service_errors`).

`tl config ls|get|set|...` are ticket T01 (`config.py`); do not touch them.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails on this base (four extension-type event types are not catalogued yet; workstream B owns that). It is the only expected failure of a whole-repo run. Do not touch it.
- `typer.testing.CliRunner` catches exceptions and returns them on the result: assert `exit_code` and `exception` in every CLI test. The provided tests do.
- ruff's autofix removed the imports the stub does not use; add back the ones listed below.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/config_exchange.py` (the stub you complete):
```python
"""`tl config diff|export|import`: compare layers and move a layer as YAML (P0-I8-T02; brief 30.4).

Each subcommand parses options, makes one call into `tl_core.settings`, and prints. The commands
join the `tl config` group (`tl_cli.config` adds this app to its own). The document format and its
rules (all or nothing, one reason for the file, locks only for the company) live in
`tl_core.settings.exchange`.

STUB (P0-I8-T02): `diff_line` and the three commands raise NotImplementedError. Names, signatures
and docstrings are final; implement the bodies, then delete this paragraph.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.settings.types import SettingDiff

from tl_cli.actors import refuse_agent

app = typer.Typer(help="Compare layers, export and import settings.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[
    str,
    typer.Option("--actor", help="Actor recorded on events.", callback=refuse_agent),
]
_Project = Annotated[str | None, typer.Option("--project", help="Project ID.")]
_User = Annotated[str | None, typer.Option("--user", help="User ID.")]
_Company = Annotated[bool, typer.Option("--company", help="The company layer.")]


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
    if sum((bool(project), bool(user), company)) != 1:
        _fail("give exactly one of --company, --project and --user")
    if company:
        return "company"
    return f"project:{project}" if project else f"user:{user}"


def diff_line(item: SettingDiff) -> str:
    """``feed.reactions.enabled  true -> false`` (key, two spaces, left, `` -> ``, right).

    Both values are ``format_value(..., max_items=3)`` of the effective value on that side.

    STUB (P0-I8-T02): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T02)")


@app.command("diff")
def diff(
    ctx: typer.Context,
    left: Annotated[str, typer.Argument(help="default, company, project:<id> or user:<id>.")],
    right: Annotated[str, typer.Argument(help="default, company, project:<id> or user:<id>.")],
) -> None:
    """Print the keys whose effective value differs between two layers, as `diff_line`s.

    Read-only unit of work inside ``_service_errors``, ``settings.diff(uow.conn(), left=left,
    right=right)``; print ``diff_line(item)`` for each (nothing when none differ).

    STUB (P0-I8-T02): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T02)")


@app.command("export")
def export(
    ctx: typer.Context,
    project: _Project = None,
    user: _User = None,
    company: _Company = False,
    out: Annotated[Path | None, typer.Option("--out", help="Write to this file.")] = None,
) -> None:
    """Print what a layer holds as YAML, or write it to ``--out`` (then print `wrote <path>`).

    ``layer = _layer(project, user, company)`` first. Read-only unit of work inside
    ``_service_errors``, ``text = settings.export_yaml(uow.conn(), layer=layer)``. Without
    ``--out`` print ``text`` with ``typer.echo(text, nl=False)``; with it write ``text`` to the
    file (UTF-8) and print ``wrote <out>``.

    STUB (P0-I8-T02): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T02)")


@app.command("import")
def import_(
    ctx: typer.Context,
    file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="A YAML file.")
    ],
    project: _Project = None,
    user: _User = None,
    company: _Company = False,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Why (for keys that need it).")
    ] = None,
    accept_risk: Annotated[
        bool, typer.Option("--accept-risk", help="I accept the risk (dangerous keys).")
    ] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Apply a YAML file to a layer, all or nothing.

    ``layer = _layer(project, user, company)`` first; ``text`` is the file read as UTF-8. Write
    unit of work (``open_uow(db)``) inside ``_service_errors``, ``done = settings.import_yaml(uow,
    text, layer=layer, actor=actor, source="cli", reason=reason, accept_risk=accept_risk)``: a
    refusal raises out of the block, so nothing of the file is kept. Print ``imported
    <len(done)> keys into <layer>``.

    STUB (P0-I8-T02): remove this paragraph when you implement the function.
    """
    raise NotImplementedError("STUB (P0-I8-T02)")
```
```python
# imports to add to config_exchange.py (the stub's autofix removed them):
from tl_adapters.sqlite.uow import open_uow
from tl_core import settings
from tl_core.settings.values import format_value
```
```python
# tl_core.settings (already implemented; read-only for you)
# settings.diff(conn, *, left: str, right: str) -> list[SettingDiff]      # SettingError subclass SettingScopeError for a bad layer
# SettingDiff(key, left: EffectiveSetting, right: EffectiveSetting)       # .value is the effective value
# settings.export_yaml(conn, *, layer: str) -> str
# settings.import_yaml(uow, text, *, layer, actor, source, reason=None, accept_risk=False) -> list[EffectiveSetting]
#   Errors (ServiceError): SettingsDocumentError, UnknownSettingError, InvalidSettingValueError, SettingScopeError,
#   SettingLockedError, ReasonRequiredError, RiskNotAcceptedError ... the first refusal raises and the unit of work rolls back.
# format_value(value, *, max_items=None) -> str
# tl_adapters.sqlite.uow.open_uow(path, *, readonly=False) -> context manager yielding a UnitOfWork (uow.conn() is the connection)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/config_exchange.py`
- `packages/tl-cli/src/tl_cli/proposal.py` (style)
- `docs/tickets/P0-I8/provided/t02-test_cli_config_exchange.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/config_exchange.py` (edit)
- `packages/tl-cli/tests/test_cli_config_exchange.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T02.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t02-test_cli_config_exchange.py.txt packages/tl-cli/tests/test_cli_config_exchange.py`
2. Implement `diff_line`, `diff`, `export`, `import_`; delete the STUB paragraphs and add the imports you use.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_config_exchange.py -q
just check
uv run pytest packages/tl-cli -q
```
Expected: 14 tests pass; `just check` is clean; the CLI package is green. The provided test seeds settings with the service, not with the other `tl config` commands (ticket T01), so it does not depend on them.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste `uv run tl --db /tmp/x.db config diff default company` and `config export --company` output.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
