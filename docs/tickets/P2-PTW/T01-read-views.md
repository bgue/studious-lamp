# P2-PTW-T01 - Read views: permit register, board and counts

Status: ready (re-issued r3 against the merged S2 interfaces; base `p2/ip-r3`)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: P2-PTW-S2 merged on `p2/ip-x4` (stub `views.py` and the provided test are in the tree; `p2/ip-x4` waits for X4 on the trunk)
Branch: `p2/ptw-t01-views`
Worktree: harness-created under `/home/user/wt/ptw/t01` (from `p2/ip-r3`)

## Goal
`tl_mod_permits.views` gives the CLI, API, MCP and screens one read layer over permits (`permit_list`, `permit_detail`, `permit_counts`, `permit_board(area)`, `permits_for`, `export_rows`; Lapsed through `rules.effective_state`). Nothing writes; no access word is checked here (entry points do). Every read takes keyword-only `viewer=`, default `LOWEST` (never widened), and applies the hidden filter (the subject join of S2 is inside `hidden_sql`) before LIMIT and before counting. A hidden record is absent from lists, its detail is `None`, counts never include it. At most two SQL statements per call. The views never read the clock: `now` is a parameter.

## Brief references
> A permit is hidden through its subject; the board's counts are filtered like the list; Lapsed is shown in place of Active and is derived, never stored (design section 4, 9). `needed_from`, `needed_until` are ISO calendar days as text; `issued_at` and `valid_until` are timestamps (text in the table, `datetime` with a UTC offset in the rows).

## Interfaces (verbatim from `packages/tl-modules/permits/src/tl_mod_permits/views.py` at `p2/ip-r3`: fill the bodies, change no name, field or signature)
```python
"""Read views of permits (P2-PTW T01 fills the bodies; the interface is fixed here).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``, never widened) and
applies the hidden filter before LIMIT and before counting: a hidden record is absent from lists,
its detail is ``None``, counts never include it. Nothing here reads the clock: ``now`` is a
parameter, and an Active permit whose ``valid_until`` has passed is shown as Lapsed through
``rules.effective_state``. Nothing is written and no access word is checked here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import Connection
from tl_core import confidentiality

#: The most rows one list returns.
MAX_LIMIT: Final = 500
#: The states a permit is shown in (Lapsed in place of Active when its validity has passed).
SHOWN_STATES: Final = (
    "Requested",
    "Approved",
    "Active",
    "Lapsed",
    "Suspended",
    "Handed back",
    "Closed",
    "Rejected",
    "Cancelled",
)
#: The states of a permit that is live: on the board.
LIVE_STATES: Final = ("Lapsed", "Suspended", "Active")
EXPORT_FORMATS: Final = ("csv", "jsonl")
#: The columns of an export, in order (the register of design section 8).
EXPORT_COLUMNS: Final = (
    "number",
    "type",
    "state",
    "area",
    "holder",
    "issued",
    "valid_until",
    "revalidations",
    "closed",
)


@dataclass(frozen=True)
class PermitRow:
    id: str  # the record id, for commands; no screen or line prints it
    key: str
    subject: str
    permit_type: str
    state: str  # as shown: Lapsed in place of Active
    area: str | None
    holder: str | None
    issued_at: datetime | None
    valid_until: datetime | None
    revalidation_count: int
    closed_by: str | None
    for_key: str | None  # the key of the record the work is for


@dataclass(frozen=True)
class PermitDetail:
    row: PermitRow
    description: str | None
    location_text: str | None
    requested_by: str | None
    needed_from: str | None
    needed_until: str | None
    approved_by: str | None
    issued_by: str | None
    precautions: list[str]  # the ticked precaution ids
    suspend_reason: str | None
    handback_note: str | None
    reject_reason: str | None
    cancel_reason: str | None
    version: int


@dataclass(frozen=True)
class PermitPage:
    rows: list[PermitRow]
    total: int


@dataclass(frozen=True)
class BoardArea:
    area: str | None
    rows: list[PermitRow]  # Lapsed and Suspended first, then by key


@dataclass(frozen=True)
class PermitBoard:
    areas: list[BoardArea]  # by area name, no area last
    counts: dict[str, int]  # live permits shown, by shown state


@dataclass(frozen=True)
class PermitRef:
    """A permit as readiness and the IWP card read it: the state is the stored one."""

    id: str
    key: str
    permit_type: str
    state: str
    valid_until: datetime | None


def permit_list(
    conn: Connection,
    scope: str,
    *,
    now: datetime,
    state: str | None = None,
    permit_type: str | None = None,
    area: str | None = None,
    holder: str | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitPage:
    """Permits of ``scope`` by key; ``state`` is a shown state (``Lapsed`` and ``Active`` split
    an Active permit at ``now``); ``total`` counts the rows the filters and the viewer leave."""
    raise NotImplementedError


def permit_detail(
    conn: Connection,
    scope: str,
    number: str,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitDetail | None:
    """The permit with key ``number``; ``None`` when it is hidden, absent or in another scope."""
    raise NotImplementedError


def permit_counts(
    conn: Connection,
    scope: str,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Permits of ``scope`` by shown state (every state of ``SHOWN_STATES``, zero included),
    after the hidden filter."""
    raise NotImplementedError


def permit_board(
    conn: Connection,
    scope: str,
    area: str | None = None,
    *,
    now: datetime,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PermitBoard:
    """The live permits (Lapsed, Suspended, Active) grouped by area, counts after the hidden
    filter; ``area`` narrows to one."""
    raise NotImplementedError


def permits_for(
    conn: Connection,
    record_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[PermitRef]:
    """The permits whose ``for_record_id`` is ``record_id`` (by key); none when the record is
    hidden from the viewer."""
    raise NotImplementedError


def export_rows(rows: Sequence[PermitRow], fmt: str) -> str:
    """``rows`` as ``csv`` (a header of ``EXPORT_COLUMNS`` then one line per row, ``\\n`` ends,
    times as ISO text) or ``jsonl`` (one JSON object per row with the same keys); another format
    is a ``ValueError``."""
    raise NotImplementedError
```
Also (verbatim, `packages/tl-modules/permits/src/tl_mod_permits/rules.py`):
```python
def effective_state(state: str, valid_until: datetime | None, now: datetime) -> str:
    """Show an Active permit whose validity has ended, or has no end, as Lapsed.

    Every other state is returned unchanged.
    """
```

