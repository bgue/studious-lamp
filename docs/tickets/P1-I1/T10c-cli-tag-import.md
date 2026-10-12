# P1-I1-T10c — `tl tag import`: preview and apply a legacy tag list

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I1-T10a and T10b (merged) and the import apply service (`tl_mod_engineering.imports.apply`, on `p1/i1`); no other ticket
Branch: `p1/i1-t10c-cli-tag-import`

## Goal
A person previews a legacy tag list against a project and then applies it. `packages/tl-cli/src/tl_cli/tag_import.py` has the helpers (`_service_errors`, `_show`, `_preview`) and the command's signature, options and docstring final; the body raises `NotImplementedError`. The command is already registered in `tl_cli/main.py` as `tl tag import`. You implement the body. One provided test file (`8` test functions) must pass on SQLite and on Postgres (one case is SQLite-only).

## Brief references (pasted)
> **Brief 9 M2 Engineering Data.** Bulk import: a tag list from a legacy system is mapped (columns to fields), compared with what the project holds, previewed as a diff, and applied; a tag number that breaks the pattern is kept and flagged, not lost.
>
> **Brief 29.6 Legacy mapping.** A mapping template per legacy source says which column is which field and how its codes translate; the same template is used for the preview and the import.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats; `_preview` prints the counts and the detail lines.
- Without `--apply` nothing is written: open the unit of work with `readonly=True`.
- With `--apply` the plan is written in one unit of work: either all of it or none. `apply_plan` raises `ImportApplyError` for rows it refuses; `_service_errors` prints `error: <message>` and one `  - <problem>` line per problem, exit 1.
- The event `source` is `import:<job>`; the job is `--job` or the file's name without its extension.
- A tag number that breaks the registry pattern is imported as a violation (the service does that); `tl tag show` then shows it.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/tag_import.py` (the stub you complete):
```python
"""`tl tag import`: preview and apply a legacy tag list (brief 9 M2, 29.6; P1-I1-T10c).

The command reads a CSV file with a mapping template, compares it with the project's tags and
prints what would change; with `--apply` it writes the plan. Reading, comparing and writing are the
module's (`tl_mod_engineering.imports`); this command parses options and prints. It is registered
by `tl_cli.main` as `tl tag import`.

STUB (P1-I1-T10c): the bodies of the commands raise NotImplementedError; their signatures, options
and docstrings and the helpers (`_service_errors`, `_show`, `_preview`) are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_mod_engineering.errors import ImportApplyError
from tl_mod_engineering.imports.apply import apply_plan, existing_tags
from tl_mod_engineering.imports.diff import plan_import
from tl_mod_engineering.imports.mapping import MappingError, load_mapping, read_rows
from tl_mod_engineering.imports.model import ImportPlan

_DEFAULT_ACTOR = "user:dev"


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a mapping, import, service or input failure into `error:` on stderr, exit 1.

    An import that cannot be applied prints one `  - <problem>` line per row problem.
    """
    try:
        yield
    except ImportApplyError as exc:
        typer.echo(f"error: {exc}", err=True)
        for problem in exc.problems:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=1) from exc
    except MappingError as exc:
        _fail(str(exc))
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _show(value: Any) -> str:
    """A value as a person reads it in a diff: ``-`` for none, JSON for the rest (4.0 as 4)."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "-" if value is None else json.dumps(value, sort_keys=True)


def _preview(plan: ImportPlan) -> None:
    """The counts line and one line per new, changed, removed and invalid row.

    ``new=2  changed=1  unchanged=2  removed=1  invalid=1`` and then, in this order:
    ``+ <number>  <class or ->  <service or ->`` for each new row,
    ``~ <number>  <field>: <old> -> <new>`` joined by ``; `` for each changed row,
    ``- <number>`` for each tag not in the file, and ``! line <n>: <problems joined by "; ">``
    for each invalid row.
    """
    counts = plan.counts()
    typer.echo("  ".join(f"{name}={counts[name]}" for name in counts))
    for row in plan.new:
        typer.echo(f"+ {row.number}  {row.class_code or '-'}  {row.service or '-'}")
    for change in plan.changed:
        fields = "; ".join(f"{c.field}: {_show(c.old)} -> {_show(c.new)}" for c in change.changes)
        typer.echo(f"~ {change.number}  {fields}")
    for tag in plan.removed:
        typer.echo(f"- {tag.number}")
    for row in plan.invalid:
        typer.echo(f"! line {row.line}: {'; '.join(row.problems)}")


def import_tags(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="The CSV file to import.")],
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    mapping: Annotated[
        Path, typer.Option("--mapping", help="The mapping template (YAML) for this file.")
    ],
    apply: Annotated[
        bool, typer.Option("--apply", help="Write the changes. Without it nothing is written.")
    ] = False,
    skip_invalid: Annotated[
        bool, typer.Option("--skip-invalid", help="Import the valid rows and leave the others out.")
    ] = False,
    job: Annotated[
        str | None, typer.Option("--job", help="Names the import in the history (default: file).")
    ] = None,
    actor: Annotated[
        str, typer.Option("--actor", help="Actor recorded on events.")
    ] = _DEFAULT_ACTOR,
) -> None:
    """Compare a tag list with the project's tags; with --apply, create and update them."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; scope = f"project:{project}"; job = job or file.stem.
    # 2. Inside `with _service_errors():` template = load_mapping(mapping); read the file
    #    (`file.read_text(encoding="utf-8")`; an OSError or UnicodeDecodeError becomes
    #    _fail(f"{file.name}: cannot read file: {exc}")); rows = read_rows(text, template).
    # 3. Print f"import {template.name} {file.name} into project {project}".
    # 4. `with open_uow(db, readonly=not apply) as uow:` plan = plan_import(rows,
    #    existing_tags(uow.conn(), scope)); _preview(plan). Without --apply print
    #    "dry run: nothing written; add --apply to write" and return.
    # 5. With --apply, still inside that block: result = apply_plan(uow, scope, plan, actor=actor,
    #    source=f"import:{job}", reason=f"import {job}", skip_invalid=skip_invalid).
    # 6. After the block print f"applied {job}: created={result.created}  changed={result.changed}
    #    skipped={result.skipped}" (two spaces between the three fields).
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/imports/apply.py`:
```python
@dataclass(frozen=True)
class ApplyResult:
    created: int; changed: int; unchanged: int; not_in_file: int; skipped: int; correlation_id: str

