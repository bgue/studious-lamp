# P2-X2 S1 — Filing check: the module `user` word on the scope; hidden equals missing

kind: piece
review: full
branch: p2/x2-s1-filing-check
worktree: /home/user/wt/x2/s1
base: p2/x2 (seams committed: `agent_scope.check_filing` stub, called from `proposals.submit` and `proposals.propose`)

## Why
ADR-0027 F1 (accepted; moves from Phase 3 to X2): at filing the agent needs the module's `user` word on the command's scope
("may propose"); the command's own word (`controller`, `admin`) is checked only at accept (`_require_module_access`). Agent
tokens carry no scope today (`tl_core/auth/types.py:101-108`), so any agent files anywhere. Owner amendment to ADR-0027 is an
approval (95 line); this piece adds a one-paragraph amendment note to ADR-0027 only if the orchestrator says so: do not edit the ADR.

## Goal
1. Fill `tl_core.services.agent_scope.check_filing(conn, agent, command)`. For a command a module declares
   (`module_roles.command_index()`), resolve the agent's holder (`holder_for_actor`) and require the `user` word for that
   module on `command.scope` with `module_roles.require_word` (no new resolver). The command's own word is not asked.
2. Hidden equals missing (140): an agent that lacks the word is refused exactly as an agent filing into a scope that does not
   exist: same exception class, same status, same text with no module name, word or scope id that a missing scope would not
   also carry. Test: refusal text for a real scope without the word equals the refusal for a never-created scope (id masked).
3. Order inside `submit` and `propose` (decided here, do not move the wiring): replay first (X1 S2: a filed key answers before
   budget and precheck; it writes nothing and shows only what the agent filed, through `replay_result`'s viewer filter), then
   `check_filing`, then `agent_stop.require_not_stopped` (S3), then budget, then precheck. So an agent that lost its word after
   filing still gets its first answer on replay and nothing else; a fresh filing is refused before it costs a budget unit
   or a dry run. Test the order with a key: replay allowed after the word is revoked; a new key refused.
4. Core commands (no module in `command_index()`; Q1 decided by the orchestrator 2026-11-14, closed by default, ADR-0009): the agent must hold at least one module role (any module, any word) on the scope, read through the same grant lookup the module check uses; otherwise the same uniform refusal as a scope that does not exist. No new grant type. Add a test for each side (core command with no grant refused as missing; with any grant files).
5. Filing refused: no event, no budget use, no idempotency row (the check runs before `idempotency.record`; assert row count).
6. The scenario agents of I6 are granted before I6 T04: do not change them; list in the report which existing tests file
   as an agent without a grant and had to gain one (`GrantModuleRole` in the fixture), a consequential pin.

## Allowed paths
- `packages/tl-core/src/tl_core/services/agent_scope.py` (`check_filing` and helpers)
- `packages/tl-core/tests/test_agent_filing_check.py` (create)
- existing tests that file as an agent and now need a grant (fixture-only edits; list in the report)
- `docs/reports/P2-X2/S1.md` (create)
Read-only: `proposals.py` (wiring is committed), `module_roles.py`, ADR-0027, ADR-0016.

## Tests to add (test_agent_filing_check.py)
1. No word: refused; with `GrantModuleRole` user: files; `read` only: refused.
2. Refusal equals the missing-scope refusal (class, text, API status via the existing error mapper).
3. The command's own word is not needed at filing: an agent with `user` files a `controller` command (accept still refused
   for a person without it; existing accept test).
4. Replay-order test (item 3); refusal writes no event, no idempotency row, no budget use.
5. Both entry points: `submit` and `propose`.
6. Five readers: the refusal is identical for a viewer with clearance and one without (it reads no record text).

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); `just gate packages/tl-core/tests/test_agent_filing_check.py packages/tl-core/tests/test_proposals.py packages/tl-core/tests/test_idempotency_submit_order.py packages/tl-mcp/tests packages/tl-api/tests/test_confidentiality_walk.py`.
Mutation: one sentinel plus at most 4 targeted mutants (check skipped, word `user` swapped for the command's word, refusal text differs from missing, check moved before replay), 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; commit `P2-X2-S1: ...` with the session trailers; no model names in committed text.
