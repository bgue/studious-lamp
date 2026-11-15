# P2-X2-T04 — Walking tests: refusals look like missing, cap text without counts, five-reader walk of held count and stopped list

Status: staged (dispatch after S1, S2, S3, T03 are merged; the supervisor re-reads the merged helper names below before dispatch, round 4)
Tier: haiku
kind: ticket
review: full
Labels: tests, security
Depends on: S1, S2, S3, T03
Branch: `p2/x2-t04-scope-walks`
Worktree: `/home/user/wt/x2/t04`

## Goal
Tests only, no source change. Three walks that pin demo clauses 1, 3 and 6 at the edges an agent and a reader really use: (A) an agent refused at filing gets the same answer as for a
scope that does not exist; (B) the queue-cap refusal is one fixed text with no number or id; (C) the held count and the stopped list, read as five kinds of reader, name no hidden record and count none.
The `AGENT_MAY_NOT` rows were added by T01 (D9); this ticket asserts they are present and that the agent actually gets 403, it does not add them again.

## Brief references (pasted)
> AGENTS.md: a hidden record answers as one that never existed; a new route, tool, feed, webhook or export that can carry record text needs a walking test as five kinds of reader.
> The viewer defaults to the lowest clearance; a test that widens the default to get green is wrong. An admin is not a clearance (ADR-0016): the admin without a clearance row cannot read `privileged`.
> Phrase book: 140 hidden looks exactly like missing (status, text, counts); 141 the visibility filter runs before LIMIT and before counting.
> P2-X2 demo 1: an agent without the module `user` word files: refused, the same as a scope that does not exist. 3: the cap is reached: refused with a fixed text that shows no counts.
> 6: held count and stopped list, read as five kinds of reader, name no hidden record and count none.

## Interfaces (names; the supervisor pastes the merged signatures at dispatch)
- Filing check (S1, `tl_core/services/agent_scope.check_filing`): refusal equals the missing-scope refusal (class, text, API status). Agent fixtures hold `GrantModuleRole` through the shared helpers
  (`ensure_agent` in `packages/tl-mcp/tests/mcp_harness.py`, `packages/tl-api/tests/harness.py`, `tl_mod_correspondence.confseed`); a test of "no word" revokes or never grants it.
- Cap (S2): `QueueFullError`, API row `queue_full` 429, fixed text `this review queue is full; ask a reviewer to clear it, then file again`; setting `ai.agents.max_pending_per_project` (set with `ChangeSetting` at the project layer).
- Stop (S3/T01): `agent_stop.list_stopped(conn, viewer, limit=200) -> list[StoppedAgent]`, `held_count(conn, agent, viewer)`; routes `GET /admin/agents/stopped`, `POST /admin/agents/stop|resume`; `AGENT_MAY_NOT` rows in
  `packages/tl-api/tests/test_auth_review.py` for `admin.agents.stop`, `admin.agents.resume`, `admin.agents.list`, `admin.command.StopAgent`, `admin.command.ResumeAgent`.
- Seed the hidden world and five readers as `packages/tl-api/tests/test_confidentiality_walk.py` and `packages/tl-mcp/tests/test_confidentiality_walk.py` do (`seed_hidden_world`, `TOKENS`); file a proposal that
  carries a privileged record under `confidentiality.system_view()` (a plain `propose` reads back through the caller's viewer and would raise `ProposalNotFoundError`).

## Context (read these, nothing else; may exceed six because it is tests only, each file is read in part)
- `packages/tl-api/tests/test_api_agent_stop.py` (the five-reader seed and `held` assertions: copy, do not import) and `packages/tl-api/tests/test_confidentiality_walk.py` (lines 1-120)
- `packages/tl-mcp/tests/test_idempotency_walk.py` (an agent through MCP, refusal shapes) and `packages/tl-mcp/tests/test_confidentiality_walk.py` (lines 1-80)
- `packages/tl-core/tests/test_agent_filing_check.py`, `packages/tl-core/tests/test_agent_queue_cap.py`, `packages/tl-core/tests/test_agent_stop.py` (what is already pinned at the service level; do not repeat it)
- `packages/tl-api/tests/test_auth_review.py` (lines 355-400)
may explore: (none)

## Allowed paths
- `packages/tl-api/tests/test_agent_scope_walk.py` (create)
- `packages/tl-mcp/tests/test_agent_scope_walk.py` (create)
- `docs/reports/P2-X2/T04.md` (create)
Read-only: everything else. If a walk needs a helper change in a shared harness, stop (Escalation).

## Tests to add
`packages/tl-api/tests/test_agent_scope_walk.py` (parity harness, both adapters):
1. Refusals look like missing (A): an agent with no module word on `project:P1` and the same agent filing on a scope that does not exist get equal status, error code and body text, for the
   HTTP command route and for a proposing route; no event, no idempotency row, no budget use written by the refused call.
2. Cap text (B): fill a project queue to a lowered limit (2); the next filing is 429 `queue_full`; the body equals the fixed text for two projects and two limits; the body and headers contain no digit
   taken from the limit, the count, a project id or an agent id (assert the body text has no digit at all).
3. Held count and stopped list (C), five readers (admin without a clearance row, plain user, document controller, the person named on the privileged item, full clearance), service level through
   `agent_stop.list_stopped` with `viewer_for_actor` as T01 does, plus the admin over HTTP: one stopped agent, three pending proposals, one carrying a privileged record. For every reader who may not read it:
   `held` equals the count in a world that never had that proposal, and the serialised list (`model_dump_json`) contains neither the record id nor its title nor the proposal id. The reader who may read it counts it.
   The count is the same with `limit=1` and `limit=200` (141: filtered before any LIMIT).
4. Agents and the three admin routes: the agent token gets 403 on stop, resume and stopped; the five `AGENT_MAY_NOT` entries above are present (import `AGENT_MAY_NOT` from `test_auth_review`).
5. The route count: the GET `/admin/agents/stopped` route is found by the walk's own route listing (a count assertion, L-P1-I3-11), so the walk cannot pass by finding nothing.
`packages/tl-mcp/tests/test_agent_scope_walk.py`: (a) the MCP tool for a proposing write, called by an agent with no word on the scope and for a scope that does not exist, answers the same error
text and code; (b) at the cap the tool answers the fixed queue text with no digit; (c) no MCP tool name contains `stop` or `resume` (an agent cannot stop itself or another; the tool list is walked).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-api/tests/test_agent_scope_walk.py packages/tl-mcp/tests/test_agent_scope_walk.py packages/tl-api/tests/test_api_agent_stop.py packages/tl-api/tests/test_auth_review.py packages/tl-api/tests/test_confidentiality_walk.py packages/tl-mcp/tests/test_confidentiality_walk.py tests/services/test_proposals.py
just gate-pg packages/tl-api/tests/test_agent_scope_walk.py
```
Expected: all pass on both adapters; `just check` clean.

## Report requirements
Standard report plus: for each of walks 1-3, the assertion that would fail if the guard were removed (one line each; the reviewer picks one and checks it by reading, nothing is mutated); output of the gate (<= 5 lines).

## Escalation triggers
Stop and write *Blocked* if a refusal differs between the no-word and missing-scope cases (that is an S1 defect, not a test to loosen); if the cap text carries a digit; if a hidden record is counted or named
for any reader; if a shared harness must change; if a walk cannot be built without widening the viewer.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
