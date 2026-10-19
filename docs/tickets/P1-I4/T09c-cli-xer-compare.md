# P1-I4-T09c — CLI `tl xer compare|look-ahead|trend`

Status: ready
Tier: haiku
Labels: cli
Depends on: S8 and S7 on `p1/i4` (the `tl xer` group, the views and `xercli_support.py` are in the tree); no other ticket (T09b writes `xer_read.py`, a different file)
Branch: `p1/i4-t09c-cli-xer-compare`

## Goal
A planner sees from the terminal what changed between two updates of a schedule (date shifts, float erosion, logic changes), what the next weeks hold, and how one activity's float moved through the updates. `packages/tl-cli/src/tl_cli/xer_compare.py` has the options, the docstrings (the exact output lines), the helpers `days` and `shift` and `register` written; the bodies of `compare`, `look_ahead` and `trend` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M11.** *Compare*: any two snapshots of a schedule show activities added and removed, date shifts, total-float erosion, logic changes, progress, and the activities that entered or left the critical set. *Look-aheads* (3-6 week) are generated from the current snapshot. The float trend of one activity is read across the published snapshots.
>
> **Surfaces do not re-implement rules (ADR-0015).** The module (`tl_mod_schedule.views`) computes and reads; a surface parses its options, calls one view and prints what comes back. These commands read and write nothing; a missing schedule, snapshot or activity is the module's error and `service_errors()` turns it into `error: ...` on stderr with exit 1.
>
> **Units.** Shifts are calendar days (positive is later); floats are days of the activity's own calendar (a negative float change is erosion). The views give them in days already; do not convert.

