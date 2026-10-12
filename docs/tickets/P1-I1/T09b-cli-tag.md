# P1-I1-T09b — `tl tag`: create, show, ls, reclassify, rename, split, merge

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I1-T06 (tag handlers, `registry.list_tags`) and S3, on `p1/i1`; no other ticket
Branch: `p1/i1-t09b-cli-tag`

## Goal
A person works with tags from the shell. `packages/tl-cli/src/tl_cli/tag.py` has the helpers and the seven commands'
signatures, options and docstrings final; the seven bodies raise `NotImplementedError`. The group is already registered in
`tl_cli/main.py` as `tl tag`. You implement the bodies. One provided test file (`15` test functions, 18 cases on SQLite)
must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M2.** `Tag` (project-unique identifier): tag number (pattern-validated, parsed into segments), class, service description, status (planned, design, installed, commissioned, deleted). Tag class determines mandatory psets. Tag rename/split/merge is an explicit event with `supersedes` links.
>
> **Brief 16 Phase 1 / P1-I1 demo.** `tl tag create 47-FV-1001 --class ControlValve` parses segments (`47`, `FV`, `1001`), rejects `47-XX-1`, and shows missing mandatory `valve_data` properties as non-conformant.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (the default `user:dev` is replaced by the signed-in user by the root; do not change the default text).
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure, and prints one `  - <segment>: <message> (<level>)` line per problem when a tag number is refused.
- Rules are in the handlers: a command makes one call and prints. Look a tag up by number with `_tag(...)` (it exits `error: no tag 'X' in project 'P'`).
- Reads (`show`, `ls`) open the unit of work with `readonly=True`; writes use `open_uow(db)` and print after the block, except `create`, which prints inside the block because it reads the new tag back.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/tag.py` (the stub you complete):
```python
"""The `tl tag` group: create, show, list and change engineering tags (brief 9 M2; P1-I1-T09b).

Each subcommand parses options, makes one call into `tl_mod_engineering` (a handler or a read) and
prints. The rules (the numbering pattern, the class, the supersession of a rename) live in the
module. Tags are named by number.

STUB (P1-I1-T09b): the bodies of the seven commands raise NotImplementedError; their signatures,
options, docstrings and the helpers (`_service_errors`, `_tag`, `_segments_text`, `_issue_lines`,
`_psets`, `_show_created`) are final. Each body has a STEPS comment. Implement them, then delete
this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.services.psets import conformance
from tl_core.uow import UnitOfWork
from tl_mod_engineering import registry
from tl_mod_engineering.errors import InvalidTagNumberError
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    MergeTags,
    ReclassifyTag,
    RenameTag,
    SplitTag,
    handle_create_tag,
    handle_merge_tags,
    handle_reclassify_tag,
    handle_rename_tag,
    handle_split_tag,
)

from tl_cli.pset import parse_assignment

app = typer.Typer(help="Create, show and change engineering tags.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1.

    A tag number the pattern refuses prints one `  - <segment>: <message>` line per problem.
    """
    try:
        yield
    except InvalidTagNumberError as exc:
        typer.echo(f"error: {exc}", err=True)
        for issue in exc.issues:
            where = issue["segment"] or "number"
            typer.echo(f"  - {where}: {issue['message']} ({issue['level']})", err=True)
        raise typer.Exit(code=1) from exc
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _tag(uow: UnitOfWork, scope: str, project: str, number: str) -> registry.TagRow:
    found = registry.find_tag(uow.conn(), scope, number)
    if found is None:
        _fail(f"no tag {number!r} in project {project!r}")
    return found


def _segments_text(row: registry.TagRow) -> str:
    if not row.segments:
        return "-"
    return " ".join(f"{name}={value}" for name, value in row.segments.items())


def _issue_lines(uow: UnitOfWork, tag_id: str) -> list[str]:
    report = conformance(uow, tag_id)
    return [f"issue {i.level} {i.path} {i.rule}: {i.message}" for i in report.issues]


def _psets(items: list[str] | None) -> dict[str, dict[str, Any]]:
    """``["valve_data.size_in=4"]`` becomes ``{"valve_data": {"size_in": 4}}``."""
    found: dict[str, dict[str, Any]] = {}
    for item in items or []:
        path, value = parse_assignment(item)
        pset, separator, prop = path.partition(".")
        if not separator or not prop or prop.startswith("x.") or pset in ("prj", "x"):
            _fail(f"expected PSET.PROPERTY=VALUE for a standard property, got {item!r}")
        found.setdefault(pset, {})[prop] = value
    return found


def _show_created(uow: UnitOfWork, scope: str, project: str, number: str, stream_id: str) -> None:
    row = _tag(uow, scope, project, number)
    typer.echo(f"created {stream_id}")
    typer.echo(f"tag {row.number}")
    typer.echo(f"class {row.class_code or '-'}")
    typer.echo(f"segments {_segments_text(row)}")
    typer.echo(f"number_status {row.number_status}")
    typer.echo(f"conformance {row.conformance}")
    for line in _issue_lines(uow, row.id):
        typer.echo(line)


