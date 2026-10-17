# P1-I4-T07 — Activity link resolution

Status: ready
Tier: haiku
Labels: core
Depends on: P1-I4-S1 to S6 on `p1/i4` (the schedule module, its registry, `LinkActivity` and the stub are in the tree); no other ticket
Branch: `p1/i4-t07-activity-link-resolver`

## Goal
A link from a record to a P6 activity points at the stable *activity reference* `MAIN/A1230`, never at a snapshot row. `packages/tl-modules/schedule/src/tl_mod_schedule/resolver.py` is the one place that says what such a link means now and as of an earlier snapshot: `resolve_snapshot`, `resolve_activity`, `links_to_activities` and `orphaned_links` raise `NotImplementedError`. The types, the two SQL statements and `_pin_as_of` are written. You implement the four functions by their STEPS comments. One provided test file must pass. The demo of this increment ends on it: a record linked to `A1230` resolves to the current snapshot and as of the earlier one.

## Brief references (pasted)
> **Brief 9 M11.** *Linking is by stable Activity ID, not snapshot row.* A link from an IWP to activity `A1230` resolves to whatever the current snapshot holds, and can be viewed as of any earlier snapshot. Activities that vanish from a new snapshot flag their links as orphaned. *Snapshot series* give schedule history without P6 access: "what was planned for this IWP at data date X".
>
> **ADR-0015 section 5.** A record links to an activity with `LinkActivity`, which makes the reference record `schedule.ActivityRef` for `<schedule>/<activity id>` the first time and then the core `AddLink` (relation `references`). A link is **floating** (no pin: it resolves to the current snapshot) or **pinned to a snapshot number** (the pin is the number as text: it resolves to that snapshot). Only Published and Superseded snapshots are history. Publishing a snapshot marks a reference whose activity is gone as absent and flags its active links stale with the fixed reason `ORPHAN_REASON` (this is already written, in `handlers/publish.py`); a link a person flagged keeps its own reason and is not an orphan of the module.

### Specification
- Nothing here writes and nothing checks a role; reads need `document.read`, which the callers (routes, CLI) check.
- `as_of` is `None` (the current snapshot), an `int` (a snapshot number), or a `str`: `YYYY-MM-DD` means the end of that day (the latest published snapshot whose data date is on or before `YYYY-MM-DDT23:59`), `YYYY-MM-DDTHH:MM` that minute. Any other string, and a `bool`, names no snapshot (the result is `None`, not an error).
- Data dates are ISO text (`2026-10-05T08:00`), so ``<=`` on the text is the date comparison. Use `re.fullmatch` for both patterns (a trailing newline or seconds must not match).
- An unknown schedule is `ScheduleNotFoundError`; everything else that is missing is a value (`no_snapshot`, `unknown_activity`, `orphaned`), never an exception.
- Booleans go to the database as Python `bool` (`False`, not `0`): SQLite and Postgres both take it.
- The two SQL statements and `_pin_as_of` are final: do not change them.

