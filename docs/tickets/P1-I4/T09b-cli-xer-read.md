# P1-I4-T09b — CLI `tl xer ls|show|activities|activity|resolve|health`

Status: ready
Tier: haiku
Labels: cli
Depends on: S8 and S7 on `p1/i4` (the `tl xer` group, the views and the test support `xercli_support.py` are in the tree); no other ticket (T09c writes `xer_compare.py`, a different file)
Branch: `p1/i4-t09b-cli-xer-read`

## Goal
A person looks at a project's schedules from the terminal: the list, one schedule with its snapshots, the activities of a snapshot, one activity with its neighbours, what an activity id is now or as of an earlier snapshot, and the links whose activity left. `packages/tl-cli/src/tl_cli/xer_read.py` has the options, the docstrings (the exact output lines), the helper `hours` and `register` written; the bodies of `ls`, `show`, `activities`, `activity`, `resolve` and `health` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M11.** P6 schedules arrive as XER snapshots, each immutable, one of them the current schedule. Records link to an activity by its stable activity id; a link floats (resolves to the current snapshot) or is pinned to a snapshot; a link whose activity left the schedule is flagged stale (an orphan).
>
> **Surfaces do not re-implement rules (ADR-0015).** The module (`tl_mod_schedule.views`) decides and reads; a surface parses its options, calls one view and prints what comes back. These commands read and write nothing; a missing schedule, snapshot or activity is the module's error and `service_errors()` turns it into `error: ...` on stderr with exit 1.
>
> **Scope.** A command's `--project` makes the scope `project:<ID>`; a schedule of another project is not found (the views check the scope).

### Specification
- Every command is `db: DbTarget = ctx.obj`, then `with service_errors(), open_uow(db, readonly=True) as uow:`, one view call, and printing after the `with`.
- Output is asserted exactly, two spaces between fields. The docstring of each command is the format. `cell(value, width)` writes `-` for a missing value and cuts to the width; `hours(value)` (written) writes `40h` or `-`.
- `activities` passes `critical=True` when `--critical` is given and `None` otherwise; `False` would ask for the non-critical activities.
- `resolve --as-of` is turned into what the view takes by `views.as_of_of` (nothing or `current` is the current snapshot, ASCII digits a snapshot number, anything else a date).
- `show` prints `links being checked` only while the module says the flagging job has work left (`d.links_being_checked`).