@app.command("create")
def create(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number, for example 47-FV-1001.")],
    project: _Project,
    class_code: Annotated[
        str | None, typer.Option("--class", help="Tag class code, for example ControlValve.")
    ] = None,
    service: Annotated[
        str | None, typer.Option("--service", help="Service description (the title).")
    ] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    pset: Annotated[
        list[str] | None,
        typer.Option("--pset", help="PSET.PROPERTY=VALUE (JSON when it parses); repeatable."),
    ] = None,
    allow_violation: Annotated[
        bool,
        typer.Option(
            "--allow-violation", help="Store a number that breaks the pattern, as a violation."
        ),
    ] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Create a tag. The number must fit the registry numbering pattern."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` call handle_create_tag(uow,
    #    CreateTag(actor=actor, source="cli", scope=scope, number=number, class_code=class_code,
    #    service=service, description=description, psets=_psets(pset),
    #    pattern_policy="record" if allow_violation else "enforce")).
    # 3. Still inside the block: _show_created(uow, scope, project, number, result.stream_id).
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number.")],
    project: _Project,
) -> None:
    """Show a tag: its parts, its class, what it lacks, its values."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` row = _tag(uow, scope,
    #    project, number); issues = _issue_lines(uow, row.id).
    # 2. Print `name: value` for these fields in this order: id, number, title, class (class_code
    #    or "-"), status ("-" when None), area ("-"), mnemonic ("-"), sequence ("-" when None),
    #    pattern (pattern_code or "-"), number_status, origin, conformance, version.
    # 3. Then `segments: ` + _segments_text(row).
    # 4. For each violation of row.violations print
    #    f"violation {level} {segment or 'number'}: {message}".
    # 5. Print each line of issues. Last, print "psets: " + json.dumps(row.psets, sort_keys=True,
    #    separators=(",", ":")).
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    class_code: Annotated[str | None, typer.Option("--class")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    mnemonic: Annotated[str | None, typer.Option("--mnemonic")] = None,
    area: Annotated[str | None, typer.Option("--area")] = None,
    number_status: Annotated[
        str | None, typer.Option("--number-status", help="ok or violation.")
    ] = None,
    include_ended: Annotated[
        bool, typer.Option("--all", help="Include superseded and deleted tags.")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=5000)] = 1000,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON list.")] = False,
) -> None:
    """List a project's tags by number: number, class, status, conformance, title."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` rows =
    #    registry.list_tags(uow.conn(), f"project:{project}", class_code=class_code, status=status,
    #    mnemonic=mnemonic, area=area, number_status=number_status, include_ended=include_ended,
    #    limit=limit).
    # 2. With --json print json.dumps(list of dicts, indent=2): for each row the keys number,
    #    class_code, status, conformance, title, number_status (values as on the row), then return.
    # 3. Otherwise one line per row: number, class_code or "-", status or "-", conformance and
    #    title joined with two spaces.
    raise NotImplementedError