### Table columns (sqlite DDL as generated; Postgres is the same shape)
```sql
CREATE TABLE IF NOT EXISTS cur_permits_permit (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  permit_type TEXT NOT NULL,
  for_record_id TEXT,
  area TEXT,
  location_text TEXT,
  holder TEXT,
  requested_by TEXT,
  needed_from TEXT,
  needed_until TEXT,
  approved_by TEXT,
  issued_by TEXT,
  issued_at TEXT,
  valid_until TEXT,
  precautions_json TEXT NOT NULL DEFAULT '[]',
  revalidation_count INTEGER NOT NULL DEFAULT 0,
  last_revalidated_at TEXT,
  suspend_reason TEXT,
  handback_note TEXT,
  closed_by TEXT,
  reject_reason TEXT,
  cancel_reason TEXT,
  lapse_flagged_for TEXT,
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
1. Copy the provided test. 2. Build the permit select once (a private helper): `cur_permits_permit` joined to `cur_core_record` and `cur_workflow_state`, the `not_hidden` clause on `r.id`, the for-record key by a left join on `for_record_id` (key only). 3. `permit_list`: the stored state is Active for both Active and Lapsed, so a `state` filter of `Active` or `Lapsed` splits on `valid_until` against `now` in SQL (a NULL end is Lapsed), before LIMIT and in `total`. 4. Counts, board (live states only, Lapsed and Suspended first then by key; areas by name, no area last), `permits_for`, detail, export. 5. Run the acceptance commands.

## Context (read these, nothing else)
- `packages/tl-modules/permits/src/tl_mod_permits/views.py`, `packages/tl-modules/permits/src/tl_mod_permits/rules.py` (`effective_state`, `LAPSED` in `names.py`)
- `packages/tl-modules/permits/tests/permit_world.py` and `conftest.py` (world helper the provided test imports)
- `packages/tl-modules/quality/src/tl_mod_quality/views.py` (pattern, abridged)
- the provided test `docs/tickets/P2-PTW/provided/T01_test_views.py` (382 lines)

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/views.py` (bodies and the imports they need only)
- `packages/tl-modules/permits/tests/test_views.py` (create: byte-identical copy)
- `docs/reports/P2-PTW/T01.md` (create)

## Provided test
`docs/tickets/P2-PTW/provided/T01_test_views.py` is committed and is the spec. Copy it byte-identical to `packages/tl-modules/permits/tests/test_views.py`; do not edit it. Checked at r3 in that location: `ruff format --check`, `ruff check` and `pyright` report 0 findings, so `just check` stays green with the copy in place.

## Acceptance
```
cmp docs/tickets/P2-PTW/provided/T01_test_views.py packages/tl-modules/permits/tests/test_views.py
just check
just gate packages/tl-modules/permits/tests/test_views.py
```
Expected: `cmp` silent; `just check` exit 0; the gate prints `gate: PASS`, every test in the provided file passing.

## Escalation triggers
A column the views need is not on the table; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test); a statement count above two on any call.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed (none expected). Commit subjects `P2-PTW-T01: ...` with the session trailers; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment 1 (orchestrator, 2026-11-16)
The provided test issues the two permits whose subject is restricted as ada (a controller who can read them; dora requested
them and may not issue them, per PTW-S2), not as pam. Both copies of the test are updated to the same bytes.
