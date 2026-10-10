# Runbook — Review what agents proposed

Purpose: list, inspect, accept or reject the changes AI agents proposed through MCP, and recover when a proposal fails or an agent runs out of budget. Brief: §11.3, §18.12. Identity is the dev-only stub of ADR-0005.

## When to use
- Trigger: an agent (MCP client acting as `agent:<id>`) says it filed a proposal, `GET /proposals` shows pending rows, or an agent reports that it has used its daily proposals.

## Before you start
- Access needed: the repository, `uv`, and the dev ledger (`TL_DB`). To decide over HTTP: a token for a person (`uv run tl dev token add user:alice`).
- Safe to run during business hours: yes. Accepting runs a normal record command as you. Only `user:<id>` actors can accept or reject; an `agent:<id>` is refused. Which people may accept what is the permission model, a human gate: today any person may.

## Steps
1. See the queue, oldest first:
   ```
   uv run tl proposal ls --project P123            # pending; --status all|accepted|rejected|failed, --agent agent:triage
   uv run tl proposal show <id>                    # the proposal and the command it would run
   ```
   Expected: `id  pending  agent:triage  create_record  Create core.Record 'Weld NCR' in project:P123`. `show` prints `command CreateRecord` and one `  field json` line per field the agent set.
2. Decide. Look at the command first: accepting makes the change as you.
   ```
   uv run tl proposal accept <id> --actor user:alice
   uv run tl proposal reject <id> --reason "Duplicate of NCR-0040" --actor user:alice
   ```
   Expected: `accepted <id>` and `result <stream id>` (the new record, or the record that changed), or `rejected <id>`. The record's first event has `actor user:alice`, `source mcp:triage`, and the proposal's `Proposal.Created` event as its cause.
3. The same over HTTP:
   ```
   curl -s -H "Authorization: Bearer $TOKEN" 'localhost:8765/proposals?scope=project:P123'
   curl -s -X POST -H "Authorization: Bearer $TOKEN" localhost:8765/proposals/<id>/accept
   curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"reason":"no"}' localhost:8765/proposals/<id>/reject
   ```
   Add `"roles": ["manager"]` to the accept body (or `--role manager` on the CLI) to accept a workflow transition whose guard needs a role. A proposal never carries roles: you supply the ones you hold.

## Verify
- `uv run tl proposal ls --project P123 --status all` shows the proposal as `accepted` or `rejected`.
- `just demo P0-I6-B` runs the whole path on a temporary ledger and fails on any unmet expectation.

## Roll back
- A rejected proposal stays rejected; the agent files a new one. An accepted proposal made a normal change: undo it the normal way (void the record, retract the link). Events are never deleted.

## Troubleshooting
- `failed <id>` and `error: ConcurrencyError: ...`: the record changed after the agent looked (its `expected_version` is stale). Nothing was applied; the proposal is `failed` for good. Ask the agent to propose again from the current record (`get_record` gives the version).
- `failed <id>` and `error: GuardFailedError: ...`: a workflow guard does not pass now (a missing property, a missing link). Fix the record, then ask for a new proposal.
- `error: only a person (user:<id>) can accept a proposal`: use `--actor user:<id>`; an agent never decides.
- `error: proposal ... is already accepted`: someone decided it first (two people can race; one wins).
- An agent is told `agent:<id> has used its N proposals for today (UTC)`: the daily budget is `TL_AGENT_DAILY_PROPOSALS` (default 500). Accepted and rejected proposals still count. It resets at 00:00 UTC. Raise it for a throwaway dev ledger by setting the variable where the MCP server runs; a per-agent override waits for the permission model.
- A proposal the agent could not file (`error: ... already used`, `no record ...`): the proposal is checked with the accept-time rules when it is filed, so nothing reaches the queue.
- `tool mode 'write' is not available`: there is no direct-write mode in Phase 0. Who may write directly is a human gate (ADR-0005).

## Related
- `docs/tickets/P0-I6/README-B.md` (decisions B1 to B14), `docs/runbooks/api-and-mcp-dev.md`, ADR-0005, FANOUT decision D4.
