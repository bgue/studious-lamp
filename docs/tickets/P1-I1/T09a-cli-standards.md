# P1-I1-T09a — `tl standards`: load, ls, show, values, add-value, close, close-value

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I1-T03 (registry commands, merged) and the standards loader (`tl_mod_engineering.loader`, on `p1/i1`); no other ticket
Branch: `p1/i1-t09a-cli-standards`

## Goal
The administrator loads and reads the company standards from the shell. `packages/tl-cli/src/tl_cli/standards.py` has the helpers and the seven commands' signatures, options and docstrings final; the seven bodies raise `NotImplementedError`. The group is already registered in `tl_cli/main.py` as `tl standards`. You implement the bodies. One provided test file (`12` test functions) must pass on SQLite and on Postgres (three cases are SQLite-only and skip on Postgres).

## Brief references (pasted)
> **Brief 6.4 Standards registry.** Mnemonics, numbering patterns and code lists are versioned and governed, each with an owner, effective dates, supersession links and project adoption status. Code lists follow the `value_list_policy` and crosswalk rules of pset value lists: `closed` (company values only), `extensible` (a project value must crosswalk to a company value), `project_defined` (the project owns the list; the crosswalk is optional).
>
> **P1-I1 plan D8.** Registry writes are admin-only; a project may add its own value to a list when the list's policy allows it (any signed-in person).

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`) and an actor from `--actor` (the default `user:dev` is replaced by the signed-in user by the root; do not change the default text).
- Admin gate: `load`, `close` and a company `add-value`/`close-value` (no `--project`) call `require_admin(db)` first; it prints `error: not signed in ...` or `error: forbidden: this command needs the admin role` and exits 1. A project `add-value`/`close-value` (with `--project`) does not.
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for service, document and validation failures.
- Rules are in the handlers and the loader: a command makes one call and prints.
- Reads (`ls`, `show`, `values`) open the unit of work with `readonly=True` and need no admin.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/standards.py` (the stub you complete):
```python
"""The `tl standards` group: load and read the company standards registry (brief 6.4; P1-I1-T09a).

Each subcommand parses options, makes one call into `tl_mod_engineering` (the loader, a handler or
a read) and prints. The rules (code-list policies, supersession, what the registry may hold) live
in the module. The registry is company data: every command that changes it needs the admin role,
except adding a value to a code list in a project (`add-value --project`), which any signed-in user
may do when the list's policy allows it.

STUB (P1-I1-T09a): the bodies of the commands raise NotImplementedError; their signatures, options
and docstrings and the helpers (`_service_errors`, `_kind`, `_scope`, `_counts`) are final. Each
body has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the
`ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_mod_engineering import codelists, registry
from tl_mod_engineering.document import StandardsDocError, load_standards_file
from tl_mod_engineering.handlers.standards import (
    AddCodeValue,
    CloseCodeValue,
    CloseStandard,
    handle_add_code_value,
    handle_close_code_value,
    handle_close_standard,
)
from tl_mod_engineering.loader import ItemKind, LoadReport, load_standards, plan_load
from tl_mod_engineering.names import COMPANY

from tl_cli.session import require_admin

