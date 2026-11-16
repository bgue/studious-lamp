# P2-INSP-T01 - Read views: checklists and inspections

Status: ready (re-issued r3 against the merged S2 interfaces; base `p2/ip-r3`)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: P2-INSP-S2 merged on `p2/ip-x4` (stub `insp_views.py` and the provided test are in the tree; `p2/ip-x4` waits for X4 on the trunk)
Branch: `p2/insp-t01-read-views`
Worktree: harness-created under `/home/user/wt/insp/t01` (from `p2/ip-r3`)

## Goal
`tl_mod_quality.insp_views` gives the CLI, API, MCP and screens one read layer over checklists and inspections (`inspection_list`, `inspection_detail`, `inspection_counts`, `inspections_for`, `checklist_list`, `checklist_detail`, `export_rows`). Nothing writes; no access word is checked here (entry points do). Every read takes keyword-only `viewer=`, default `LOWEST` (never widened), and applies the hidden filter (the subject join of S2 is inside `hidden_sql`) before LIMIT and before counting. A hidden record is absent from lists, its detail is `None`, counts never include it. At most two SQL statements per call (the detail's punch keys are the second). The views never read the clock. The rules beyond the filter are in the stub's module docstring below.

## Brief references
> Hidden looks like missing: an inspection whose subject is hidden is absent from lists, its detail is `None`, counts and totals never include it (design section 7, 8). The work package (`for_iwp_id`) is not part of the confidentiality chain: its key is hidden from a reader who may not read it, and a `for_key` filter never matches such a package.

## Interfaces (verbatim from `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` at `p2/ip-r3`: fill the bodies, change no name, field or signature)
```python
"""Read views of checklists and inspections (P2-INSP S2 fixes the interface, T01 fills the bodies).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``, never widened) and
applies the hidden filter before ``LIMIT`` and before counting: an inspection is hidden through
its subject (``tl_core.confidentiality.SUBJECT_LINKS``), so a hidden subject reads as no rows, a
``None`` detail and a count of zero. Nothing here writes, checks an access word or reads the clock.
At most two SQL statements per call.

Rules the provided test pins, beyond the hidden filter: a row's ``for_key`` is ``None`` when the
viewer may not read the work package (``confidentiality.not_hidden("iwp.id", viewer)`` inside the
select), and a ``for_key`` filter never matches such a package (a key is not probed); a detail
names the punch items linked ``raised_against`` it by key (a second statement, filtered the same
way); ``inspections_for`` of a record the viewer may not read is empty; ``punch_count`` is the
number the result raised; ``done_on`` is the date part of ``done_at``; ``export_rows`` keeps the
columns of ``EXPORT_COLUMNS``, writes a header even for no rows in csv, and puts an apostrophe
before a csv cell that starts with ``= + - @``, TAB or CR (jsonl cells are untouched).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality

from tl_mod_quality.names import (
    CANCELLED,
    DONE,
    DRAFT,
    PLANNED,
    PUBLISHED,
    RETIRED,
    SCHEDULED,
    VERIFIED,
)

#: The most rows one list returns.
MAX_LIMIT: Final = 500
MSG_STATE: Final = "unknown inspection state"
MSG_POINT: Final = "unknown inspection point"
MSG_CHECKLIST_STATE: Final = "unknown checklist state"
MSG_FORMAT: Final = "export format: csv or jsonl"
INSPECTION_STATES: Final = (PLANNED, SCHEDULED, DONE, VERIFIED, CANCELLED)
CHECKLIST_STATES: Final = (DRAFT, PUBLISHED, RETIRED)
#: The columns of an export row, in order (one row per inspection).
EXPORT_COLUMNS: Final = (
    "number",
    "subject",
    "for",
    "point",
    "state",
    "result",
    "scheduled",
    "done",
    "inspector",
    "punch_count",
)
EXPORT_FORMATS: Final = ("csv", "jsonl")


@dataclass(frozen=True)
class InspectionRow:
    id: str  # the record id, for commands; no screen or line prints it
    key: str
    title: str
    subject_key: str | None
    for_key: str | None  # the work package; None when it is not readable by the viewer
    state: str
    point: str
    area: str | None
    planned_on: str | None
    scheduled_for: str | None
    inspector: str | None
    result: str | None
    done_on: str | None  # the day the result was recorded (YYYY-MM-DD)
    punch_count: int  # the punch items the result raised


@dataclass(frozen=True)
class InspectionDetail:
    row: InspectionRow
    checklist_key: str | None
    checklist_version: int | None
    answers: list[dict[str, Any]]
    note: str | None
    done_at: str | None
    recorded_by: str | None
    verified_by: str | None
    verified_on: str | None
    reinspection_of_key: str | None
    cancel_reason: str | None
    punch_keys: list[str]  # the punch items linked raised_against it, by key
    version: int


@dataclass(frozen=True)
class InspectionPage:
    rows: list[InspectionRow]
    total: int


@dataclass(frozen=True)
class ChecklistRow:
    id: str
    key: str
    title: str
    discipline: str | None
    version: int
    state: str
    question_count: int


@dataclass(frozen=True)
class ChecklistDetail:
    row: ChecklistRow
    questions: list[dict[str, Any]]
    supersedes_key: str | None
    published_by: str | None
    published_on: str | None
    retired_on: str | None
    record_version: int


@dataclass(frozen=True)
class ChecklistPage:
    rows: list[ChecklistRow]
    total: int


def inspection_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    point: str | None = None,
    area: str | None = None,
    inspector: str | None = None,
    subject_key: str | None = None,
    for_key: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> InspectionPage:
    """Visible inspections of ``scope`` by key; ``total`` counts the matches before ``limit``."""
    raise NotImplementedError  # T01 fills the body


def inspection_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> InspectionDetail | None:
    """One inspection; ``None`` when it is absent, in another project or hidden."""
    raise NotImplementedError  # T01 fills the body


def inspection_counts(
    conn: Connection,
    scope: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Visible inspections by state, each of the five present."""
    raise NotImplementedError  # T01 fills the body


def inspections_for(
    conn: Connection,
    record_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[InspectionRow]:
    """Visible inspections whose subject or work package is ``record_id``, by key; none when the
    record itself is hidden."""
    raise NotImplementedError  # T01 fills the body


def checklist_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    discipline: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ChecklistPage:
    """Visible checklists of ``scope`` by key; ``total`` counts the matches before ``limit``."""
    raise NotImplementedError  # T01 fills the body


def checklist_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ChecklistDetail | None:
    """One checklist with its questions; ``None`` when it is absent or in another project."""
    raise NotImplementedError  # T01 fills the body


def export_rows(rows: Sequence[InspectionRow], fmt: str) -> str:
    """The rows as ``csv`` (a header, then a line per row, ``\\n`` ends; a cell that starts like a
    formula gets an apostrophe) or ``jsonl`` (one object per line, the same columns, null for
    none). The rows are the caller's page: whatever the viewer could not read is not in it."""
    raise NotImplementedError  # T01 fills the body
```

### Table columns (sqlite DDL as generated; Postgres is the same shape)
```sql
CREATE TABLE IF NOT EXISTS cur_quality_inspection (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  subject_id TEXT,
  for_iwp_id TEXT,
  checklist_id TEXT,
  checklist_version INTEGER,
  point TEXT,
  area TEXT,
  planned_on TEXT,
  scheduled_for TEXT,
  inspector TEXT,
  result TEXT,
  done_at TEXT,
  answers_json TEXT NOT NULL DEFAULT '[]',
  note TEXT,
  recorded_by TEXT,
  verified_by TEXT,
  verified_on TEXT,
  reinspection_of_id TEXT,
  cancel_reason TEXT,
  punch_count INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS cur_quality_checklist (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  discipline TEXT,
  checklist_version INTEGER NOT NULL DEFAULT 1,
  questions_json TEXT NOT NULL DEFAULT '[]',
  question_count INTEGER,
  supersedes_id TEXT,
  published_by TEXT,
  published_on TEXT,
  retired_on TEXT,
  last_seq INTEGER NOT NULL
);
```

### Hidden filter
`tl_core.confidentiality` (read at r3; use as the quality views do):
```
LOWEST: Final = Viewer()      # default viewer; never widen it
def not_hidden(id_expr: str, viewer: Viewer | None = None) -> tuple[str, dict[str, Any]]:
    """(clause, params): id_expr is a record the viewer may read. id_expr is SQL written by the caller
    (a column such as r.id), never user input. Merge params into the statement's parameters."""
def is_hidden(conn: Connection, record_id: str, viewer: Viewer | None = None) -> bool: ...
```
Record key, title, scope, voided and type are in `cur_core_record` (`r`); the workflow state is `cur_workflow_state.state` by `record_id` (as `quality/views.py` joins it).

## Steps
1. Copy the provided test. 2. Build the inspection select once (a private helper): `cur_quality_inspection` joined to `cur_core_record` for key, title and scope, state from `cur_workflow_state`, the subject key by a left join on `subject_id` and the work-package key by a left join on `for_iwp_id` under `not_hidden` (a hidden package gives `for_key` None and never matches a filter). 3. List, detail, counts, `inspections_for` and the two checklist reads over it. 4. `export_rows`: csv with the formula guard, jsonl untouched. 5. Run the acceptance commands.

## Context (read these, nothing else)
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py`, `packages/tl-modules/quality/src/tl_mod_quality/views.py` (pattern; the punch views, abridged)
- `packages/tl-modules/quality/tests/insp_world.py` and `conftest.py` (world helper the provided test imports; fixture `insp`)
- the S2 report `docs/reports/P2-INSP/S2.md` (names; rules as built)
- the provided test `docs/tickets/P2-INSP/provided/T01_test_insp_views.py` (409 lines)

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (bodies and the imports they need only)
- `packages/tl-modules/quality/tests/test_insp_views.py` (create: byte-identical copy)
- `docs/reports/P2-INSP/T01.md` (create)

## Provided test
`docs/tickets/P2-INSP/provided/T01_test_insp_views.py` is committed and is the spec. Copy it byte-identical to `packages/tl-modules/quality/tests/test_insp_views.py`; do not edit it. Checked at r3 in that location: `ruff format --check`, `ruff check` and `pyright` report 0 findings, so `just check` stays green with the copy in place.

## Acceptance
```
cmp docs/tickets/P2-INSP/provided/T01_test_insp_views.py packages/tl-modules/quality/tests/test_insp_views.py
just check
just gate packages/tl-modules/quality/tests/test_insp_views.py
```
Expected: `cmp` silent; `just check` exit 0; the gate prints `gate: PASS`, every test in the provided file passing.

## Escalation triggers
A column the views need is not on the table; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test); a statement count above two on any call.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed (none expected). Commit subjects `P2-INSP-T01: ...` with the session trailers; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
