# P1-I4-T02b — CLI `tl cost snapshots|codes|show`

Status: ready
Tier: haiku
Labels: cli
Depends on: S8 and S7 on `p1/i4` (the `tl cost` group with `import`, the cost views and `xercli_support.py` are in the tree); T02a is merged (the provided test imports cost files through `tl cost import`)
Branch: `p1/i4-t02b-cli-cost-read`

## Goal
A person looks at the mirrored cost system from the terminal: the imported periods, the cost codes with their latest amounts, and one code with its figures and what every snapshot said about it. `packages/tl-cli/src/tl_cli/cost_read.py` has the options, the docstrings (the exact output lines), the helpers `money` and `matrix` and `register` written; the bodies of `snapshots`, `codes` and `show` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M11.** The cost module mirrors the cost system: cost codes with a hierarchy and, for each imported period, a matrix of figures: hours, quantity and amount, each as budget, actual, earned, forecast to complete (ftc) and estimate at completion (eac). A later period adds history; a corrected file is the next revision of the period (`2026-07@2`).
>
> **Surfaces do not re-implement rules (ADR-0015).** The module (`tl_mod_cost.views`) reads; a surface parses its options, calls one view and prints what comes back. These commands read and write nothing; a missing code is the module's error and `service_errors()` turns it into `error: ...` on stderr with exit 1.
>
> **Figures.** A figure the snapshot did not state is absent (`None`), never zero: print `-`. `money()` (written) formats a figure with thousands separators and two decimals.

### Specification
- Every command is `db: DbTarget = ctx.obj`, then `with service_errors(), open_uow(db, readonly=True) as uow:`, one view call, and printing after the `with`.
- Output is asserted exactly, two spaces between fields. The docstring of each command is the format. `cell(value, width)` writes `-` for a missing value and cuts to the width.
- The figures of a code are `figures[f"{unit}_{measure}"]` (for example `amount_budget`, `hours_actual`); `matrix()` (written) turns them into the three unit lines of `show`.
- `codes` and `show` look only at the project given by `--project` (the view checks the scope).

### Learnings that apply
> **Convention (P1-I3).** A command that writes declares `--actor` with the default `DEV_ACTOR`; these commands only read, so they declare none.
>
> **L-P1-I4-9.** `just check` takes over two minutes in a fresh worktree; give it (and a pytest run) a long timeout or run it in the background and wait for it.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401, F841` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/cost_read.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl cost snapshots|codes|show`: reads of cost codes and snapshots (P1-I4-T02b).

None of these writes anything. The reads are the module's (`tl_mod_cost.views`); these commands
parse options and print one line per fact, with two spaces between fields. Figures are printed
with thousands separators and two decimals; a figure the snapshot did not state is `-`.


STUB (P1-I4-T02b): the bodies of `snapshots`, `codes` and `show` are `NotImplementedError`; the
options, docstrings (the exact output), the helpers `money` and `matrix` and `register` are
written. The ticket fills the bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_cost import views

from tl_cli.derive_support import Project, cell, service_errors

#: The five measures of each unit, in the order they are printed.
MEASURES = ("budget", "actual", "earned", "ftc", "eac")
UNITS = ("hours", "quantity", "amount")


def money(value: float | None) -> str:
    """``-`` for none, else the figure with thousands separators and two decimals."""
    return "-" if value is None else f"{value:,.2f}"


def matrix(unit: str, figures: dict[str, float | None]) -> str:
    """`<unit>  budget <x>  actual <x>  earned <x>  ftc <x>  eac <x>` from the keys
    `<unit>_<measure>` of ``figures``."""
    parts = [f"{measure} {money(figures.get(f'{unit}_{measure}'))}" for measure in MEASURES]
    return f"{unit}  " + "  ".join(parts)


def snapshots(ctx: typer.Context, project: Project) -> None:
    """List the imported periods, newest first.

    `<period>@<revision>  as of <date>  rows <n>  new <n>  revised <n>  <currency or ->
    <source file or ->`. With none: `no cost snapshots in project <project>`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.cost_snapshots(conn, scope)`.
    # 3. No snapshots: print `no cost snapshots in project <project>`.
    # 4. Per snapshot print the line of the docstring (`s.key`, `s.as_of`, `s.row_count`,
    #    `s.new_code_count`, `s.revised_code_count`, `cell(s.currency)`,
    #    `cell(s.source_name)`).
    raise NotImplementedError


def codes(
    ctx: typer.Context,
    project: Project,
    parent: Annotated[
        str | None, typer.Option("--parent", help="Only the direct children of this code.")
    ] = None,
    search: Annotated[
        str | None, typer.Option("--search", help="Code or title contains this text.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=20000)] = 100,
) -> None:
    """List the cost codes by code, with the latest amounts.

    `cost codes: <n>`, then `<code>  level <n>  uom <uom or ->  budget <amount>  actual <amount>
    eac <amount>  <title>` for each, the amounts being the `amount_*` figures of the latest
    snapshot that stated the code.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.cost_codes(conn, scope,
    #    parent=parent, search=search, limit=limit)`.
    # 3. Print `cost codes: <n>`, then one line per code: the amounts are
    #    `money(c.figures.get('amount_budget'))`, `'amount_actual'` and `'amount_eac'`;
    #    `cell(c.uom)` and `cell(c.title, 60)`.
    raise NotImplementedError


def show(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The cost code, for example 4210-PIP.")],
    project: Project,
) -> None:
    """Show one cost code, its latest figures and what every snapshot said about it.

    Lines: `cost code <code>`, `title <title>`, `parent <code or ->`, `level <n>`,
    `uom <uom or ->`, `active <yes or no>`, `children <codes, comma separated, or ->`,
    `figures from <period or -> as of <date or ->`, then one line per unit
    (`hours`, `quantity`, `amount`): `<unit>  budget <x>  actual <x>  earned <x>  ftc <x>
    eac <x>`, then `history <n>` and for each snapshot, oldest first,
    `  <period>@<revision>  as of <date>  amount budget <x>  actual <x>  eac <x>  hours actual <x>`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.cost_code_detail(conn, scope,
    #    code)`.
    # 3. Collect the lines of the docstring in a list: the eight header lines (`children`
    #    joins `d.children` with `, ` and is `-` when empty; `figures from` uses `d.period`
    #    or `-`), one `matrix(unit, d.figures)` line for each of `UNITS`, then `history <n>`
    #    and one line per entry of `d.history` in the order given.
    # 4. A history line is `  <period>@<revision>  as of <as_of>  amount budget <x>  actual
    #    <x>  eac <x>  hours actual <x>` with `money()` of `amount_budget`, `amount_actual`,
    #    `amount_eac` and `hours_actual`. Print each line.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the read commands to the `tl cost` group."""
    for name, function in (("snapshots", snapshots), ("codes", codes), ("show", show)):
        app.command(name)(function)
```

`packages/tl-cli/src/tl_cli/derive_support.py (excerpt; read only)` (read-only for you):
```python
Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]