app = typer.Typer(help="Load and read the company standards registry.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]
_Project = Annotated[
    str | None,
    typer.Option("--project", help="Project ID; the project's own values (default: company)."),
]
_Kind = Annotated[str, typer.Argument(help="code-list, mnemonic or pattern.")]

#: The kind names a person types, and the kind the registry stores.
KINDS = {"code-list": "code_list", "mnemonic": "mnemonic", "pattern": "numbering_pattern"}
#: The order in which a load summary lists the kinds of entry.
LOAD_ORDER: tuple[ItemKind, ...] = (
    "code_list",
    "code_value",
    "mnemonic",
    "numbering_pattern",
    "tag_class",
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency, document or input failure into `error:` on stderr, exit 1."""
    try:
        yield
    except StandardsDocError as exc:
        _fail(str(exc))
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _kind(value: str) -> str:
    """The stored kind for what a person typed, or `error:` and exit 1."""
    if value not in KINDS:
        _fail(f"unknown kind {value!r}: use code-list, mnemonic or pattern")
    return KINDS[value]


def _scope(project: str | None) -> str:
    return COMPANY if project is None else f"project:{project}"


def _counts(report: LoadReport) -> None:
    """One line per kind of entry: `<kind>  create=<n>  skip=<n>`."""
    for kind in LOAD_ORDER:
        typer.echo(
            f"{kind}  create={report.count(kind, 'create')}  skip={report.count(kind, 'skip')}"
        )


@app.command("load")
def load(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="A standards YAML file, one edition.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print what would be loaded; write nothing.")
    ] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Load an edition of the standards into the registry. Entries already there are skipped."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)` (it exits with its own error line).
    # 2. Inside `with _service_errors():` doc = load_standards_file(file).
    # 3. With --dry-run: `with open_uow(db, readonly=True) as uow:` report = plan_load(uow.conn(),
    #    doc); print f"plan {doc.edition}"; call _counts(report); return.
    # 4. Otherwise `with open_uow(db) as uow:` report = load_standards(uow, doc, actor=actor,
    #    source="cli"); after the block print f"loaded {doc.edition}" and call _counts(report).
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    kind: Annotated[
        str | None, typer.Option("--kind", help="code-list, mnemonic or pattern.")
    ] = None,
    include_closed: Annotated[
        bool, typer.Option("--all", help="Include superseded and retired entries.")
    ] = False,
) -> None:
    """List registry entries: kind, code, edition, lifecycle, label."""
    # STEPS
    # 1. kinds = [_kind(kind)] when --kind is given, else all three values of KINDS in the order
    #    code_list, mnemonic, numbering_pattern.
    # 2. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` for each kind
    #    rows += registry.find_standards(uow.conn(), scope=COMPANY, kind=k,
    #    active_only=not include_closed).
    # 3. Print one line per row with two spaces between the columns: the *CLI* kind name (the key
    #    of KINDS whose value is row.kind), row.code, row.edition, row.lifecycle, row.label.
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    kind: _Kind,
    code: Annotated[str, typer.Argument(help="The entry's code, for example Area or FV.")],
) -> None:
    """Show one registry entry: its fields and, for a code list, how many values it has."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` rows =
    #    registry.find_standards(uow.conn(), scope=COMPANY, kind=_kind(kind), code=code); if none,
    #    _fail(f"no {kind} {code!r} in the registry"). row = the last one (the newest edition).
    #    For a code list also count = len(registry.code_values(uow.conn(), COMPANY, code)).
    # 2. Print `name: value` lines in this order: kind (the CLI name as typed), code, label,
    #    edition, lifecycle, adoption, owner ("-" when None), key ("-" when None), definition
    #    ("-" when None).
    # 3. A code list also prints `value_list_policy: <policy>` and `values: <count>`; a numbering
    #    pattern prints `record_type: <data["record_type"]>` and `template: <data["template"]>`.
    raise NotImplementedError


@app.command("values")
def values(
    ctx: typer.Context,
    code_list: Annotated[str, typer.Argument(help="The code list, for example Area.")],
    project: _Project = None,
    include_all: Annotated[
        bool, typer.Option("--all", help="Include closed values and values outside their dates.")
    ] = False,
) -> None:
    """List a code list's values as a scope sees them: company values, then the project's own."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` found =
    #    codelists.values(uow.conn(), _scope(project), code_list, usable_only=not include_all).
    # 2. Print one line per value, columns separated by two spaces: code, label, origin,
    #    company_code ("-" when None), lifecycle.
    raise NotImplementedError


@app.command("add-value")
def add_value(
    ctx: typer.Context,
    code_list: Annotated[str, typer.Argument(help="The code list, for example Area.")],
    code: Annotated[str, typer.Argument(help="The new value's code.")],
    label: Annotated[str, typer.Option("--label", help="What the value is called.")],
    crosswalk: Annotated[
        str | None,
        typer.Option("--crosswalk", help="For a project value: the company value it maps to."),
    ] = None,
    meaning: Annotated[
        str | None, typer.Option("--meaning", help="IRI of the value's meaning.")
    ] = None,
    project: _Project = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Add a value to a code list: a company value (admin) or a project's own (any user)."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; scope = _scope(project); without --project call
    #    `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` handle_add_code_value(uow,
    #    AddCodeValue(actor=actor, source="cli", scope=scope, code_list=code_list, code=code,
    #    label=label, crosswalk=crosswalk, meaning=meaning)); then row =
    #    registry.find_code_value(uow.conn(), scope, code_list, code).
    # 3. Print f"added {code_list}.{code} origin={row.origin} crosswalk={row.crosswalk or '-'}".
    raise NotImplementedError


@app.command("close")
def close(
    ctx: typer.Context,
    kind: _Kind,
    code: Annotated[str, typer.Argument(help="The entry's code.")],
    reason: _Reason,
    edition: Annotated[
        str | None, typer.Option("--edition", help="Which edition, when several are active.")
    ] = None,
    superseded_by: Annotated[
        str | None,
        typer.Option(
            "--superseded-by", help="The replacing entry's key, for example CL:Area@2.0.0."
        ),
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """End the life of a code list, mnemonic or numbering pattern (admin)."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`; stored = _kind(kind).
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` active = registry.find_standards(
    #    uow.conn(), scope=COMPANY, kind=stored, code=code, active_only=True); with --edition keep
    #    the rows whose edition equals it. None left: _fail(f"no active {kind} {code!r}"); more than
    #    one: _fail(f"{kind} {code!r} has several active editions: use --edition"). row = the one.
    # 3. successor = None; with --superseded-by find the row among
    #    registry.find_standards(uow.conn(), scope=COMPANY, kind=stored) whose key equals it and
    #    use its id; no such row: _fail(f"no {kind} with key {superseded_by!r}").
    # 4. handle_close_standard(uow, CloseStandard(actor=actor, source="cli", scope=COMPANY,
    #    stream_id=row.id, lifecycle="superseded" if successor else "retired",
    #    superseded_by=successor, reason=reason)).
    # 5. After the block print f"closed {kind} {row.code} {row.edition} as {lifecycle}".
    raise NotImplementedError


@app.command("close-value")
def close_value(
    ctx: typer.Context,
    code_list: Annotated[str, typer.Argument(help="The code list, for example Area.")],
    code: Annotated[str, typer.Argument(help="The value's code.")],
    reason: _Reason,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="The replacing value's code in the same list."),
    ] = None,
    project: _Project = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """End the life of a value of a code list: a company value (admin) or a project's own."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; scope = _scope(project); without --project call
    #    `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` row = registry.find_code_value(
    #    uow.conn(), scope, code_list, code); none: _fail(f"no value {code_list}.{code} in
    #    {scope}"). With --superseded-by other = registry.find_code_value(uow.conn(), scope,
    #    code_list, superseded_by); none: _fail(f"no value {code_list}.{superseded_by} in
    #    {scope}").
    # 3. handle_close_code_value(uow, CloseCodeValue(actor=actor, source="cli", scope=scope,
    #    stream_id=row.id, lifecycle="superseded" if other else "retired",
    #    superseded_by=other.id if other else None, reason=reason)).
    # 4. After the block print f"closed value {code_list}.{code} as {lifecycle}".
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/loader.py` (signatures; bodies omitted):
```python
def plan_load(conn: Connection, doc: StandardsDoc) -> LoadReport: ...
def load_standards(uow: UnitOfWork, doc: StandardsDoc, *, actor: str, source: str, correlation_id: str | None = None) -> LoadReport: ...

@dataclass(frozen=True)
class LoadReport:
    edition: str
    items: list[LoadItem]
    def count(self, kind: ItemKind, action: Literal["create", "skip"]) -> int: ...
    created: int   # property
    skipped: int   # property
```

`packages/tl-modules/engineering/src/tl_mod_engineering/registry.py` (rows and reads you use):
```python
@dataclass(frozen=True)
class StandardRow:
    id: str; scope: str; kind: str; code: str; label: str; definition: str | None; edition: str
    owner: str | None; adoption: str; value_list_policy: str | None; effective_from: str | None
    effective_to: str | None; lifecycle: str; superseded_by: str | None; data: dict[str, Any]
    key: str | None; version: int; record_type: str

@dataclass(frozen=True)
class CodeValueRow:
    id: str; scope: str; code_list: str; code: str; label: str; meaning: str | None
    crosswalk: str | None; origin: str; sort_order: int; effective_from: str | None
    effective_to: str | None; lifecycle: str; superseded_by: str | None
    attributes: dict[str, Any]; edition: str; key: str | None; version: int

def find_standards(conn, *, scope: str, kind: str, code: str | None = None, active_only: bool = False) -> list[StandardRow]: ...  # by code then edition
def code_values(conn, scope: str, code_list: str, *, active_only: bool = False) -> list[CodeValueRow]: ...  # list order
def find_code_value(conn, scope: str, code_list: str, code: str) -> CodeValueRow | None: ...
```

`packages/tl-modules/engineering/src/tl_mod_engineering/codelists.py`:
```python
@dataclass(frozen=True)
class Resolution:
    code_list: str; scope: str; code: str; label: str
    company_code: str | None   # the company value it stands for; None for a project value with no crosswalk
    origin: str                # company | project
    lifecycle: str; usable: bool

def values(conn, scope: str, name: str, *, on: date | None = None, usable_only: bool = True) -> list[Resolution]: ...
    # the company's values, then the scope's own; raises UnknownCodeListError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/handlers/standards.py` (the commands you build; fields only):
```python
class AddCodeValue(Command):   # + actor, source, scope (company or project:<id>)
    code_list: str; code: str; label: str; meaning: str | None = None; crosswalk: str | None = None
    sort_order: int | None = None; effective_from/effective_to: str | None = None; attributes: dict = {}; edition: str | None = None
class CloseStandard(Command):  # + actor, source, scope="company"
    stream_id: str; expected_version: int | None = None; lifecycle: Literal["superseded","retired"] = "retired"
    superseded_by: str | None = None   # the id of the replacing entry; needed for "superseded"
    effective_to: str | None = None; reason: str
class CloseCodeValue(Command): ...  # the same fields; stream_id is the value's id
def handle_add_code_value(uow, cmd) -> CommandResult: ...
def handle_close_standard(uow, cmd) -> CommandResult: ...
def handle_close_code_value(uow, cmd) -> CommandResult: ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/standards.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; read it for style)
- `packages/tl-cli/tests/engcli_support.py` (test support; read only)
- `docs/tickets/P1-I1/provided/t09a-test_cli_standards.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-cli`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- On Postgres the tl-cli `conftest.py` signs a test user in for you (L-P1-I0B-8); start Postgres with `sudo pg_ctlcluster 16 main start` if needed. A parity run of a CLI test file takes about one to two minutes.
- Admin-only commands call `tl_cli.session.require_admin(db)` first. On SQLite the test file signs an admin in through `engcli_support.admin_env` (already in the tree); do not change `engcli_support.py`.
- CLI tests (L-P0-I4-B8): `CliRunner.invoke` catches exceptions; the test asserts `exit_code` and that no traceback is printed. A command that crashes with `NotImplementedError` fails the test; do not catch it.
- The provided test imports `engcli_support` (in the same tests directory, already committed) and `auth_support`; they are importable because `conftest.py` puts the directory on `sys.path`.


## Allowed paths
- `packages/tl-cli/src/tl_cli/standards.py` (edit)
- `packages/tl-cli/tests/test_cli_standards.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T09a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t09a-test_cli_standards.py.txt` to `packages/tl-cli/tests/test_cli_standards.py`.
3. Implement the seven commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_standards.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_standards.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; all cases pass on SQLite; with both adapters 3 cases skip on Postgres and the rest pass; the whole tl-cli package passes (the tag-class, import and report test files are not in your tree).

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
