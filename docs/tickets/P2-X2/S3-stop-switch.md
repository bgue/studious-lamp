# P2-X2 S3 — Agent stop switch: events, projection, admin commands, filing and accept checks

kind: piece
review: full
branch: p2/x2-s3-stop-switch
worktree: /home/user/wt/x2/s3
base: p2/x2 (seams committed: `agent_stop.is_stopped` and `require_not_stopped` stubs, called from `proposals.submit`, `propose`, `accept_proposal`)
labels: schema (gated: the orchestrator holds the APPROVALS line before merge)

## Why
An admin needs to stop one agent and hold what it filed (12-extension-plan P2-X2 demo 4, 5). ADR-0029 decision 6: the stop
overrides every later policy accept; the policy path calls the one stop check this piece exposes (`agent_stop.is_stopped`),
it does not copy it. Authorization is closed for agents: an agent cannot call stop or resume (ADR-0009).

## Goal
1. Two additive event types on the agent's account stream: `Agent.Stopped {agent, reason?}` and `Agent.Resumed {agent}`, plus
   one projection table (current state per agent: stopped flag, stopped_at, stopped_by), generated from `schema/**` as the
   repo does (`just gen`; never hand-write DDL). No existing event or table changes; no data migration. Append-only.
2. Commands `StopAgent` and `ResumeAgent` (access word `admin`, row in `schema/settings/access-words.yaml` style table as
   other admin commands), actor must be a person with admin; an agent actor is refused. Stopping a stopped agent or resuming a
   running one is a quiet no-op result (no event), as `GrantModuleRole` does for a held role.
3. Fill `agent_stop.is_stopped(conn, agent)` and `require_not_stopped(conn, agent)`: fixed refusal text, no counts, no
   agent id echo beyond what the caller sent. Used at filing (`submit`, `propose`: before budget) and at accept
   (`accept_proposal`: the pending proposal stays pending, so it shows as held; `resume` lifts both).
4. Read: `list_stopped(conn, viewer)` and `held_count(conn, agent, viewer)`. Held = pending proposals of the agent. Both run the
   viewer filter before counting and before LIMIT (141); a proposal that carries a record the viewer may not read is not
   counted and not named (140). An admin is not clearance (ADR-0016).
5. Registry lines for the two commands only (command table, access word); routes, CLI and screen are tickets T01-T03.
6. `Agent.Stopped` and `Agent.Resumed` carry ids and an optional short reason; if the stream appears on `/events`, `/stream`
   or the change feed, apply the existing `hide_stream_types` pattern only if the events can carry record text (they cannot:
   state which in the report).

## Allowed paths
- `packages/tl-core/src/tl_core/services/agent_stop.py` (fill), `packages/tl-core/src/tl_core/projection/agent_stop.py` (create)
- `schema/core/agent_stop.yaml` (create) and the generated files `just gen` writes for it
- command and access-word registry lines for `StopAgent`, `ResumeAgent` (and the table file the repo uses for them)
- `packages/tl-core/tests/test_agent_stop.py`, `packages/tl-core/tests/test_agent_stop_projection.py` (create)
- `docs/reports/P2-X2/S3.md` (create)
Read-only: `proposals.py` (wiring is committed), `agent_scope.py`, `module_grants.py` (pattern), ADR-0009, ADR-0016, ADR-0029 §6.

## Tests to add
1. Stop, then filing refused with the fixed text (no counts), accept of a pending proposal refused and the proposal stays pending;
   resume lifts both; ledger shows `Agent.Stopped` then `Agent.Resumed`, nothing rewritten (event rows unchanged).
2. An agent actor cannot stop or resume (refused); a non-admin person cannot; admin can; double stop writes no second event.
3. Projection rebuild equals live (replay the stream, compare table) on both adapters.
4. `held_count` and `list_stopped` as five kinds of reader: a hidden record in a held proposal is not counted or named; counts
   equal those of a world where the record never existed. Filter before LIMIT.
5. `is_stopped` is callable alone (the ADR-0029 contract) and agrees with `require_not_stopped`.
6. Stop of an agent that never filed, or of an unknown agent id: refused as unknown with one fixed text (no existence oracle).

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); `just gen` clean (no diff after a second run);
`just gate packages/tl-core/tests/test_agent_stop.py packages/tl-core/tests/test_agent_stop_projection.py packages/tl-core/tests/test_proposals.py packages/tl-core/tests/test_idempotency_submit_order.py`; `just gate-pg packages/tl-core/tests/test_agent_stop_projection.py`.
Mutation: one sentinel plus at most 5 targeted mutants (stop check skipped at filing, skipped at accept, resume leaves flag, held count unfiltered, agent actor allowed), 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; commit `P2-X2-S3: ...` with the session trailers; no model names in committed text.
