# P1-I4-T10a — CLI `tl cost report budget|uncoded`

Status: ready
Tier: haiku
Labels: cli
Depends on: S12 on `p1/i4` (the report functions `tl_mod_cost.reports`, the `tl cost` group and `xercli_support.py` are in the tree); no other ticket
Branch: `p1/i4-t10a-cli-cost-report`

## Goal
A cost controller compares the budget with the forecast per cost code, and finds the records nobody has given a cost code, from the terminal. `packages/tl-cli/src/tl_cli/cost_report.py` has the options, the docstrings (the exact output lines) and `register` written; the bodies of `budget` and `uncoded` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M11.** Any record can carry a cost code; quantities and hours from execution records can be summarised by cost code for comparison with the budget. The mirror holds, per cost code, hours, quantity and amount, each as budget, actual, earned, forecast to complete (ftc) and estimate at completion (eac).
>
> **Surfaces do not re-implement rules (ADR-0015).** The report functions (`tl_mod_cost.reports`) read and decide (the variance, the percentage spent, what is over budget, which records are uncoded); a command parses its options, calls one report and prints what comes back. These commands read and write nothing.
>
> **Figures.** A figure the snapshot did not state is `None`, never zero: print `-`. `money()` (imported from `tl_cli.cost_read`) formats a figure with thousands separators and two decimals.

### Specification
- Each command is `db: DbTarget = ctx.obj`, then `with service_errors(), open_uow(db, readonly=True) as uow:`, one report call, and printing after the `with`.
- Output is asserted exactly, two spaces between fields. The docstring of each command is the format.
- `--unit` is checked by the command before it opens the ledger (`fail(...)`), so a bad unit is `error: ...` on stderr and exit 1; the report function would raise `ValueError` for it as well.
- `--type` of `uncoded` is required (typer reports a missing option with exit code 2).

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
`packages/tl-cli/src/tl_cli/cost_report.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl cost report budget|uncoded`: the cost reports (P1-I4-T10a).

Both read and write nothing. The reports are the module's (`tl_mod_cost.reports`); these commands
parse options and print one line per fact, with two spaces between fields. Figures are printed
with `money()` of `tl_cli.cost_read`; a figure the snapshot did not state is `-`.


STUB (P1-I4-T10a): the bodies of `budget` and `uncoded` are `NotImplementedError`; the options,
docstrings (the exact output) and `register` are written. The ticket fills the bodies by their
STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_cost import reports
from tl_mod_cost.names import UNITS

from tl_cli.cost_read import money
from tl_cli.derive_support import Project, cell, fail, service_errors


def budget(
    ctx: typer.Context,
    project: Project,
    unit: Annotated[str, typer.Option("--unit", help="hours, quantity or amount.")] = "quantity",
    parent: Annotated[
        str | None, typer.Option("--parent", help="Only the direct children of this code.")
    ] = None,
    over: Annotated[
        bool, typer.Option("--over", help="Only codes whose forecast is over the budget.")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 200,
) -> None:
    """Budget against forecast for each cost code, in one unit.

    First `budget report (<unit>): <n> codes, <k> over budget`, then per code
    `<code>  level <n>  uom <uom or ->  budget <x>  actual <x>  eac <x>  variance <x>
    spent <p>%  linked <n>  <over or ok>  <title>`: `variance` is budget minus eac (negative:
    over budget), `spent` is actual as a percentage of budget with one decimal (`-` without a
    budget above zero), `linked` is the number of records linked to the code. A `--unit` other
    than the three is `error: ...` on stderr, exit 1.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. A `--unit` that is not in `UNITS` is `fail(f"unit must be one of {',
    #    '.join(UNITS)}")` (it prints `error: ...` on stderr and exits 1). Do this before
    #    you open the database.
    # 3. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the report with `uow.conn()` and the scope `f"project:{project}"`, and
    #    leave the `with` before you print. The report is `reports.budget_report(conn,
    #    scope, unit=unit, parent=parent, over_only=over, limit=limit)`.
    # 4. Print `budget report (<unit>): <n> codes, <k> over budget` where k counts the lines
    #    with `over_budget`.
    # 5. Per line print the line of the docstring: the figures with `money(x)` (the helper
    #    imported above: `-` for none), `spent` as `<percent:.1f>%` or `-`, `over` or `ok`,
    #    `cell(x.uom)` and `cell(x.title, 60)`.
    raise NotImplementedError


def uncoded(
    ctx: typer.Context,
    project: Project,
    record_type: Annotated[
        str, typer.Option("--type", help="The record type, for example engineering.Tag.")
    ],
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 200,
) -> None:
    """List the records of a type that are linked to no cost code.

    First `records without a cost code (<type>): <n>`, then `<key or ->  <id>  <title>` for each,
    by key.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the report with `uow.conn()` and the scope `f"project:{project}"`, and
    #    leave the `with` before you print. The report is
    #    `reports.records_without_cost_code(conn, scope, record_type, limit=limit)`.
    # 3. Print `records without a cost code (<type>): <n>`, then one line per record:
    #    `<cell(key)>  <id>  <cell(title, 60)>`.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the `report` group to the `tl cost` group."""
    group = typer.Typer(help="Cost reports.", no_args_is_help=True)
    group.command("budget")(budget)
    group.command("uncoded")(uncoded)
    app.add_typer(group, name="report")
```

`packages/tl-cli/src/tl_cli/derive_support.py (excerpt; read only)` (read-only for you):
```python
Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]

