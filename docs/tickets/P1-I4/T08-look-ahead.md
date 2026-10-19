# P1-I4-T08 — Look-ahead query

Status: ready
Tier: haiku
Labels: core
Depends on: P1-I4-S1 to S6 on `p1/i4` (the schedule module, its registry and the stub are in the tree); no other ticket
Branch: `p1/i4-t08-look-ahead`

## Goal
`build_look_ahead(snapshot, activities, day_hours, weeks)` lists the activities of a snapshot that a planner has to talk about in the next 1 to 26 weeks (the usual look-ahead is 3 to 6): what is under way, what should have started and has not, and what starts before the window closes. `packages/tl-modules/schedule/src/tl_mod_schedule/lookahead.py` has the row types and constants written; `_days`, `build_look_ahead` and `look_ahead` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M11.** *Look-aheads* (3-6 week) are generated from the current snapshot plus AWP readiness, so planners see which upcoming activities have unready IWPs. Activities link to CWPs/IWPs/systems; readiness and progress can be compared to activity dates.
>
> **Phase 1 plan, T08.** Look-ahead query (3-6 weeks) from the current snapshot (the readiness join lands in Phase 2). Until then a row carries the schedule's own facts only.
>
> **Contract of this module.** The window starts at the snapshot's data date, never at the clock (the same rows always give the same answer). Durations and floats are stored in hours (as P6 writes them); a row shows float in days of the activity's own calendar (`day_hr` of the calendar, 8 when it is unknown or 0), rounded to two decimals.

### Specification
- `build_look_ahead` is a pure function of its arguments: no database, no clock. `look_ahead` reads the rows and calls it.
- Dates are ISO text (`2026-10-05T08:00`); `_day` (written) takes the date part. The window is the data date's day to `weeks` weeks later, both ends included.
- Activity types that carry no work of their own (`EXCLUDED_TYPES`), completed activities and activities without an early start are not listed.
- `weeks` outside `MIN_WEEKS..MAX_WEEKS`, or a `bool` (`True` is an int in Python), is `ValueError`. A snapshot with no data date is `ValueError`.
- The order is the contract: early start, then critical first, then activity id. `counts` has every phase even at 0, plus `critical` and `total`.

### Learnings that apply
> **L-P1-I4-6.** A mutation pass (changing `<=` to `<`, removing a guard, swapping a sort key) found the tests of this file are the only specification of its boundaries: the provided tests pin the first and the last day of the window, the order of two activities with the same start, a calendar with 0 hours and a `bool` weeks. If you think a STEPS line is wrong, a test is right.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401, F841` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/schedule/src/tl_mod_schedule/lookahead.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""The look-ahead: what the current snapshot says is about to happen (P1-I4-T08, brief 9 M11).

A look-ahead of 3 to 6 weeks lists, from a snapshot's activities, the ones a planner has to talk
about: what is under way, what should have started and has not, and what starts before the window
closes. The readiness of the work packages behind each activity joins in Phase 2 (AWP); until then
the row carries the schedule's own facts only.

``build_look_ahead`` is a pure function of the rows it is given. ``look_ahead`` reads a snapshot's
rows and calls it. Nothing here reads the clock: the window starts at the snapshot's data date.

STUB (P1-I4-T08): the functions with a STEPS comment are for you to write; the types, the
constants, the docstrings and `_day` are final. When they are written, delete this paragraph, the
STEPS comments and the `ruff: noqa` and `pyright` lines at the top.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Connection

from tl_mod_schedule import registry
from tl_mod_schedule.registry import DEFAULT_DAY_HOURS, ActivityRow, SnapshotRow

MIN_WEEKS = 1
MAX_WEEKS = 26
#: Summary rows of the work breakdown and level-of-effort activities have no work of their own.
EXCLUDED_TYPES = ("level_of_effort", "wbs_summary")
PHASES = ("in_progress", "late_start", "starting")


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


def _day(stamp: str) -> date:
    return datetime.fromisoformat(stamp).date()


def _days(
    hours: float | None, activity: ActivityRow, day_hours: Mapping[str, float]
) -> float | None:
    # STEPS
    # 1. When hours is None return None.
    # 2. per_day = day_hours.get(activity.calendar_id, DEFAULT_DAY_HOURS) or
    #    DEFAULT_DAY_HOURS (a calendar that records 0 hours a day falls back to the default
    #    too).
    # 3. Return round(hours / per_day, 2).
    raise NotImplementedError


def build_look_ahead(
    snapshot: SnapshotRow,
    activities: Iterable[ActivityRow],
    day_hours: Mapping[str, float],
    weeks: int = 4,
) -> LookAhead:
    """The look-ahead of ``weeks`` weeks from the data date of ``snapshot``.

    An activity is listed when it is not completed, is not a level-of-effort or WBS summary, and
    its early start is on or before the last day of the window (an activity without an early
    start is not listed). Rows are ordered by early start, then critical first, then activity id.
    Raises ``ValueError`` for a ``weeks`` outside 1 to 26 (or a boolean) and for a snapshot with
    no data date.
    """
    # STEPS
    # 1. When weeks is a bool or not MIN_WEEKS <= weeks <= MAX_WEEKS raise
    #    ValueError(f"weeks must be between {MIN_WEEKS} and {MAX_WEEKS}"). A snapshot whose
    #    data_date is None raises ValueError(f"snapshot {snapshot.key} has no data date: it
    #    has not been built").
    # 2. start = _day(snapshot.data_date); end = start + timedelta(weeks=weeks).
    # 3. For each activity a: skip it when a.status == "completed", or a.task_type is in
    #    EXCLUDED_TYPES, or a.early_start is None. begins = _day(a.early_start); skip it
    #    when begins > end (starting exactly on the last day is listed).
    # 4. phase: "in_progress" when a.status == "in_progress"; else "late_start" when begins
    #    < start; else "starting".
    # 5. Append LookAheadRow(a.activity_id, a.name, a.wbs_path, a.status, phase,
    #    a.early_start, a.early_finish, _days(a.total_float_hr, a, day_hours), a.critical,
    #    a.percent_complete).
    # 6. Sort the rows by (early_start, not critical, activity_id): earliest first, critical
    #    before non-critical on the same start, then by id.
    # 7. counts: one entry per name in PHASES (the rows with that phase), then "critical"
    #    (the rows with critical true) and "total" (all rows). Every phase is present even
    #    at 0.
    # 8. Return LookAhead(snapshot_key=snapshot.key, snapshot_number=snapshot.number,
    #    data_date=snapshot.data_date, window_start=start.isoformat(),
    #    window_end=end.isoformat(), weeks=weeks, rows=tuple(rows), counts=counts).
    raise NotImplementedError


def look_ahead(conn: Connection, snapshot: SnapshotRow, weeks: int = 4) -> LookAhead:
    """Read the rows of ``snapshot`` and build its look-ahead (see ``build_look_ahead``)."""
    # STEPS
    # 1. Call build_look_ahead(snapshot, registry.activities(conn, snapshot.id),
    #    registry.day_hours(conn, snapshot.id), weeks) and return its result.
    raise NotImplementedError
```

