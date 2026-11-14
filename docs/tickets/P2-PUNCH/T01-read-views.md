# P2-PUNCH-T01 — Read views: punch list, detail and counts

Status: ready (r4: the provided test and the interface stub are committed on `p2/punch`; dispatch now)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: S2 (merged)
Branch: `p2/punch-t01-read-views`
Worktree: harness-created under `/home/user/wt/punch/t01` (from `p2/punch` head)

## Goal
`tl_mod_quality.views` gives the CLI, API, MCP and screens one read layer: the punch list, one item's detail and counts by state. Nothing writes; no access word is
checked here (entry points do). Every read takes keyword-only `viewer=`, default `confidentiality.LOWEST`, and applies the same hidden filter as `api.py` (the subject join of S2 is inside `hidden_sql`) before LIMIT and before counting.

## Brief references (pasted)
> Pattern: `packages/tl-modules/quality/src/tl_mod_quality/api.py` (`open_punch_for`: `not_hidden_each("r.id", viewer)` joined into `text()` SQL over `cur_core_record r`, `r.voided = :no`, state `COALESCE(r.status, :open)`, `MAX_ROWS` 500). Table `cur_quality_punch_item` (S1; columns in the README "Record shape"); `r.key` is the item number; the source key is read with one LEFT JOIN to `cur_core_record` on `source_id`.
> Hidden looks like missing: a hidden item is absent from lists, its detail is `None`, counts and `total` never include it. Statements per call: at most two (no per-row query).

## Interfaces (in the tree as a stub: the three dataclasses are final, the three function bodies raise `NotImplementedError`; fill the bodies, change no name, field or signature)
```python
@dataclass(frozen=True)
class PunchRow:      # id (the record id, for commands; never printed), key, subject, state, category, area, system, due_on, assignee, raised_by, source_key (str | None); all str | None except key, subject, state, category, raised_by
@dataclass(frozen=True)
class PunchDetail:   # row: PunchRow, description, cleared_by, cleared_on, clear_note, verified_by, verified_on, reopen_count: int, last_reopen_reason, void_reason, source_type (str | None), version: int
@dataclass(frozen=True)
class PunchPage:     # rows: list[PunchRow], total: int      (total = visible rows matching the filters, before limit)
def punch_list(conn, scope, *, state=None, area=None, system=None, assignee=None, category=None, source_key=None, overdue=False, today=None, limit=200, viewer=LOWEST) -> PunchPage   # ordered by key; limit clamped 1..500; unknown state or category is ValueError; overdue needs today (ValueError without) and means state Open and due_on < today; source_key is the key of the source record (an unknown one gives an empty page)
def punch_detail(conn, scope, key, *, viewer=LOWEST) -> PunchDetail | None
def punch_counts(conn, scope, *, viewer=LOWEST) -> dict[str, int]   # keys Open, Cleared, Verified, Void, each present (0 allowed), visible items only
```
`today` is an ISO date string (`YYYY-MM-DD`, compared as text with `due_on`); entry points pass `date.today().isoformat()`; the views never read the clock. A key of another project, or an unknown one, gives `None` (`scope` is checked: `r.scope = :scope`).

## Context (read these, nothing else)
- `packages/tl-modules/quality/src/tl_mod_quality/{api.py, names.py, views.py}`, `docs/reports/P2-PUNCH/S2.md`
- `packages/tl-modules/quality/tests/punch_world.py` and `test_punch_visibility.py` (lines 1-60), `packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py` (the list/detail pattern, abridged)
- the provided test `docs/tickets/P2-PUNCH/provided/T01_test_views.py` (committed at r4; do not edit it); `packages/tl-modules/quality/tests/conftest.py` (fixtures `db`, `world`: they exist, nothing to add)

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/views.py` (bodies only)
- `packages/tl-modules/quality/tests/test_views.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-PUNCH/T01.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/quality/tests
```
Expected: the provided tests pass in `test_views.py`, the rest of the folder unchanged; `cmp` of the test and the provided copy identical.

## Tests to add
The provided test (copied). It builds the ledger only through commands (`World.call` of `punch_world.py`; a hidden source is a restricted correspondence item made with the helper, never a projection write): list ordering and filters (state, area, system, assignee, category, source key, overdue with a fixed `today`), `total` equals rows, `limit` clamps, detail fields after clear, verify and reopen, a free-standing item has `source_key` None, a hidden-source item is absent from list, detail (None) and counts for the default viewer and present for a cleared one, an unknown key and a key of another project give None.

## Escalation triggers
- A column the detail needs is not on the table; the provided test fails on a line the ticket does not explain (write the answer under Blocked; do not edit the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed (none expected). Commit subjects `P2-PUNCH-T01: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
