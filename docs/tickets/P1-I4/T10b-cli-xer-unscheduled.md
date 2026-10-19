# P1-I4-T10b — CLI `tl xer unscheduled`

Status: ready
Tier: haiku
Labels: cli
Depends on: S12 on `p1/i4` (the report function `tl_mod_schedule.reports`, the `tl xer` group and `xercli_support.py` are in the tree); no other ticket
Branch: `p1/i4-t10b-cli-xer-unscheduled`

## Goal
A planner finds the work packages (or any other record type) that point at no schedule activity, from the terminal. The work-package records (IWPs) arrive in Phase 2, so the command takes the record type as an option. `packages/tl-cli/src/tl_cli/xer_report.py` has the options, the docstring (the exact output lines) and `register` written; the body of `unscheduled` raises `NotImplementedError`. You implement it. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M11.** Activities link to CWPs, IWPs, systems and correspondence through the stable activity id. A record with no activity is not on the schedule.
>
> **Surfaces do not re-implement rules (ADR-0015).** The report function (`tl_mod_schedule.reports.unscheduled_records`) reads and decides (which links count: active ones to an activity of the schedule; a link whose activity left the schedule is stale and does not count); the command parses its options, calls it and prints what comes back. It reads and writes nothing; an unknown schedule is the module's error and `service_errors()` turns it into `error: ...` on stderr with exit 1.

### Specification
- The command is `db: DbTarget = ctx.obj`, then `with service_errors(), open_uow(db, readonly=True) as uow:`, one report call, and printing after the `with`.
- Output is asserted exactly, two spaces between fields. The docstring is the format. `cell(value, width)` writes `-` for a missing value (a record may have no key) and cuts to the width.
- `--type` is required (typer reports a missing option with exit code 2); `--schedule` is optional and narrows the links that count to that schedule's activities.

### Learnings that apply
> **Convention (P1-I3).** A command that writes declares `--actor` with the default `DEV_ACTOR`; this command only reads, so it declares none.
>
> **L-P1-I4-9.** The provided tests build a whole schedule (two uploads, two builds, two publications) in every test, about 8 seconds each. Give a pytest run a long timeout (the shell tool's default is 120 s) or run it in the background and wait for it. `just check` takes over two minutes in a fresh worktree.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401, F841` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/xer_report.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl xer unscheduled`: records that point at no schedule activity (P1-I4-T10b).

Read only. The report is the module's (`tl_mod_schedule.reports`); the command parses options and
prints one line per fact, with two spaces between fields.


STUB (P1-I4-T10b): the body of `unscheduled` is `NotImplementedError`; the options, the docstring
(the exact output) and `register` are written. The ticket fills the body by its STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schedule import reports

from tl_cli.derive_support import Project, cell, service_errors


def unscheduled(
    ctx: typer.Context,
    project: Project,
    record_type: Annotated[
        str, typer.Option("--type", help="The record type, for example awp.IWP.")
    ],
    schedule: Annotated[
        str | None,
        typer.Option(
            "--schedule", help="Only count links to this schedule's activities (default: any)."
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 200,
) -> None:
    """List the records of a type that are linked to no schedule activity.

    First `records without an activity (<type>): <n>` (or `records without an activity (<type>)
    in <schedule>: <n>` with `--schedule`), then `<key or ->  <id>  <title>` for each, by key. A
    link to an activity that left the schedule does not count. An unknown schedule is
    `error: ...` on stderr, exit 1.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error such as an unknown schedule becomes
    #    `error: ...` on stderr with exit 1), call `reports.unscheduled_records(conn,
    #    f"project:{project}", record_type, schedule_code=schedule, limit=limit)` and leave
    #    the `with` before you print.
    # 3. Print `records without an activity (<type>)` followed by ` in <schedule>` when
    #    `--schedule` was given, then `: <n>`.
    # 4. Then one line per record: `<cell(key)>  <id>  <cell(title, 60)>`.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the report command to the `tl xer` group."""
    app.command("unscheduled")(unscheduled)
```

`packages/tl-cli/src/tl_cli/derive_support.py (excerpt; read only)` (read-only for you):
```python
Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]

def service_errors() -> ContextManager[None]: ...    # ServiceError and friends -> `error: ...`, exit 1
def cell(value: object, width: int = 40) -> str:
    """One value for a table line: ``-`` for none, cut to ``width`` characters."""
```

`packages/tl-modules/schedule/src/tl_mod_schedule/reports.py (excerpt)` (read-only for you):
```python
@dataclass(frozen=True)
class UnscheduledRecord:
    id: str
    key: str | None
    record_type: str
    title: str

def unscheduled_records(
    conn: Connection,
    scope: str,
    record_type: str,
    *,
    schedule_code: str | None = None,
    limit: int = MAX_LINES,
) -> list[UnscheduledRecord]:
    """The records of ``record_type`` in ``scope`` with no active link to an activity, by key.

    With ``schedule_code`` only links to that schedule's activities count (a record linked to
    another schedule is listed); without it a link to any schedule of the project counts. A link
    whose activity left the schedule is flagged stale and does not count. Void records are left
    out. ``ScheduleNotFoundError`` for a code the project lacks. At most ``limit`` (and
    ``MAX_LINES``).
    """
    ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/xer_report.py`
- `packages/tl-cli/src/tl_cli/derive_read.py (the same kind of command, for the style)`
- `packages/tl-modules/schedule/src/tl_mod_schedule/reports.py (the report function, named above)`
- `packages/tl-cli/tests/xercli_support.py (what the provided test calls; read only)`
- `docs/tickets/P1-I4/provided/t10b-test_cli_xer_report.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/xer_report.py (edit)`
- `packages/tl-cli/tests/test_cli_xer_report.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T10b.md (create; commit it)`

## Lines you must not change
Everything in `xer_report.py` outside the function that has a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove) and `register`. The signature, options and docstring of `unscheduled`. The read is opened with `open_uow(db, readonly=True)`: the report writes nothing (`test_the_report_writes_nothing_to_the_ledger` counts the events). The provided test and `xercli_support.py`.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t10b-test_cli_xer_report.py.txt` to `packages/tl-cli/tests/test_cli_xer_report.py`. Do not edit it.
3. Implement the function marked STEPS in `xer_report.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands (both adapters). Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_xer_report.py -q
TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-cli/tests/test_cli_xer_report.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli/tests/test_cli_xer.py -q
```
Expected: `just check` clean; 5 pass on SQLite and 10 with both adapters; the existing `tl xer` tests still pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a change to `reports.py`, `xer.py`, `xercli_support.py` or the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