def existing_tags(conn: Connection, scope: str) -> list[ExistingTag]: ...
def apply_plan(uow, scope: str, plan: ImportPlan, *, actor: str, source: str, reason: str, skip_invalid: bool = False, correlation_id: str | None = None) -> ApplyResult: ...
    # raises ImportApplyError(message, problems) when invalid rows are present (unless skip_invalid) or a row is refused
```

`packages/tl-modules/engineering/src/tl_mod_engineering/imports/mapping.py` and `diff.py`:
```python
class TagListMapping(BaseModel):
    name: str; description: str; delimiter: str = ","; columns: list[ColumnMap]; ignore: list[str] = []
def load_mapping(path: Path) -> TagListMapping: ...          # raises MappingError (a ValueError) naming the file
def read_rows(text: str, mapping: TagListMapping) -> list[ImportRow]: ...   # raises MappingError for a bad file
def plan_import(rows: Sequence[ImportRow], existing: Sequence[ExistingTag]) -> ImportPlan: ...
```

`packages/tl-modules/engineering/src/tl_mod_engineering/imports/model.py` (what `_preview` prints from):
```python
@dataclass(frozen=True)
class ImportRow:    line: int; number: str; class_code: str | None; service: str | None; psets: dict[str, dict[str, Any]]; problems: list[str]; raw: dict[str, str]
@dataclass(frozen=True)
class FieldChange:  field: str; old: Any; new: Any
@dataclass(frozen=True)
class RowChange:    line: int; number: str; tag_id: str; changes: list[FieldChange]
@dataclass
class ImportPlan:   new: list[ImportRow]; changed: list[RowChange]; unchanged: list[str]; removed: list[ExistingTag]; invalid: list[ImportRow]
                    def counts(self) -> dict[str, int]: ...   # new, changed, unchanged, removed, invalid
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/tag_import.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group; read it for style)
- `docs/tickets/P1-I1/provided/t10c-test_cli_tag_import.py.txt` (the test)
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
- On Postgres the tl-cli `conftest.py` signs a test user in for you (L-P1-I0B-8); start Postgres with `sudo pg_ctlcluster 16 main start` if needed.
- CLI tests (L-P0-I4-B8): the test asserts `exit_code` and that no traceback is printed; do not catch exceptions you do not handle.
- The command is a plain function registered by `tl_cli.main` (`tag.app.command("import")(tag_import.import_tags)`); it is not a Typer app of its own.
- Returning from inside the `with open_uow(...)` block is fine: the unit of work closes (a read-only one writes nothing).


## Allowed paths
- `packages/tl-cli/src/tl_cli/tag_import.py` (edit)
- `packages/tl-cli/tests/test_cli_tag_import.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T10c.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t10c-test_cli_tag_import.py.txt` to `packages/tl-cli/tests/test_cli_tag_import.py`.
3. Implement `import_tags` by its STEPS comment; remove the STUB paragraph, the STEPS comment and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_tag_import.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_tag_import.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; all cases pass on SQLite; with both adapters 1 case skips on Postgres and the rest pass; the whole tl-cli package passes.

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