### Specification
- Every command is `db: DbTarget = ctx.obj`, then `with service_errors(), open_uow(db, readonly=True) as uow:`, one view call, and printing after the `with`.
- Output is asserted exactly, two spaces between fields. The docstring of each command is the format. `days(x)` and `shift(x)` (written) format a float in days (`4d`) and a signed shift (`+7d`).
- `compare` prints the lists in the order of `LIST_FIELDS` (imported). The view has already cut each list to `--limit` rows; the full counts are in `c.totals`, and a list with more rows than printed ends with the line `... <list> <k> more not shown`.
- `look-ahead`: the view raises `ValueError` for `--weeks` outside 1 to 26 (it is not a typer range, on purpose: the rule is the module's). Catch it and call `fail(str(problem))`.
- The command is spelled `look-ahead` (`register` does this) and its function is `look_ahead`.

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
`packages/tl-cli/src/tl_cli/xer_compare.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl xer compare|look-ahead|trend`: what changed between snapshots and what comes next (T09c).

None of these writes anything. The reads are the module's (`tl_mod_schedule.views`); these
commands parse options and print one line per fact, with two spaces between fields. Floats and
shifts are in days (of the activity's own calendar), as the views give them.


STUB (P1-I4-T09c): the bodies of `compare`, `look_ahead` and `trend` are `NotImplementedError`;
the options, docstrings (the exact output), the helpers `days` and `shift` and `register` are
written. The ticket fills the bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schedule import views
from tl_mod_schedule.compare import LIST_FIELDS

from tl_cli.derive_support import Project, cell, fail, service_errors

_Schedule = Annotated[
    str, typer.Option("--schedule", help="The schedule's code, for example MAIN.")
]


def days(value: float | int | None) -> str:
    """``-`` for none, else the number with no trailing zeros and a ``d`` (``4d``, ``-5.5d``)."""
    return "-" if value is None else f"{value:g}d"


def shift(value: int | None) -> str:
    """A shift in calendar days with its sign: ``+7d``, ``-2d``, ``+0d``; ``-`` for none."""
    return "-" if value is None else f"{value:+d}d"


def compare(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    new: Annotated[
        int | None, typer.Option("--new", min=1, help="The newer snapshot (default: current).")
    ] = None,
    old: Annotated[
        int | None, typer.Option("--old", min=1, help="The older one (default: the one before).")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000, help="Rows per list.")] = 20,
) -> None:
    """Compare two snapshots of a schedule.

    Lines: `compare <new key> (<data date>) with <old key> (<data date>)`,
    `data date shift <+n>d`, `latest finish <old or -> -> <new or ->  <+n>d or -`, then
    `summary added <n>  removed <n>  date shifts <n>  float changes <n>  logic changes <n>
    progress changes <n>  duration changes <n>  critical changes <n>` (the full counts), and up to
    `--limit` rows of each list, in this order:
    `added <id>  <name>`, `removed <id>  <name>`,
    `shift <id>  start <+n>d  finish <+n>d  largest <n>d  <name>`,
    `float <id>  <old>d -> <new>d  eroded or improved  <name>`,
    `logic <added|removed|changed> <pred> -> <succ>  <old type> -> <new type>`,
    `progress <id>  <old>% -> <new>%  <old status> -> <new status>  <name>`,
    `duration <id>  <old>d -> <new>d  <name>`,
    `critical <id>  <entered|left>  float <old>d -> <new>d  <name>`.
    A list longer than `--limit` ends with `... <list> <k> more not shown`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.comparison(conn, scope, schedule,
    #    new, old, limit=limit)`; it already cuts each list to `limit` rows and keeps the
    #    full counts in `c.totals`.
    # 3. Print, in this order: the `compare` line (`c.new.key`, `c.new.data_date`,
    #    `c.old.key`, `c.old.data_date`), the `data date shift` line with
    #    `shift(c.data_date_shift_days)`, the `latest finish` line (`cell()` of both dates,
    #    then `shift(c.finish_shift_days)` after two spaces) and the `summary` line.
    # 4. The `summary` line is `summary ` and then, for each name in `LIST_FIELDS` (imported
    #    above), `<name with _ replaced by a space> <c.totals.get(name, 0)>`, joined by two
    #    spaces.
    # 5. Then for each name in `LIST_FIELDS`, in that order: print the rows of that list in
    #    the format of the docstring (the attribute `c.<name>` is a tuple of rows), and if
    #    `c.totals.get(name, 0)` is more than the rows printed, print `... <name> <k> more
    #    not shown` with k the difference.
    # 6. Row formats: `float` uses `days(old_days) -> days(new_days)` and `eroded` when
    #    `r.eroded` else `improved`; `shift` uses `shift(r.start_shift_days)`,
    #    `shift(r.finish_shift_days)` and `r.largest_days`; `logic` uses `cell(old_type) ->
    #    cell(new_type)`; progress percents with `:g`; names with `cell(name, 60)`.
    raise NotImplementedError


def look_ahead(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    snapshot: Annotated[
        int | None, typer.Option("--snapshot", min=1, help="A snapshot (default: current).")
    ] = None,
    weeks: Annotated[int, typer.Option("--weeks", help="Weeks to look ahead, 1 to 26.")] = 4,
) -> None:
    """List what is under way or starts in the next weeks from the data date.

    Lines: `look-ahead <snapshot key>  <window start> to <window end>  <weeks> weeks`,
    `in progress <n>  late start <n>  starting <n>  critical <n>  total <n>`, then
    `<id>  <phase>  start <early start>  finish <early finish>  float <n>d  <percent>%
    <critical or ok>  <name>` per activity, in the order the module gives. A `--weeks` outside 1
    to 26 is `error: ...` on stderr, exit 1.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.look_ahead_view(conn, scope,
    #    schedule, snapshot, weeks)`; it raises `ValueError` for a `weeks` outside 1 to 26.
    #    Catch it inside the `with` and call `fail(str(problem))` (it prints `error: ...`
    #    and exits 1).
    # 3. Print the `look-ahead` line (`r.snapshot_key`, `r.window_start`, `r.window_end`,
    #    `r.weeks`) and the counts line from `r.counts` (`.get(name, 0)` for `in_progress`,
    #    `late_start`, `starting`, `critical`, `total`).
    # 4. Per row print the line of the docstring: float with `days(a.total_float_days)`,
    #    percent with `:g`, `critical` or `ok`, the name with `cell(a.name, 60)`.
    raise NotImplementedError


def trend(
    ctx: typer.Context,
    activity_id: Annotated[str, typer.Argument(help="The P6 activity id, for example A1230.")],
    project: Project,
    schedule: _Schedule,
) -> None:
    """Show one activity's float in every published snapshot, oldest first.

    `trend <id> in <schedule>`, then `<schedule>#<n>  <state>  data date <date>  float <n>d
    start <early start>  finish <early finish>  <percent>%  <critical or ok>` per snapshot that
    has the activity.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.float_trend(conn, scope, schedule,
    #    activity_id)`.
    # 3. Print `trend <activity_id> in <schedule>`, then one line per point as in the
    #    docstring: `<schedule>#<number>  <state>  data date <cell>  float <days(...)>
    #    start <cell>  finish <cell>  <percent:g>%  critical|ok`.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the comparison commands to the `tl xer` group."""
    for name, function in (
        ("compare", compare),
        ("look-ahead", look_ahead),
        ("trend", trend),
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
@dataclass(frozen=True)
class TrendPoint:
    """One activity in one published snapshot (the float trend of brief 9 M11)."""

    snapshot_number: int
    data_date: str | None
    state: str
    total_float_days: float | None
    early_start: str | None
    early_finish: str | None
    percent_complete: float
    critical: bool

def float_trend(conn: Connection, scope: str, code: str, activity_id: str) -> list[TrendPoint]:
    """The activity in every published snapshot, oldest data date first (at most 500 points).

    A snapshot that lacks the activity is left out of the list. An activity no snapshot has is
    ``ActivityNotFoundError``.
    """
    ...

def comparison(
    conn: Connection,
    scope: str,
    code: str,
    new: int | None = None,
    old: int | None = None,
    *,
    limit: int = DEFAULT_COMPARE_LIMIT,
) -> Comparison:
    """What changed from ``old`` to ``new`` (default: the current snapshot and the one before).

    Both must be built. ``SnapshotNotFoundError`` when ``old`` is not given and ``new`` is the
    first. Each list is cut to ``limit`` rows (at most 5000); ``totals`` keeps the full counts.
    """
    ...

def look_ahead_view(
    conn: Connection, scope: str, code: str, number: int | None = None, weeks: int = 4
) -> LookAhead:
    """The look-ahead of a built snapshot (default: the current one). ``ValueError`` for weeks."""
    ...
```

`packages/tl-modules/schedule/src/tl_mod_schedule/compare.py (excerpt)` (read-only for you):
```python
@dataclass(frozen=True)
class Header:
    key: str
    number: int
    data_date: str

@dataclass(frozen=True)
class Brief:
    """An activity added or removed."""

    activity_id: str
    name: str
    wbs_path: str
    status: str
    early_start: str | None
    early_finish: str | None
    total_float_days: float | None
    critical: bool

@dataclass(frozen=True)
class FieldShift:
    field: str
    old: str | None
    new: str | None
    shift_days: int | None  # calendar days, new minus old; None when a date appeared or went

@dataclass(frozen=True)
class DateShift:
    activity_id: str
    name: str
    shifts: tuple[FieldShift, ...]
    #: The largest shift in days of any date, by size (0 when only appearances or removals).
    largest_days: int
    start_shift_days: int | None  # early start
    finish_shift_days: int | None  # early finish

@dataclass(frozen=True)
class FloatChange:
    activity_id: str
    name: str
    old_days: float | None
    new_days: float | None
    delta_days: float | None
    eroded: bool  # the float is smaller than it was

@dataclass(frozen=True)
class LogicChange:
    kind: str  # added, removed or changed
    pred_activity_id: str
    succ_activity_id: str
    old_type: str | None
    new_type: str | None
    old_lag_hr: float | None
    new_lag_hr: float | None

@dataclass(frozen=True)
class ProgressChange:
    activity_id: str
    name: str
    old_percent: float
    new_percent: float
    delta_percent: float
    old_status: str
    new_status: str
    old_remaining_days: float | None
    new_remaining_days: float | None

@dataclass(frozen=True)
class DurationChange:
    activity_id: str
    name: str
    old_days: float | None
    new_days: float | None

@dataclass(frozen=True)
class CriticalChange:
    activity_id: str
    name: str
    direction: str  # entered or left
    old_float_days: float | None
    new_float_days: float | None

@dataclass(frozen=True)
class Comparison:
    old: Header
    new: Header
    data_date_shift_days: int
    #: The latest early finish in each snapshot (a stand-in for the project finish) and its shift.
    latest_finish_old: str | None
    latest_finish_new: str | None
    finish_shift_days: int | None
    added: tuple[Brief, ...]
    removed: tuple[Brief, ...]
    date_shifts: tuple[DateShift, ...]
    float_changes: tuple[FloatChange, ...]
    logic_changes: tuple[LogicChange, ...]
    progress_changes: tuple[ProgressChange, ...]
    duration_changes: tuple[DurationChange, ...]
    critical_changes: tuple[CriticalChange, ...]
    #: Rows per list before any cut: the same numbers whether or not ``limited`` was applied.
    totals: Mapping[str, int] = field(default_factory=dict[str, int])
    cut: bool = False

    def summary(self) -> dict[str, int]:
        """The counts a screen leads with: rows per list, and how many floats eroded."""
        return dict(self.totals)

    def limited(self, limit: int) -> Comparison:
        """Every list cut to ``limit`` rows; ``totals`` keeps the counts of the whole."""
        cut = any(self.totals[name] > limit for name in LIST_FIELDS)
        changes: dict[str, Any] = {name: getattr(self, name)[:limit] for name in LIST_FIELDS}
        return replace(self, cut=cut, **changes)
```

`packages/tl-modules/schedule/src/tl_mod_schedule/lookahead.py (excerpt)` (read-only for you):
```python
@dataclass(frozen=True)
class LookAheadRow:
    activity_id: str
    name: str
    wbs_path: str
    status: str
    #: ``in_progress`` (started, not finished), ``late_start`` (not started, early start before
    #: the data date) or ``starting`` (not started, early start inside the window).
    phase: str
    early_start: str | None
    early_finish: str | None
    total_float_days: float | None
    critical: bool
    percent_complete: float

@dataclass(frozen=True)
class LookAhead:
    snapshot_key: str
    snapshot_number: int
    data_date: str
    window_start: str  # ISO date, the day of the data date
    window_end: str  # ISO date, ``weeks`` weeks later
    weeks: int
    rows: tuple[LookAheadRow, ...]
    #: Rows per phase, and ``critical`` and ``total``.
    counts: Mapping[str, int]
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/xer_compare.py`
- `packages/tl-cli/src/tl_cli/derive_read.py (the same kind of command, for the style)`
- `packages/tl-modules/schedule/src/tl_mod_schedule/compare.py (the row types, named above)`
- `packages/tl-cli/tests/xercli_support.py (what the provided test calls; read only)`
- `docs/tickets/P1-I4/provided/t09c-test_cli_xer_compare.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/xer_compare.py (edit)`
- `packages/tl-cli/tests/test_cli_xer_compare.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T09c.md (create; commit it)`

## Lines you must not change
Everything in `xer_compare.py` outside the three functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), `_Schedule`, `days`, `shift`, `register`. The signatures, options and docstrings of the three functions. In every command the read is opened with `open_uow(db, readonly=True)`: reads write nothing (`test_no_comparison_read_writes_to_the_ledger` counts the events). The provided test and `xercli_support.py`.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t09c-test_cli_xer_compare.py.txt` to `packages/tl-cli/tests/test_cli_xer_compare.py`. Do not edit it.
3. Implement the three functions marked STEPS in `xer_compare.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands (both adapters). Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_xer_compare.py -q
TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-cli/tests/test_cli_xer_compare.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli/tests/test_cli_xer.py -q
```
Expected: `just check` clean; 12 pass on SQLite and 24 with both adapters; the existing `tl xer` tests still pass.

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