`packages/tl-modules/schedule/src/tl_mod_schedule/registry.py (excerpt)` (read-only for you):
```python
@dataclass(frozen=True)
class SnapshotRow:
    id: str
    scope: str
    key: str
    state: str  # the workflow state; a snapshot that never moved is Uploaded
    schedule_id: str
    schedule_code: str
    number: int
    p6_project_option: str | None
    source_file_id: str | None
    source_name: str | None
    source_sha256: str | None
    source_size: int | None
    requested_by: str | None
    attempts: int
    last_error: str | None
    data_date: str | None
    p6_version: str | None
    p6_project: str | None
    activity_count: int | None
    relationship_count: int | None
    wbs_count: int | None
    calendar_count: int | None
    code_count: int | None
    udf_count: int | None
    error_count: int | None
    warning_count: int | None
    report_file_id: str | None
    raw_file_id: str | None
    typed_sha256: str | None
    raw_sha256: str | None
    built_at: str | None
    published_at: str | None

    @property
    def built(self) -> bool:
        return self.state in BUILT_STATES

    @property
    def queued(self) -> bool:
        return self.source_file_id is not None

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

def activities(conn: Connection, snapshot_id: str) -> list[ActivityRow]:
    """Every activity of a snapshot in file order."""
    ...

def day_hours(conn: Connection, snapshot_id: str) -> dict[str, float]:
    """Work hours per day of each calendar of a snapshot, by calendar id."""
    ...
```

`packages/tl-modules/schedule/src/tl_mod_schedule/registry.py (constant)` (read-only for you):
```python
DEFAULT_DAY_HOURS = 8.0
```

## Context (read these, nothing else)
- `packages/tl-modules/schedule/src/tl_mod_schedule/lookahead.py`
- `packages/tl-modules/schedule/src/tl_mod_schedule/registry.py (the functions and rows named above only)`
- `packages/tl-modules/schedule/src/tl_mod_schedule/testing.py (what the provided test calls: `ScheduleWorld`, `make_activity`)`
- `docs/tickets/P1-I4/provided/t08-test_lookahead.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-modules/schedule/src/tl_mod_schedule/lookahead.py (edit)`
- `packages/tl-modules/schedule/tests/test_lookahead.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T08.md (create; commit it)`

## Lines you must not change
Everything in `lookahead.py` outside the three functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), `MIN_WEEKS`, `MAX_WEEKS`, `EXCLUDED_TYPES`, `PHASES`, `LookAheadRow`, `LookAhead`, `_day`. The signatures and docstrings of the three functions. The provided test.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t08-test_lookahead.py.txt` to `packages/tl-modules/schedule/tests/test_lookahead.py`. Do not edit it.
3. Implement the three functions marked STEPS in `lookahead.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines; remove the imports that are then unused.
4. Run the acceptance commands (both adapters). Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-modules/schedule/tests/test_lookahead.py -q
uv run pytest packages/tl-modules/schedule/tests/test_lookahead.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules/schedule -q
```
Expected: `just check` clean; 19 tests pass on SQLite (the database ones also on Postgres with `--adapters sqlite,postgres`); the whole schedule package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a new dependency, or a change to `registry.py`, `testing.py` or the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