def fail(message: str) -> NoReturn: ...              # prints `error: <message>` on stderr, exit 1
def service_errors() -> ContextManager[None]: ...    # ServiceError and friends -> `error: ...`, exit 1
def cell(value: object, width: int = 40) -> str:
    """One value for a table line: ``-`` for none, cut to ``width`` characters."""
```

`packages/tl-modules/cost/src/tl_mod_cost/reports.py (excerpt)` (read-only for you):
```python
class BudgetLine(BaseModel):
    """One cost code in one unit. A figure the snapshot did not state is ``None``, never zero."""

    code: str
    title: str
    level: int
    uom: str | None
    period: str | None
    as_of: str | None
    budget: float | None
    actual: float | None
    earned: float | None
    ftc: float | None
    eac: float | None
    #: Budget minus EAC: negative means the forecast is over the budget. ``None`` if either is.
    variance: float | None
    #: Actual as a percentage of the budget, one decimal. ``None`` without a budget above zero.
    percent_spent: float | None
    over_budget: bool
    linked_records: int

@dataclass(frozen=True)
class UncodedRecord:
    id: str
    key: str | None
    record_type: str
    title: str

def budget_report(
    conn: Connection,
    scope: str,
    *,
    unit: str = "quantity",
    parent: str | None = None,
    over_only: bool = False,
    limit: int = MAX_LINES,
) -> list[BudgetLine]:
    """The cost codes of ``scope`` for ``unit`` (``quantity``, ``hours`` or ``amount``), by code.

    ``parent`` keeps the direct children of one code. ``over_only`` keeps the codes whose EAC is
    over their budget. At most ``limit`` rows (and ``MAX_LINES``). ``ValueError`` for another
    ``unit``. Inactive codes are listed: a retired code can still hold figures.
    """
    ...

def records_without_cost_code(
    conn: Connection, scope: str, record_type: str, *, limit: int = MAX_LINES
) -> list[UncodedRecord]:
    """The records of ``record_type`` in ``scope`` with no active ``references`` link to a cost
    code, by key. Void records are left out. At most ``limit`` (and ``MAX_LINES``)."""
    ...
```

`packages/tl-modules/cost/src/tl_mod_cost/names.py (excerpt)` (read-only for you):
```python
UNITS = ("hours", "quantity", "amount")
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/cost_report.py`
- `packages/tl-cli/src/tl_cli/cost_read.py (the `money` helper and the same kind of command; another ticket's file, read only)`
- `packages/tl-modules/cost/src/tl_mod_cost/reports.py (the report functions and models, named above)`
- `packages/tl-cli/tests/xercli_support.py (what the provided test calls; read only)`
- `docs/tickets/P1-I4/provided/t10a-test_cli_cost_report.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/cost_report.py (edit)`
- `packages/tl-cli/tests/test_cli_cost_report.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T10a.md (create; commit it)`

## Lines you must not change
Everything in `cost_report.py` outside the two functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove) and `register`. The signatures, options and docstrings of the two functions. In every command the read is opened with `open_uow(db, readonly=True)`: reports write nothing (`test_no_report_writes_to_the_ledger` counts the events). The provided test, `xercli_support.py` and `cost_read.py`.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t10a-test_cli_cost_report.py.txt` to `packages/tl-cli/tests/test_cli_cost_report.py`. Do not edit it.
3. Implement the two functions marked STEPS in `cost_report.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands (both adapters). Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_cost_report.py -q
TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-cli/tests/test_cli_cost_report.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli/tests/test_cli_cost.py -q
```
Expected: `just check` clean; 7 pass on SQLite and 14 with both adapters; the existing `tl cost import` tests still pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a change to `reports.py`, `cost.py`, `xercli_support.py` or the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
