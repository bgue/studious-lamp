# P2-X2 S2 — Project pending-queue cap: setting, counted after the viewer filter, fixed refusal text

kind: piece
review: full
branch: p2/x2-s2-queue-cap
worktree: /home/user/wt/x2/s2
base: p2/x2 after S1 (merged) and S3 (merged @a03515d2)
dispatch: ONLY after S1 is merged. S1 rewrites `services/agent_scope.py`; S2 adds a function to the same file, so it branches from the trunk that holds S1's version.

## Why
12-extension-plan P2-X2 demo 3: a project's pending queue cannot be flooded by agents. A cap on pending proposals per queue, a setting, refused with a fixed text that shows no counts
(AGENTS.md: a count can leak a hidden record, 140/141). Additive: one setting, one error class, no event change, no data migration.

## Setting (gated: 95 line, orchestrator holds the APPROVALS line before merge)
Key `ai.agents.max_pending_per_project`, in `schema/settings/platform.yaml` next to `ai.agents.daily_proposals`:
`type: int`, `default: 100`, `validation: {minimum: 1, maximum: 100000}`, `scopes: [platform, company, project]`, `risk: advanced`, lockable as the other keys, `since` the current
release string used by `idempotency.retention_days`. Description: "How many proposals may wait for review in one queue (a project, or the company)". No 0 value: the cap cannot switch filing off
(`ai.agents.daily_proposals` 0 does that). Consequential pins: the key set in `packages/tl-core/tests/test_settings_definitions.py`, and the TUI settings list snapshot
(`packages/tl-tui/tests/__snapshots__/test_snapshots_settings/`) if it breaks; list both in the report.

## Goal
1. In `tl_core.services.agent_scope` add `check_queue_cap(conn, agent, command) -> None`. The queue is `command.scope` (`project:<id>` or `company`). The limit is
   `value_of(conn, "ai.agents.max_pending_per_project", project=<id>)` for a project scope, the company value for `company`.
2. The count is the pending proposals in that scope **that the filing agent's viewer may read**: take every pending row of `cur_proposals` for the scope, collect carried ids
   (`proposals._carried_ids`, as `agent_stop.held_count` does), run `confidentiality.hidden_among` with the viewer from `tl_core.integration.actor_access.viewer_of(conn, agent)`
   over all of them, and count the rows with none hidden. The filter runs over every row before the count and before any LIMIT; do not add a LIMIT that stops early on the raw rows.
   Trade-off, record in the report: a pending proposal that carries a record the agent cannot read does not count against that agent's cap (the alternative leaks it).
3. Refusal when `count >= limit`: new `QueueFullError(ServiceError)` in `services/errors.py`, text fixed and identical for every queue and every reader:
   `this review queue is full; ask a reviewer to clear it, then file again`. No number, no scope id, no agent id, no limit in the text, the exception arguments or any log line. Add the
   `tl_api/errors.py` table row (`queue_full`, 429) and satisfy `packages/tl-api/tests/test_error_table.py`; MCP tools surface it as the other service errors do (no new tool code).
4. Wire in `proposals.py` (the one edit outside `agent_scope.py`, two lines, one in `propose` at line ~501 and one in `submit` at ~764): `agent_scope.check_queue_cap(uow.conn(), agent, command)` after
   `agent_stop.require_not_stopped` and before the budget lines. Decided order: replay, `check_filing`, `require_not_stopped`, `check_queue_cap`, budget, precheck. A refused filing writes no
   event, uses no budget, writes no idempotency row; an idempotent replay of a filed key answers before the cap (it runs first, unchanged).
5. Accept is untouched (an accept reduces the queue). Person-filed action proposals (`ACTION_PROPOSAL_TOOL`) and rule proposals do not call `check_queue_cap` (they do not call `check_filing`).
6. Hidden equals missing is not in play (the scope is already known to the agent after S1); the text still reads no record text.

## Allowed paths
- `packages/tl-core/src/tl_core/services/agent_scope.py` (add `check_queue_cap` and helpers; keep S1's `check_filing` as merged)
- `packages/tl-core/src/tl_core/services/proposals.py` (the two wiring lines only)
- `packages/tl-core/src/tl_core/services/errors.py` (`QueueFullError`), `packages/tl-api/src/tl_api/errors.py` (one row)
- `schema/settings/platform.yaml` (the key)
- `packages/tl-core/tests/test_agent_queue_cap.py` (create); consequential pins as above; `packages/tl-api/tests/test_error_table.py` only if it lists rows
- `docs/reports/P2-X2/S2.md` (create)
Read-only: `agent_stop.py` (copy its `held_count` shape), `confidentiality.py`, ADR-0016, ADR-0027.

## Tests to add (test_agent_queue_cap.py; adapters via the existing parity fixtures)
1. At the limit the next filing is refused; one below it files; a lowered project value (`ChangeSetting`, project layer) changes the limit for that project only; company scope uses the company value.
2. Refusal text equals the fixed text for two projects, two agents, two limits; it contains no digit and no scope or agent id (assert on `str(exc)` and `exc.args`).
3. Both entry points: `submit` and `propose`; refusal writes no event, no idempotency row, no budget use (`proposals_today` unchanged).
4. Order: a stopped agent gets the stop text, not the cap text; an agent without the word (S1) gets S1's refusal, not the cap text; a replayed key answers when the queue is full.
5. Viewer filter: at the limit, a pending proposal carrying a hidden record (for the filing agent) is not counted: with `limit - 1` visible and one hidden pending the filing succeeds, and the result
   equals a world where the hidden proposal never existed. Five readers do not apply (the viewer is the agent's); assert the cap decision is identical when a person with full clearance files
   the same count of visible ones.
6. Accepting or rejecting a pending proposal reopens the queue; other scopes' queues do not count.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); `just gate packages/tl-core/tests/test_agent_queue_cap.py packages/tl-core/tests/test_agent_filing_check.py packages/tl-core/tests/test_agent_stop.py tests/services/test_proposals.py packages/tl-core/tests/test_idempotency_submit_order.py packages/tl-core/tests/test_settings_definitions.py tests/settings/test_phase2_keys.py packages/tl-api/tests/test_error_table.py packages/tl-api/tests/test_api_settings.py packages/tl-tui/tests/test_snapshots_settings.py packages/tl-mcp/tests`; `just gate-pg packages/tl-core/tests/test_agent_queue_cap.py`.
The test path for proposals is `tests/services/test_proposals.py` (there is no `packages/tl-core/tests/test_proposals.py`).
Mutation: one sentinel plus at most 4 targeted mutants (cap check skipped in `submit`, filter skipped before count, `>=` swapped for `>`, count includes other scopes, text carries a number), 3 lines in the report.

## Report
Builder return <= 15 lines; report <= 60 lines; commit `P2-X2-S2: ...` with the session trailers; no model names in committed text.