def service_errors() -> ContextManager[None]: ...    # ServiceError and friends -> `error: ...`, exit 1
def cell(value: object, width: int = 40) -> str:
    """One value for a table line: ``-`` for none, cut to ``width`` characters."""
```

`packages/tl-modules/cost/src/tl_mod_cost/views.py (excerpt)` (read-only for you):
```python
class CostCodeView(BaseModel):
    """A cost code with the latest figures a snapshot stated for it."""

    id: str
    code: str
    title: str
    parent_code: str | None
    level: int
    uom: str | None
    is_active: bool
    period: str | None  # the snapshot the figures come from
    as_of: str | None
    figures: dict[str, float | None]

    @classmethod
    def of(cls, row: registry.CostCodeRow) -> CostCodeView:
        return cls(
            id=row.id,
            code=row.code,
            title=row.title,
            parent_code=row.parent_code,
            level=row.level,
            uom=row.uom,
            is_active=row.is_active,
            period=row.period,
            as_of=row.as_of,
            figures=row.figures,
        )

class SnapshotValueView(BaseModel):
    """What one snapshot said about one code."""

    period: str
    revision: int
    as_of: str
    figures: dict[str, float | None]

class CostCodeDetailView(CostCodeView):
    """A code with its children's codes and the figures of every snapshot, oldest first."""

    children: list[str]
    history: list[SnapshotValueView]

class CostSnapshotView(BaseModel):
    id: str
    period: str
    revision: int
    key: str  # period@revision
    as_of: str
    currency: str | None
    source_name: str | None
    source_sha256: str | None
    row_count: int
    new_code_count: int
    revised_code_count: int
    created_at: str

    @classmethod
    def of(cls, row: registry.CostSnapshotRow) -> CostSnapshotView:
        return cls(
            id=row.id,
            period=row.period,
            revision=row.revision,
            key=f"{row.period}@{row.revision}",
            as_of=row.as_of,
            currency=row.currency,
            source_name=row.source_name,
            source_sha256=row.source_sha256,
            row_count=row.row_count,
            new_code_count=row.new_code_count,
            revised_code_count=row.revised_code_count,
            created_at=row.created_at,
        )

def cost_codes(
    conn: Connection,
    scope: str,
    *,
    parent: str | None = None,
    search: str | None = None,
    limit: int = 1000,
) -> list[CostCodeView]:
    """The cost codes of a scope by code. ``parent`` keeps the direct children of one code,
    ``search`` the codes whose code or title holds a text (any case). At most ``limit``."""
    ...

def cost_code_detail(conn: Connection, scope: str, code: str) -> CostCodeDetailView:
    ...

def cost_snapshots(conn: Connection, scope: str) -> list[CostSnapshotView]:
    """The snapshots of a scope, newest period and revision first."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/cost_read.py`
- `packages/tl-cli/src/tl_cli/derive_read.py (the same kind of command, for the style)`
- `packages/tl-modules/cost/src/tl_mod_cost/views.py (the read functions and models, named above)`
- `packages/tl-cli/tests/xercli_support.py (what the provided test calls; read only)`
- `docs/tickets/P1-I4/provided/t02b-test_cli_cost_read.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/cost_read.py (edit)`
- `packages/tl-cli/tests/test_cli_cost_read.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T02b.md (create; commit it)`

## Lines you must not change
Everything in `cost_read.py` outside the three functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), `MEASURES`, `UNITS`, `money`, `matrix`, `register`. The signatures, options and docstrings of the three functions. In every command the read is opened with `open_uow(db, readonly=True)`: reads write nothing (`test_no_read_writes_to_the_ledger` counts the events). The provided test and `xercli_support.py`.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t02b-test_cli_cost_read.py.txt` to `packages/tl-cli/tests/test_cli_cost_read.py`. Do not edit it.
3. Implement the three functions marked STEPS in `cost_read.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands (both adapters). Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_cost_read.py -q
TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-cli/tests/test_cli_cost_read.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli/tests/test_cli_cost.py -q
```
Expected: `just check` clean; 9 pass on SQLite and 18 with both adapters; the existing `tl cost import` tests still pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a change to a view, `cost.py`, `xercli_support.py` or the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
