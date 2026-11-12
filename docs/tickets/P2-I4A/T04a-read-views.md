# P2-I4A-T04a — Read views: requisitions and work orders

Status: ready (S2 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality
Depends on: S2 (merged)
Branch: `p2/i4a-t04a-read-views`
Worktree: harness-created under `/home/user/wt/i4a/t04a` (from `p2/i4a` head)

## Goal
`tl_mod_requisitions.views` (today an empty stub) gives the API, CLI, MCP and screens one read layer: requisition list and detail, work order list and detail. Nothing writes; no access word is checked here (entry points do). Every read takes keyword-only `viewer=`, default `confidentiality.LOWEST`, and applies the same hidden filter as `api.py` before LIMIT.

## Brief references (pasted)
> Pattern: `packages/tl-modules/requisitions/src/tl_mod_requisitions/api.py` (`open_requisitions_for`, `work_order_for`: `not_hidden_each("r.id", viewer)` joined into text() SQL over `cur_core_record r`, `r.voided = :no`, state `COALESCE(r.status, :requested|:open)`, `MAX_ROWS` 500). Reuse `RequisitionRow` and `WorkOrderRow` from `api.py`; do not copy them.
> Tables: `names.TABLES` (one per kind, plus `WORK_ORDER_TABLE`); `KINDS` maps `labor|material|general|scaffold` to the type. Scope is `r.scope`.
> Hidden looks like missing: a hidden requisition (or the work order of one) is absent from lists and its detail is `None`; limits and counts never include it.

## Interfaces (create in `views.py`; signatures fixed)
```python
@dataclass(frozen=True)
class RequisitionDetail:      # row: RequisitionRow, fields: dict[str, str | None] (the kind-specific columns as stored, e.g. craft, headcount, start_date, end_date; lines as stored for material), work_order: WorkOrderRow | None
@dataclass(frozen=True)
class WorkOrderDetail:        # row: WorkOrderRow, requisition_key: str
def requisition_list(conn, scope, *, kind=None, state=None, requester=None, for_record=None, limit=200, viewer=LOWEST) -> list[RequisitionRow]   # by key; limit clamped 1..500; for_record is a record id; unknown kind is ValueError
def requisition_detail(conn, scope, key, *, viewer=LOWEST) -> RequisitionDetail | None
def work_order_list(conn, scope, *, state=None, assigned_to=None, limit=200, viewer=LOWEST) -> list[WorkOrderRow]
def work_order_detail(conn, scope, key, *, viewer=LOWEST) -> WorkOrderDetail | None
```
Statements per list call: at most one per kind (no per-row query).

## Context (read these, nothing else)
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/{api.py, names.py, views.py}`
- `docs/reports/P2-I4A/S2.md`, `packages/tl-modules/requisitions/tests/{req_world.py, test_api_and_visibility.py (lines 1-60)}`
- the provided test `docs/tickets/P2-I4A/provided/T04a_test_views.py`

## Allowed paths
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/views.py`
- `packages/tl-modules/requisitions/tests/test_views.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-I4A/T04a.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/requisitions/tests
```
Expected: 6 passed in `test_views.py`, the rest of the folder unchanged; `cmp` of the test and the provided copy identical.

## Tests to add
The provided test (copied). It changes state only through commands (`World.call`). A hidden-subject case cannot be made by a command today (an IWP is not confidential); the filter is the one `api.py` already tests (`test_api_and_visibility.py`), and you reuse its helper, not a new one.

## Escalation triggers
- A kind-specific column the detail needs is not on the table; the provided test fails on a line this ticket does not explain (write the answer under Blocked; do not edit the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T04a: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
D-r3c (orchestrator, 2026-11-11): attempt 1 blocked only on pyright in the provided test; the orchestrator added `assert ... is not None` narrowing to the test and its provided copy (63b5e3ac); check 0, gate 51 passed, full review pass. The report's Blocked lines are historical.