### Learnings that apply
> **L-P1-I4-2.** `int(text)` and `str.isdigit()` accept digits of other scripts (`"\u0662"`, `"\u00b2"`) and `int` refuses a text of more than 4300 digits. A pin is text a person gave (`RepinLink`), so `_pin_as_of` only reads plain ASCII digits (nine at most) as a snapshot number. Do not replace it.
>
> **L-P1-I4-5.** The same record cannot link twice to one target (`DuplicateLinkError`), so a test that wants two links uses two records or two activities; and a write inside an open read unit of work times out on SQLite (the writer lock), so a test opens and closes its read transactions around each write. The provided tests already do both. You write nothing here.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401, F841` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/schedule/src/tl_mod_schedule/resolver.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""Resolve a link to an activity: to the current snapshot, as of an earlier one, or orphaned (T07).

A link from a record points at an activity *reference* (``schedule.ActivityRef``), never at a
snapshot row (brief 9 M11). This module is the one place that decides what such a link means:

* ``resolve_snapshot`` says which snapshot an *as-of* names: nothing (the current one), a snapshot
  number, or a date (the latest published snapshot whose data date is on or before that day);
* ``resolve_activity`` reads the activity of that snapshot and says in which state the link is;
* ``links_to_activities`` lists the activity links of one record, each resolved the way its own pin
  asks (floating: the current snapshot; pinned to a number: that snapshot);
* ``orphaned_links`` lists the links of a schedule whose activity left the current snapshot (the
  link-health view of brief 7.3).

Only *published* snapshots (Published and Superseded) are history: a snapshot that is built but not
published is not what the project was planning with. Nothing here writes, and nothing here checks a
role (reads need ``document.read``).

STUB (P1-I4-T07): the functions with a STEPS comment are for you to write; the types, the SQL, the
constants, the docstrings and `_pin_as_of` are final. When they are written, delete this paragraph,
the STEPS comments and the `ruff: noqa` and `pyright` lines at the top.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection, text

from tl_mod_schedule import registry
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.names import ACTIVITY_REF_TABLE, ORPHAN_REASON

#: ``None`` is the current snapshot; an ``int`` a snapshot number; a ``str`` a date written
#: ``YYYY-MM-DD`` (the end of that day) or ``YYYY-MM-DDTHH:MM``.
AsOf = int | str | None
#: ``current``: the activity of the current snapshot. ``as_of``: the activity of an earlier
#: snapshot. ``orphaned``: the snapshot has no such activity but a reference to it exists (it
#: left the schedule). ``unknown_activity``: the snapshot has no such activity and nothing ever
#: referred to it. ``no_snapshot``: the as-of names no published snapshot.
State = Literal["current", "as_of", "orphaned", "unknown_activity", "no_snapshot"]

MAX_PIN_DIGITS = 9
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_MINUTE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


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
class ActivityLink:
    """One activity link of a record and what it resolves to now."""

    link_id: str
    status: str  # the link's own status: active or stale
    pin: str | None
    reason: str | None
    ref_key: str
    resolution: Resolution


def resolve_snapshot(
    conn: Connection, schedule_id: str, as_of: AsOf = None
) -> registry.SnapshotRow | None:
    """The published snapshot ``as_of`` names, or ``None``.

    ``None`` names the schedule's current snapshot. An integer names a snapshot by number if it
    is Published or Superseded. A string names the latest published snapshot whose data date is on
    or before it: ``YYYY-MM-DD`` means the end of that day, ``YYYY-MM-DDTHH:MM`` that minute. Any
    other string names nothing. Raises ``ScheduleNotFoundError`` for an unknown schedule.
    """
    # STEPS
    # 1. schedule = registry.get_schedule(conn, schedule_id). When it is None raise
    #    ScheduleNotFoundError(f"no schedule {schedule_id!r}").
    # 2. as_of is None: when schedule.current_snapshot_id is None return None, else return
    #    registry.get_snapshot(conn, schedule.current_snapshot_id).
    # 3. published = registry.history(conn, schedule_id): the Published and Superseded
    #    snapshots, ordered by data date, then number.
    # 4. A bool as_of names nothing: return None (test isinstance(as_of, bool) BEFORE the
    #    int test, because True is an int).
    # 5. An int names a snapshot number: return the member of published whose number equals
    #    it, else None.
    # 6. A str: if _DAY.fullmatch(as_of) the limit is f"{as_of}T23:59" (the end of that
    #    day); elif _MINUTE.fullmatch(as_of) the limit is as_of itself; any other string
    #    returns None. Use fullmatch, not match.
    # 7. found = the members of published whose data_date is not None and is <= limit (the
    #    stamps are ISO text, so the comparison is a string comparison). Return the last of
    #    found, or None when it is empty.
    raise NotImplementedError


def resolve_activity(
    conn: Connection, schedule_id: str, activity_id: str, as_of: AsOf = None
) -> Resolution:
    """What ``activity_id`` of the schedule is, as of ``as_of`` (see ``State``)."""
    # STEPS
    # 1. schedule = registry.get_schedule(...); None raises ScheduleNotFoundError(f"no
    #    schedule {schedule_id!r}").
    # 2. snapshot = resolve_snapshot(conn, schedule_id, as_of). When it is None return
    #    Resolution("no_snapshot", schedule.code, activity_id, None, None, None, None).
    # 3. activity = registry.get_activity(conn, snapshot.id, activity_id). Found: the state
    #    is "current" when as_of is None, else "as_of". Not found: "orphaned" when
    #    registry.find_ref(conn, schedule_id, activity_id) is not None (something referred
    #    to the activity once), else "unknown_activity".
    # 4. Return Resolution(state, schedule.code, activity_id, snapshot.id, snapshot.number,
    #    snapshot.data_date, activity).
    raise NotImplementedError


_LINKS_SQL = text(
    "SELECT l.link_id, l.status, l.pin, l.reason, r.key AS ref_key, a.schedule_id, a.activity_id "
    f"FROM cur_links l JOIN {ACTIVITY_REF_TABLE} a ON a.id = l.to_id "
    "JOIN cur_core_record r ON r.id = a.id "
    "WHERE l.from_id = :record AND l.status IN ('active', 'stale') "
    "ORDER BY l.created_at, l.link_id"
)


def _pin_as_of(pin: str | None) -> AsOf:
    """A link's pin as an as-of: a snapshot number, or floating.

    A pin is the label a person gave (``RepinLink``), so only plain ASCII digits (nine at most:
    ``int`` refuses a text of thousands) name a snapshot; any other pin floats.
    """
    if pin is not None and pin.isascii() and pin.isdigit() and len(pin) <= MAX_PIN_DIGITS:
        return int(pin)
    return None


def links_to_activities(conn: Connection, record_id: str) -> list[ActivityLink]:
    """The activity links of a record (active and stale), oldest first, each resolved by its pin."""
    # STEPS
    # 1. found = []. For each row of conn.execute(_LINKS_SQL, {"record": record_id}):
    # 2. append ActivityLink(link_id=str(row.link_id), status=str(row.status), pin=None when
    #    row.pin is None else str(row.pin), reason=None when row.reason is None else
    #    str(row.reason), ref_key=str(row.ref_key), resolution=resolve_activity(conn,
    #    str(row.schedule_id), str(row.activity_id), _pin_as_of(row.pin))).
    # 3. Return found (the SQL already orders it).
    raise NotImplementedError


_ORPHANED_SQL = text(
    "SELECT l.link_id, l.from_id, l.reason, a.activity_id, a.last_seen_number "
    f"FROM cur_links l JOIN {ACTIVITY_REF_TABLE} a ON a.id = l.to_id "
    "WHERE a.schedule_id = :schedule AND a.present = :absent AND l.status = 'stale' "
    "AND l.reason LIKE :reason ORDER BY a.activity_id, l.created_at, l.link_id"
)


@dataclass(frozen=True)
class OrphanedLink:
    link_id: str
    from_id: str
    activity_id: str
    last_seen_number: int | None
    reason: str


def orphaned_links(conn: Connection, schedule_id: str) -> list[OrphanedLink]:
    """The stale links of a schedule whose activity left the current snapshot.

    Only links the module flagged on a publication (their reason starts with ``ORPHAN_REASON``)
    are listed, ordered by activity id, then by age of the link.
    """
    # STEPS
    # 1. Run _ORPHANED_SQL with {"schedule": schedule_id, "absent": False, "reason":
    #    ORPHAN_REASON + "%"} (the LIKE pattern: a reason that starts with ORPHAN_REASON;
    #    the boolean is passed as a Python bool so SQLite and Postgres both take it).
    # 2. Return one OrphanedLink per row: link_id, from_id, activity_id and reason as str,
    #    and last_seen_number as int, or None when the column is None.
    raise NotImplementedError
```