@app.command("reclassify")
def reclassify(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number.")],
    project: _Project,
    class_code: Annotated[str, typer.Option("--class", help="The new tag class code.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Move a tag to another class; the new class binds its own property sets."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db) as uow:` row = _tag(uow, scope, project,
    #    number); handle_reclassify_tag(uow, ReclassifyTag(actor=actor, source="cli", scope=scope,
    #    stream_id=row.id, class_code=class_code, reason=reason)); after = _tag(...) again.
    # 2. Print f"reclassified {number} {row.class_code or '-'} -> {after.class_code}" and then
    #    f"conformance {after.conformance}".
    raise NotImplementedError


@app.command("rename")
def rename(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number to replace.")],
    new_number: Annotated[str, typer.Argument(help="The new tag number.")],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace a tag by a new one with another number; the old tag is superseded."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db) as uow:` row = _tag(...); made =
    #    handle_rename_tag(uow, RenameTag(actor=actor, source="cli", scope=scope, stream_id=row.id,
    #    new_number=new_number, reason=reason)).
    # 2. Print f"renamed {number} -> {new_number}" and f"created {made.stream_id}".
    raise NotImplementedError


@app.command("split")
def split(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The tag number to replace.")],
    new_numbers: Annotated[list[str], typer.Argument(help="Two or more new tag numbers.")],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace a tag by several; the old tag is superseded."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db) as uow:` row = _tag(...); made =
    #    handle_split_tag(uow, SplitTag(actor=actor, source="cli", scope=scope, stream_id=row.id,
    #    new_numbers=new_numbers, reason=reason)) (a list of results).
    # 2. Print f"split {number} -> " + ", ".join(new_numbers), then one f"created {id}" line per
    #    result.
    raise NotImplementedError


@app.command("merge")
def merge(
    ctx: typer.Context,
    numbers: Annotated[list[str], typer.Argument(help="Two or more tag numbers to replace.")],
    project: _Project,
    into: Annotated[str, typer.Option("--into", help="The new tag number.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace several tags by one; the new tag takes the values of the first number."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db) as uow:` rows = [_tag(...) for each number];
    #    made = handle_merge_tags(uow, MergeTags(actor=actor, source="cli", scope=scope,
    #    stream_ids=[r.id for r in rows], new_number=into, reason=reason)).
    # 2. Print f"merged {', '.join(numbers)} -> {into}" and f"created {made.stream_id}".
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/handlers/tags.py` (commands and handler signatures; docstrings omitted):
```python
class CreateTag(Command):
    """Create a tag in a project scope. ``number`` becomes the record key."""

    number: str = Field(min_length=1)
    class_code: str | None = None
    service: str | None = None  # the service description; becomes the title (default: the number)
    description: str | None = None
    psets: dict[str, dict[str, Any]] = {}  # initial standard-layer values, by pset
    # "enforce": a number that breaks the pattern is refused. "record": it is stored as a
    # violation (a legacy import); the problems are kept on the tag.
    pattern_policy: Literal["enforce", "record"] = "enforce"
    origin: Literal["created", "import"] = "created"


class ReclassifyTag(Command):
    stream_id: str
    expected_version: int | None = None
    class_code: str
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class RenameTag(Command):
    """Replace a tag by a new tag with another number (same class, service and values)."""

    stream_id: str
    expected_version: int | None = None
    new_number: str = Field(min_length=1)
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class SplitTag(Command):
    """Replace one tag by several (each with the old tag's class, service and values)."""

    stream_id: str
    expected_version: int | None = None
    new_numbers: list[str] = Field(min_length=2)
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class MergeTags(Command):
    """Replace several tags by one. The new tag takes class, service and values of the first."""

    stream_ids: list[str] = Field(min_length=2)
    new_number: str = Field(min_length=1)
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)

def handle_create_tag(uow: UnitOfWork, cmd: CreateTag) -> CommandResult : ...
def handle_reclassify_tag(uow: UnitOfWork, cmd: ReclassifyTag) -> CommandResult : ...
def handle_rename_tag(uow: UnitOfWork, cmd: RenameTag) -> CommandResult : ...
def handle_split_tag(uow: UnitOfWork, cmd: SplitTag) -> list[CommandResult] : ...
def handle_merge_tags(uow: UnitOfWork, cmd: MergeTags) -> CommandResult : ...
```

`packages/tl-modules/engineering/src/tl_mod_engineering/registry.py`:
```python
@dataclass(frozen=True)
class TagRow:
    id: str
    scope: str
    number: str
    class_code: str | None
    title: str
    status: str | None
    area: str | None
    mnemonic: str | None
    sequence: int | None
    segments: dict[str, str]
    pattern_code: str | None
    number_status: str  # ok | violation
    violations: list[dict[str, Any]]
    origin: str
    conformance: str
    version: int
    psets: dict[str, Any]

def list_tags(
    conn: Connection,
    scope: str,
    *,
    class_code: str | None = None,
    status: str | None = None,
    mnemonic: str | None = None,
    area: str | None = None,
    number_status: str | None = None,
    include_ended: bool = False,
    limit: int = 1000,
    offset: int = 0,
) -> list[TagRow]:
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/tag.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/link.py` (a finished group of the same shape; read it for style)
- `packages/tl-modules/engineering/src/tl_mod_engineering/registry.py`
- `docs/tickets/P1-I1/provided/t09b-test_cli_tag.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-modules`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- CLI tests (L-P0-I4-B8): `CliRunner.invoke` catches exceptions; the test asserts `exit_code` and that `result.exception` is `None` or `SystemExit`. A command that crashes with `NotImplementedError` fails the test; do not catch it.
- The test seeds the registry with `tl_mod_engineering.testing.seed_registry`; it needs no standards file.
- On Postgres the tl-cli `conftest.py` signs a test user in for you (L-P1-I0B-8); run `TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_tag.py -q --adapters sqlite,postgres` (start Postgres with `sudo pg_ctlcluster 16 main start` if needed). It takes about 90 seconds.
- `tl_cli.pset.parse_assignment` turns `valve_data.size_in=4` into `("valve_data.size_in", 4)` (JSON when it parses); `_psets` already uses it.

## Allowed paths
- `packages/tl-cli/src/tl_cli/tag.py` (edit)
- `packages/tl-cli/tests/test_cli_tag.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T09b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t09b-test_cli_tag.py.txt` to `packages/tl-cli/tests/test_cli_tag.py`.
3. Implement the seven commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_tag.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_tag.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 18 passed on SQLite; 36 passed with both adapters; the whole tl-cli package passes (the other tag-report test file is not in your tree).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `tl_mod_engineering` or in another `tl_cli` file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
