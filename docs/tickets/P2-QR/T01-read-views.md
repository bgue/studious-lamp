# P2-QR-T01 - Read views: scan code register

Status: ready (re-issued r3 against the merged S2 interfaces; base `p2/ip-r3`)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: P2-QR-S2 merged on `p2/ip-x4` (stub `views.py` and the provided test are in the tree; `p2/ip-x4` waits for X4 on the trunk)
Branch: `p2/qr-t01-read-views`
Worktree: harness-created under `/home/user/wt/qr/t01` (from `p2/ip-r3`)

## Goal
`tl_mod_qr.views` gives the CLI, API, MCP and screens one read layer over the scan code register (`codes_for_record`, `code_counts`, `export_rows`; `CodeRow` never holds the code or its hash). Nothing writes; no access word is checked here (entry points do). Both reads take keyword-only `viewer=`, default `LOWEST` (never widened), and apply the hidden filter before LIMIT and before counting: a hidden record gives `[]` and zero counts. At most two SQL statements per call. State is derived, not stored: `revoked` when `revoked_at` is set, else `expired` when `expires_on[:10]` is before today's UTC date, else `live` (the rule of `resolve.py` line 61). The signatures carry no `now`, so the one clock read is `tl_core.util.utcnow()` for that comparison.

## Brief references
> Register: id, label text, who issued, when, state, expiry. It can never show the code (qr-workface section 7). A listing of a record's codes reads the record under the viewer first; a hidden record gives `[]` and zero counts.
> `codes_for_record`: newest first by `issued_at`, at most 100. `code_counts`: `{live, revoked, expired}`, all three keys always present. `export_rows(rows, "csv"|"jsonl")`: columns in `CodeRow` field order; a csv header even for no rows; other format is a `ValueError`.

## Interfaces (verbatim from `packages/tl-modules/qr/src/tl_mod_qr/views.py` at `p2/ip-r3`: fill the bodies, change no name, field or signature)
```python
"""Read views of scan codes (stub: T01 fills them; the provided test pins the interfaces).

``CodeRow`` holds the register fields and never the code or its hash. Names raise
``NotImplementedError`` until T01.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection
from tl_core.confidentiality import LOWEST, Viewer


@dataclass(frozen=True)
class CodeRow:
    id: str
    label_text: str | None
    size: str
    issued_by: str
    issued_at: str
    expires_on: str | None
    state: str
    revoked_at: str | None
    replaced_by_id: str | None


def codes_for_record(conn: Connection, record_id: str, *, viewer: Viewer = LOWEST) -> list[CodeRow]:
    """The codes of one record, newest first, at most 100 (T01)."""
    raise NotImplementedError("T01")


def code_counts(conn: Connection, *, viewer: Viewer = LOWEST) -> dict[str, int]:
    """Counts by state: ``live``, ``revoked``, ``expired`` (T01)."""
    raise NotImplementedError("T01")


def export_rows(rows: list[CodeRow], fmt: Literal["csv", "jsonl"]) -> str:
    """The rows as CSV or JSON lines (T01)."""
    raise NotImplementedError("T01")
```

### Table columns (sqlite DDL as generated; Postgres is the same shape)
```sql
CREATE TABLE IF NOT EXISTS cur_qr_scan_code (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  target_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  label_text TEXT,
  size TEXT NOT NULL DEFAULT 'tag',
  issued_by TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  expires_on TEXT,
  revoked_at TEXT,
  revoked_by TEXT,
  revoke_reason TEXT,
  replaced_by_id TEXT,
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
1. Copy the provided test. 2. Fill `codes_for_record`: one statement over `cur_qr_scan_code` with `target_id = :id`, the `not_hidden` clause on the target (the subject join of S2 is inside `hidden_sql`), `ORDER BY issued_at DESC, id DESC LIMIT 100`. 3. `code_counts`: one grouped statement with the same hidden clause on `target_id`, state by the rule above, absent states 0. 4. `export_rows` with `csv` and `json` from the standard library. 5. Run the acceptance commands.

## Context (read these, nothing else)
- `packages/tl-modules/qr/src/tl_mod_qr/views.py`, `packages/tl-modules/qr/src/tl_mod_qr/resolve.py` (the hidden check and the expiry rule, lines 20-70)
- `packages/tl-modules/qr/tests/qr_world.py` and `conftest.py` (world helper the provided test imports)
- `packages/tl-modules/quality/src/tl_mod_quality/views.py` (list, detail and counts pattern, abridged)
- the provided test `docs/tickets/P2-QR/provided/T01_test_views.py` (161 lines)

## Allowed paths
- `packages/tl-modules/qr/src/tl_mod_qr/views.py` (bodies and the imports they need only)
- `packages/tl-modules/qr/tests/test_views.py` (create: byte-identical copy)
- `docs/reports/P2-QR/T01.md` (create)

## Provided test
`docs/tickets/P2-QR/provided/T01_test_views.py` is committed and is the spec. Copy it byte-identical to `packages/tl-modules/qr/tests/test_views.py`; do not edit it. Checked at r3 in that location: `ruff format --check`, `ruff check` and `pyright` report 0 findings, so `just check` stays green with the copy in place.

## Acceptance
```
cmp docs/tickets/P2-QR/provided/T01_test_views.py packages/tl-modules/qr/tests/test_views.py
just check
just gate packages/tl-modules/qr/tests/test_views.py
```
Expected: `cmp` silent; `just check` exit 0; the gate prints `gate: PASS`, every test in the provided file passing.

## Escalation triggers
A column the views need is not on the table; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test); a statement count above two on any call.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed (none expected). Commit subjects `P2-QR-T01: ...` with the session trailers; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
