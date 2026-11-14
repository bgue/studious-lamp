# P2-X1 S2 — Replay a keyed proposal before the budget and the dry run

kind: piece
review: full
branch: p2/x1-s2-replay-first
worktree: /home/user/wt/x1/s2

## Why
T07 proved Q3 red (report `docs/reports/P2-X1/T07.md` on `p2/x1-t07-idempotency-walk`, tests in
`packages/tl-mcp/tests/test_idempotency_walk.py` there). `proposals.submit` (`packages/tl-core/src/tl_core/services/proposals.py:725`)
runs the budget check (`:743`) and `precheck` (`:748`) before `propose` reaches its idempotency claim. So an agent that retries
a filed proposal with the same key is refused instead of getting the first proposal back:
(a) the agent is at its daily cap after the first filing -> `BudgetExceededError`; (b) the first filing's command would now
fail its dry run (for example the record key it creates is taken) -> `DuplicateKeyError`.

## Goal
In `submit`, when `command.idempotency_key` is set, look up the (agent, key) entry first, through the S1 helper
(`tl_core.services.idempotency`), in a read before the budget and the precheck:
- an existing entry with the same command name and body hash -> return the stored proposal (replay), with no budget
  use, no precheck, no event;
- an existing entry with a different command or hash -> the fixed 409 mismatch refusal, nothing written;
- no entry, or `idempotency_key` is None -> today's order unchanged (budget, precheck, propose with its claim).
The claim inside `propose` stays the authority for concurrent first filings (two first filings racing still give one row).
The replay re-reads the proposal id through the viewer filter as S1 does (hidden looks absent).

## Allowed paths
- `packages/tl-core/src/tl_core/services/proposals.py` (submit only; no other function changes behaviour)
- `packages/tl-core/src/tl_core/services/idempotency.py` (a read-only lookup helper if one is missing)
- `packages/tl-core/tests/test_idempotency_submit_order.py` (create)
- `docs/reports/P2-X1/S2.md` (create)

## Tests to add (test_idempotency_submit_order.py, SQLite)
1. Agent with budget 1 files with key K; a retry with K and the same body returns the same proposal id; no new row, no event.
2. First filing with key K creates record key R; R is then taken by another command; a retry with K returns the first proposal.
3. Retry with K and a different body -> the fixed mismatch refusal, before any budget or precheck error.
4. No key: an over-budget agent is still refused by the budget first (order unchanged).
5. Another agent with the same key value is not affected by the first agent's entry.

## Gate
`just check`; `just gate packages/tl-core/tests/test_idempotency_submit_order.py packages/tl-core/tests/test_idempotency.py packages/tl-core/tests/test_proposals*.py`
(drop a glob that matches nothing); `just gate-pg packages/tl-core/tests/test_idempotency_submit_order.py`.
Mutation: one sentinel plus at most 3 targeted mutants (lookup skipped, hash compare inverted, order restored), in the report, 3 lines.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; commit `P2-X1-S2: ...` with the session trailers. No model names in committed text.
