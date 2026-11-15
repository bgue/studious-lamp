# P2-X2 S3b — A stopped agent's proposal stays pending when accepted through `accept_or_fail`

kind: piece (core fix, found by the T05 demo)
branch: p2/x2-s3b-held-accept   worktree: /home/user/wt/x2/s3b   base: p2/x2@be36175a

## Why
S3 design: while an agent is stopped, accepting what it filed is refused and the proposal STAYS PENDING (it reads as
held; `Agent.Resumed` lifts it). `accept_proposal` does that, but `accept_or_fail` catches every `ServiceError`
(`ForbiddenError` is one) and records `Proposal.Failed`, so the proposal leaves pending and `held_count` drops
(T05 demo clause 4: 2 -> 1).

## Interface
- `agent_stop.AgentStoppedError(ForbiddenError)`: the one error `require_not_stopped` raises (text `STOPPED_TEXT`
  unchanged). Same class family, so every caller that maps `ForbiddenError` (403, CLI error, MCP error) is unchanged.
- `accept_or_fail` re-raises `AgentStoppedError` untouched, with nothing appended (no `Proposal.Failed`, no events),
  as it already does for `RiskNotAcceptedError`. Every other failure keeps today's behaviour. Hidden == missing unchanged.
- Callers (CLI `tl proposal accept`, API accept route, MCP tests, batch review) get the plain refusal; none needs a change.

## Allowed paths
- `packages/tl-core/src/tl_core/services/agent_stop.py`, `packages/tl-core/src/tl_core/services/proposals.py` (the one except clause)
- `packages/tl-core/tests/test_agent_stop.py`, `packages/tl-cli/tests/test_cli_agent_stop.py`
- `docs/tickets/P2-X2/S3b-held-accept.md`, `docs/reports/P2-X2/S3b.md`

## Tests
1. Service: `accept_or_fail` on a stopped agent's proposal raises `ForbiddenError` with `STOPPED_TEXT`; event rows
   unchanged; status pending; `held_count` unchanged; after `Agent.Resumed` the accept succeeds.
2. CLI: `tl proposal accept` on the stopped agent's proposal exits 1 with the stop text, no `failed` line, no new event,
   `tl agent stopped` still shows `held 1`; after `tl agent resume` the accept prints `accepted`.
3. A non-stop refusal through `accept_or_fail` still records `Proposal.Failed` (existing tests keep passing).
Mutation: sentinel plus at most 3 targeted (re-raise removed; stop error class not raised; failure recorded before re-raise).

## Gate
`NODE_OPTIONS=--max-old-space-size=6144 just check`; `just gate` on test_agent_stop.py, test_proposals.py, tl-cli tests,
test_api_agent_stop.py; `just gate-pg packages/tl-core/tests/test_agent_stop.py`.