### Learnings that apply
> **Convention (P1-I3).** A command that writes declares `--actor` with the default `DEV_ACTOR`; these commands only read, so they declare none.
>
> **L-P1-I4-9.** The provided tests build a whole schedule (two uploads, two builds, two publications) in every test, about 8 seconds each. Give a pytest run a long timeout (the shell tool's default is 120 s) or run it in the background and wait for it. `just check` takes over two minutes in a fresh worktree.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401, F841` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/xer_read.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl xer ls|show|activities|activity|resolve|health`: reads of schedules (P1-I4-T09b).

None of these writes anything. The reads are the module's (`tl_mod_schedule.views`); these
commands parse options and print one line per fact, with two spaces between fields, so that a
person can read them and a script can split them. A missing schedule, snapshot or activity is the
module's error (`error: ...` on stderr, exit 1).


STUB (P1-I4-T09b): the bodies of `ls`, `show`, `activities`, `activity`, `resolve` and `health`
are `NotImplementedError`; the options, docstrings (the exact output) and `register` are written.
The ticket fills the bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schedule import views

from tl_cli.derive_support import Project, cell, service_errors

_Schedule = Annotated[
    str, typer.Option("--schedule", help="The schedule's code, for example MAIN.")
]
_Snapshot = Annotated[
    int | None, typer.Option("--snapshot", min=1, help="A snapshot number (default: current).")
]
_ActivityId = Annotated[str, typer.Argument(help="The P6 activity id, for example A1230.")]


def hours(value: float | None) -> str:
    """``-`` for none, else the hours with no trailing zeros and an ``h`` (``40h``, ``-8.5h``)."""
    return "-" if value is None else f"{value:g}h"


def ls(ctx: typer.Context, project: Project) -> None:
    """List the project's schedules, one line each.

    `<code>  <type>  current <n or ->  data date <date or ->  snapshots <n>  <title>`.
    With none: `no schedules in project <project>`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.schedule_views(conn, scope)`.
    # 3. No schedules: print `no schedules in project <project>`.
    # 4. Per schedule print the line in the docstring; `cell(x)` writes `-` for a missing
    #    value, `cell(s.title, 60)` cuts the title.
    raise NotImplementedError


def show(ctx: typer.Context, project: Project, schedule: _Schedule) -> None:
    """Show a schedule and its snapshots, newest first.

    Lines: `schedule <code>`, `title <title>`, `type <type>`, `p6 project <name or ->`,
    `owner <name or ->`, `current <n or ->  data date <date or ->`, `links being checked`
    (only while the flagging job has work left), then for each snapshot
    `snapshot <n>  <state>  data date <date or ->  activities <n or ->  errors <n or ->
    warnings <n or ->  <source file or ->`; the current snapshot has `  current` after its state.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.schedule_detail(conn, scope,
    #    schedule)`.
    # 3. Collect the lines of the docstring in a list in that order; add `links being
    #    checked` after the `current` line only when `d.links_being_checked` is true.
    # 4. A snapshot line has `  current` after its state when `s.is_current`. Use `cell()`
    #    for every value that can be missing.
    # 5. Print each line with `typer.echo`.
    raise NotImplementedError


def activities(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    snapshot: _Snapshot = None,
    critical: Annotated[bool, typer.Option("--critical", help="Only critical activities.")] = False,
    status: Annotated[str | None, typer.Option("--status", help="Only this status.")] = None,
    search: Annotated[
        str | None, typer.Option("--search", help="Id or name contains this text.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 50,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
) -> None:
    """List the activities of a snapshot in file order.

    First `<snapshot key>  data date <date>  showing <n> of <total> from <offset>`, then
    `<id>  <status>  start <early start>  finish <early finish>  float <n>h  <percent>%
    <critical or ok>  <name>` per activity (`-` for a missing value, float in hours).
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.activity_page(conn, scope,
    #    schedule, snapshot, critical=..., status=status, search=search, limit=limit,
    #    offset=offset)`; pass `critical=True` when the flag is set and `None` otherwise
    #    (`False` would ask for the non-critical ones).
    # 3. Print the header with `page.snapshot_key`, `cell(page.data_date)`,
    #    `len(page.rows)`, `page.total` and `page.offset`.
    # 4. Per row print the line of the docstring: float with `hours(a.total_float_hr)` (the
    #    helper above), percent with `:g`, `critical` or `ok`, the name with `cell(a.name,
    #    60)`.
    raise NotImplementedError


def activity(
    ctx: typer.Context,
    activity_id: _ActivityId,
    project: Project,
    schedule: _Schedule,
    snapshot: _Snapshot = None,
) -> None:
    """Show one activity and the relationships around it.

    Lines: `activity <id> in <snapshot key>`, `name <name>`, `wbs <path>`,
    `type <task type>  status <status>  percent <n>`, `early <start> -> <finish>`,
    `late <start> -> <finish>`, `actual <start> -> <finish>`,
    `float total <n>h  free <n>h  <critical or ok>`, `predecessors <n>` and `successors <n>`,
    each followed by one line per relationship: `  <other id>  <type>  lag <n>h`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.activity_detail(conn, scope,
    #    schedule, activity_id, snapshot)`.
    # 3. Collect the lines of the docstring in a list: the eight lines about the activity,
    #    then `predecessors <n>` and one line per relationship `  <pred_activity_id>
    #    <relationship_type>  lag <hours(lag_hr)>`, then `successors <n>` and one line per
    #    relationship with `succ_activity_id`.
    # 4. `early`, `late` and `actual` lines are `<name> <cell(start)> -> <cell(finish)>`.
    #    Print each line.
    raise NotImplementedError


def resolve(
    ctx: typer.Context,
    activity_id: _ActivityId,
    project: Project,
    schedule: _Schedule,
    as_of: Annotated[
        str | None,
        typer.Option(
            "--as-of", help="A snapshot number, a date (YYYY-MM-DD) or `current` (the default)."
        ),
    ] = None,
) -> None:
    """Say what an activity id is now, or as of a snapshot or a date.

    `<activity id>  <state>  <schedule>#<n> or -  data date <date or ->`, and, when the activity
    is in that snapshot, a second line `name <name>  start <early start>  finish <early finish>
    float <n>h`. States: current, as_of, orphaned, unknown_activity, no_snapshot.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.resolution(conn, scope, schedule,
    #    activity_id, views.as_of_of(as_of))`; `as_of_of` turns the option text into what
    #    the view takes.
    # 3. The snapshot is `-` when `r.snapshot_number` is `None`, else `<schedule>#<number>`.
    #    Print `<activity id>  <state>  <snapshot>  data date <cell(r.data_date)>`.
    # 4. When `r.activity` is not `None`, print the second line of the docstring.
    raise NotImplementedError


def health(ctx: typer.Context, project: Project, schedule: _Schedule) -> None:
    """List the links whose activity is not in the current snapshot (orphaned links).

    `orphaned links: <n>`, then `<link id>  record <id>  activity <id>  last seen <snapshot
    number or ->` for each.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.orphans(conn, scope, schedule)`.
    # 3. Print `orphaned links: <n>`, then one line per link as in the docstring.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the read commands to the `tl xer` group."""
    for name, function in (
        ("ls", ls),
        ("show", show),
        ("activities", activities),
        ("activity", activity),
        ("resolve", resolve),
        ("health", health),
    ):
        app.command(name)(function)
```

`packages/tl-cli/src/tl_cli/derive_support.py (excerpt; read only)` (read-only for you):
```python
Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]

def fail(message: str) -> NoReturn: ...              # prints `error: <message>` on stderr, exit 1
def service_errors() -> ContextManager[None]: ...    # ServiceError and friends -> `error: ...`, exit 1
def cell(value: object, width: int = 40) -> str:
    """One value for a table line: ``-`` for none, cut to ``width`` characters."""
```

`packages/tl-modules/schedule/src/tl_mod_schedule/views.py (excerpt)` (read-only for you):
```python
class ScheduleView(BaseModel):
    id: str
    code: str
    title: str
    schedule_type: str
    owner: str | None
    p6_project: str | None
    current_snapshot_number: int | None
    current_data_date: str | None
    snapshot_count: int

    @classmethod
    def of(cls, row: ScheduleRow, snapshot_count: int) -> ScheduleView:
        return cls(
            id=row.id,
            code=row.code,
            title=row.title,
            schedule_type=row.schedule_type,
            owner=row.owner,
            p6_project=row.p6_project,
            current_snapshot_number=row.current_snapshot_number,
            current_data_date=row.current_data_date,
            snapshot_count=snapshot_count,
        )

class ScheduleDetailView(ScheduleView):
    """A schedule with its snapshots, newest number first.

    ``links_being_checked`` is true while the job that flags the links to activities the current
    snapshot lacks (and restores the ones that came back) has work left: until it is done a link to
    a removed activity may still read as current (ADR-0015 section 5).
    """

    snapshots: list[SnapshotView]
    links_being_checked: bool = False

@dataclass(frozen=True)
class ActivityPage:
    """A page of a snapshot's activities and how many matched in all."""

    snapshot_key: str
    snapshot_number: int
    data_date: str | None
    total: int
    offset: int
    rows: tuple[ActivityRow, ...]

@dataclass(frozen=True)
class ActivityDetail:
    """One activity with the relationships that name it."""

    snapshot_key: str
    snapshot_number: int
    activity: ActivityRow
    predecessors: tuple[RelationshipRow, ...]
    successors: tuple[RelationshipRow, ...]

def as_of_of(text: str | None) -> AsOf:
    """An as-of written as text: nothing or ``current`` is the current snapshot, ASCII digits a
    snapshot number, anything else a date for ``resolver.resolve_snapshot`` to judge."""
    ...

def schedule_views(conn: Connection, scope: str) -> list[ScheduleView]:
    ...

def schedule_detail(conn: Connection, scope: str, code: str) -> ScheduleDetailView:
    ...

def activity_page(
    conn: Connection,
    scope: str,
    code: str,
    number: int | None = None,
    *,
    critical: bool | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> ActivityPage:
    """A page of activities in file order. ``limit`` is cut to ``MAX_PAGE``."""
    ...

def activity_detail(
    conn: Connection, scope: str, code: str, activity_id: str, number: int | None = None
) -> ActivityDetail:
    ...

def resolution(
    conn: Connection, scope: str, code: str, activity_id: str, as_of: AsOf = None
) -> Resolution:
    """What ``activity_id`` is now (``as_of`` ``None``) or as of a snapshot number or a date."""
    ...

def orphans(conn: Connection, scope: str, code: str) -> list[OrphanedLink]:
    """The links the last publication flagged because their activity left the schedule."""
    ...
```

`packages/tl-modules/schedule/src/tl_mod_schedule/registry.py (excerpt)` (read-only for you):
```python
@dataclass(frozen=True)
class ActivityRow:
    """One activity of a snapshot (``sched_activity``). Durations and floats are hours."""

    snapshot_id: str
    activity_id: str
    task_id: str
    name: str
    wbs_id: str
    wbs_path: str
    task_type: str
    status: str
    calendar_id: str
    original_duration_hr: float | None
    remaining_duration_hr: float | None
    early_start: str | None
    early_finish: str | None
    late_start: str | None
    late_finish: str | None
    actual_start: str | None
    actual_finish: str | None
    target_start: str | None
    target_finish: str | None
    total_float_hr: float | None
    free_float_hr: float | None
    percent_complete: float
    percent_type: str | None
    constraint_type: str | None
    constraint_date: str | None
    critical: bool
    longest_path: bool
    seq: int

@dataclass(frozen=True)
class RelationshipRow:
    snapshot_id: str
    pred_activity_id: str
    succ_activity_id: str
    relationship_type: str
    lag_hr: float
    seq: int
```

`packages/tl-modules/schedule/src/tl_mod_schedule/resolver.py (excerpt)` (read-only for you):
```python
@dataclass(frozen=True)
class Resolution:
    state: State
    schedule_code: str
    activity_id: str
    #: The snapshot the activity was read from; ``None`` for ``no_snapshot``.
    snapshot_id: str | None
    snapshot_number: int | None
    data_date: str | None
    activity: registry.ActivityRow | None

@dataclass(frozen=True)
class OrphanedLink:
    link_id: str
    from_id: str
    activity_id: str
    last_seen_number: int | None
    reason: str
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/xer_read.py`
- `packages/tl-cli/src/tl_cli/derive_read.py (the same kind of command, for the style)`
- `packages/tl-modules/schedule/src/tl_mod_schedule/views.py (the read functions and their models, named above)`
- `packages/tl-cli/tests/xercli_support.py (what the provided test calls; read only)`
- `docs/tickets/P1-I4/provided/t09b-test_cli_xer_read.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/xer_read.py (edit)`
- `packages/tl-cli/tests/test_cli_xer_read.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T09b.md (create; commit it)`

## Lines you must not change
Everything in `xer_read.py` outside the six functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), the aliases `_Schedule`, `_Snapshot`, `_ActivityId`, `hours`, `register`. The signatures, options and docstrings of the six functions. In every command the read is opened with `open_uow(db, readonly=True)`: reads write nothing (`test_no_read_writes_to_the_ledger` counts the events). The provided test and `xercli_support.py`.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t09b-test_cli_xer_read.py.txt` to `packages/tl-cli/tests/test_cli_xer_read.py`. Do not edit it.
3. Implement the six functions marked STEPS in `xer_read.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands (both adapters). Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_xer_read.py -q
TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-cli/tests/test_cli_xer_read.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli/tests/test_cli_xer.py -q
```
Expected: `just check` clean; 18 pass on SQLite and 36 with both adapters (about 3 minutes per adapter: each test builds a schedule); the existing `tl xer` tests still pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a change to a view, `xer.py`, `xercli_support.py` or the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
