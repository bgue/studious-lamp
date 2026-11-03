# P2-I1-T10b — WBS `total_hours` must not expose a hidden cost code (F1)

Status: ready
Tier: haiku
Review: full
Labels: core
Depends on: T10 (merged)
Branch: `p2/i1-t10b-total`
Worktree: `/home/user/wt/i1-t10b` (from `p2/i1` head)

## Goal
`WbsRow.total_hours` is the stored `total` line of the rollup, which includes the hours of a cost code the viewer may
not read; "total minus the visible `by_cost_code` lines" would reveal them (ADR-0016, finding F1 MD). After this ticket,
when any cost-code line of a node is hidden from the viewer, that node's `total_hours` is the sum of the visible
cost-code lines plus its `unallocated` line; otherwise it is the stored total, unchanged.

## Brief references (pasted)
Rollup lines per node in `cur_awp_rollup`: `total`, one `cost_code` line per cost code (`cost_code_id` set), and at most one
`unallocated` line (leaf with no cost codes). A parent's lines sum its children's. Decimals are `Decimal(str(value))`.
The later row (higher `as_of_seq`) of the same line replaces the earlier one (already how `_rollup` reads).

## Interfaces (verbatim)
```python
# packages/tl-modules/awp/src/tl_mod_awp/views.py (today)
ROLLUP_MEASURE: Final = "budget_hours"; ROLLUP_TOTAL: Final = "total"   # lines 44-45; ROLLUP_COST_CODE beside them
def _hidden(conn: Connection, ids: set[str]) -> set[str]: ...            # ids the viewer may not read
def _rollup(conn, scope, node_ids) -> tuple[dict[str, Decimal], dict[str, dict[str, Decimal]]]:  # totals, by_code (line 445)
```
Callers of `_rollup` use the first dict as `total_hours`. Keep the return shape.

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` lines 40-50 and 445-476
- `dev/accept/P2-I1/T10.py` (how a script opens the seed; copy that part)
- `packages/tl-modules/awp/src/tl_mod_awp/worker.py` (`build_worker`, `requeue_orphans`; signatures only)
may explore: `.accept/p2-i1.db` (read-only)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` (only `_rollup` and one constant `ROLLUP_UNALLOCATED = "unallocated"`)
- `dev/accept/P2-I1/T10b.py` (create), `docs/reports/P2-I1/T10b.md` (create)

## Steps
1. In `_rollup`, also read `unallocated` lines. After the loop, for each subject that has at least one `cost_code` line whose
   cost code is in `hidden_cost`: `totals[subject] = Σ visible by_code values + unallocated value (0 if none)`. Other
   subjects keep the stored total. Do not name or count the hidden line anywhere.
2. Acceptance `dev/accept/P2-I1/T10b.py --db PATH`: copy PATH to a temp file (the seed stays untouched); queue and run the
   rollup on the copy (`requeue_orphans(target)` then `build_worker(target)` and `runner.run_until_idle()`, `target =
   as_target(str(copy))`); then (a) `wbs_tree` has a `total_hours` for every leaf with a CWP and the total equals the sum of
   its `by_cost_code` plus nothing hidden (print `PASS unfiltered totals`); (b) wrap `views._hidden` so it also returns the id
   of one cost code that has a `cost_code` line (monkeypatch inside the script): that node's `total_hours` equals the sum of the
   visible lines, is lower than the unpatched total, and a node without that cost code is unchanged (`PASS hidden cost code
   total`); (c) the hidden code's code string is absent from `model_dump_json()` of every row (`PASS hidden code absent`).
   Ends `T10b ok`. No pytest. If the seed has no leaf with cost codes and a CWP allocation, print which and stop (Blocked).

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db     # if .accept/p2-i1.db is missing in the worktree
uv run python dev/accept/P2-I1/T10b.py --db .accept/p2-i1.db
uv run python dev/accept/P2-I1/T10.py --db .accept/p2-i1.db      # still ok
```
Expected: `just check` clean; the PASS lines, `T10b ok`, `T10 ok`. No `just gate` (no existing test directory touched).

## Tests to add
none (T11 writes the F1 guard in `test_views.py`).

## Report requirements
`docs/reports/P2-I1/T10b.md` <= 60 lines, <= 5 decisive output lines per command; deviations first. Subject
`P2-I1-T10b: ...`; no model names; commit trailer = the harness attribution line, then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if the fix needs a column the table lacks, a file outside Allowed paths, or a `tl_core` change.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