`packages/tl-modules/schedule/src/tl_mod_schedule/registry.py (excerpt)` (read-only for you):
```python
@dataclass(frozen=True)
class ScheduleRow:
    id: str
    scope: str
    code: str
    title: str
    schedule_type: str
    owner: str | None
    p6_project: str | None
    current_snapshot_id: str | None
    current_snapshot_number: int | None
    current_data_date: str | None

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
class ActivityRefRow:
    id: str
    scope: str
    key: str
    schedule_id: str
    schedule_code: str
    activity_id: str
    first_snapshot_id: str
    first_snapshot_number: int
    present: bool
    last_seen_snapshot_id: str | None
    last_seen_number: int | None

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

def get_schedule(conn: Connection, schedule_id: str) -> ScheduleRow | None:
    ...

def get_snapshot(conn: Connection, snapshot_id: str) -> SnapshotRow | None:
    ...

def history(conn: Connection, schedule_id: str) -> list[SnapshotRow]:
    """The published snapshots of a schedule (Published and Superseded), oldest data date first."""
    ...

def find_ref(conn: Connection, schedule_id: str, activity_id: str) -> ActivityRefRow | None:
    ...

def get_activity(conn: Connection, snapshot_id: str, activity_id: str) -> ActivityRow | None:
    ...
```

`packages/tl-modules/schedule/src/tl_mod_schedule/errors.py and names.py (excerpt)` (read-only for you):
```python
class ScheduleNotFoundError(ScheduleError):
    """No schedule with that id or code in the scope."""

ACTIVITY_REF_TABLE: Final = "cur_schedule_activity_ref"
ORPHAN_REASON: Final = "activity is not in the published snapshot"
```

## Context (read these, nothing else)
- `packages/tl-modules/schedule/src/tl_mod_schedule/resolver.py`
- `packages/tl-modules/schedule/src/tl_mod_schedule/registry.py (the functions named above only)`
- `packages/tl-modules/schedule/src/tl_mod_schedule/errors.py`
- `packages/tl-modules/schedule/src/tl_mod_schedule/names.py`
- `packages/tl-modules/schedule/src/tl_mod_schedule/testing.py (what the provided test calls: `ScheduleWorld`)`
- `docs/tickets/P1-I4/provided/t07-test_resolver.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-modules/schedule/src/tl_mod_schedule/resolver.py (edit)`
- `packages/tl-modules/schedule/tests/test_resolver.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T07.md (create; commit it)`

## Lines you must not change
Everything in `resolver.py` outside the four functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), `MAX_PIN_DIGITS`, the patterns `_DAY` and `_MINUTE`, the types (`AsOf`, `State`, `Resolution`, `ActivityLink`, `OrphanedLink`), `_LINKS_SQL`, `_ORPHANED_SQL`, `_pin_as_of`. The signatures and docstrings of the four functions. The provided test.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t07-test_resolver.py.txt` to `packages/tl-modules/schedule/tests/test_resolver.py`. Do not edit it.
3. Implement the four functions marked STEPS in `resolver.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines; remove the imports that are then unused.
4. Run the acceptance commands (both adapters). Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-modules/schedule/tests/test_resolver.py -q
uv run pytest packages/tl-modules/schedule/tests/test_resolver.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules/schedule -q
```
Expected: `just check` clean; 22 tests pass on SQLite, 44 with `--adapters sqlite,postgres` (the Postgres server of the dev environment is up: `TL_PG_URL` is set); the whole schedule package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a new dependency, or a change to `registry.py`, `testing.py`, the handlers or the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
