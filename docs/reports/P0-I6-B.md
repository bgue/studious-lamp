# Report — P0-I6 workstream B: MCP write tools, the proposal review queue, the feed over the API

Supervisor session: 2026-10-10. Branch `p0/i6b` (base `p0/i6`, then `p0/i6` at 4e7e21d merged in). Plan and decisions B1 to B19:
`docs/tickets/P0-I6/README-B.md`. Runbook: `docs/runbooks/proposal-review-queue.md`.

## Outcome
Objective met: yes. An MCP agent reads, posts to the feed (labelled with the agent) and proposes record changes; a proposal is checked with the
accept-time rules, waits in a review queue, and does nothing until a person accepts it from the CLI or the API; the change is then made by that
person with `source=mcp:<agent>` and the proposal as its cause. Each agent has a daily proposal budget. No tool has a write mode, and an `agent:`
token cannot change a record over REST. The feed is served over the API and `ApiClient`, and the remote TUI shows it live.
Demo path verified: `just demo P0-I6-B` ran clean on the final tree (and, before T20/T21 merged, against reference implementations of them).

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I6-T20 `tl proposal ls\|show\|accept\|reject` | merged | 1 (pass, no findings) | 14 provided tests; implementer noted `show` prints empty containers (`numbering {}`), left as specified |
| P0-I6-T21 ApiClient review-queue methods | merged | 1 (pass, no findings) | 9 provided tests; `get_proposal` later gained a required `scope` (B19) and its provided test followed |

Supervisor-built pieces (reviewed by a fresh reviewer at 7b3769f: pass; four low findings fixed in S28):
S20 feed routes and `FeedApi`; S21 `schema/core/proposals.yaml`; S22 proposals service, projector and routes; S23 MCP write tools and tool modes;
S24 stubs and provided tests; S25 demo, runbook, docs; S26 agent-token rule (B15); S27 `RemoteClient` feed and live feed refresh; S28 reviewer fixes.

## Gates (final tree)
| Gate | Result |
|---|---|
| `just check` | clean (ruff, format, pyright, codegen drift, OpenAPI drift, licences) |
| `just test` | 3233 passed (rerun after the S28 test fix) |
| `just test-tui` | 480 passed, 24 snapshots |
| `just test-parity` | 1418 passed on SQLite and Postgres |
| `just demo P0-I6-B` | `P0-I6-B demo ok` |
| Known red at the start (`test_every_method_exists_with_the_same_parameters`) | green: `ApiClient` has the six feed methods |

One `just test` run before S28 failed `test_no_suggestion_without_hold_or_without_a_record_or_after_retraction` (a WS-A test that retracted as a
different actor than the author, which B16 now refuses); the test now retracts as the author. An earlier run failed
`test_a_live_server_answers_reads_commands_queries_and_errors` once under load (3 s remote call timeout, a real server in a thread); it passed alone,
on the next full run and in the final runs, and touches nothing of this workstream.

## REVIEW-SUPERVISOR-PIECES
Reviewed: the feed routes and their error mapping (`routes/feed.py`, `commands.py`), the proposals service (`services/proposals.py`,
`projection/proposals.py`, `routes/proposals.py`), the MCP write layer (`tl_mcp/write_tools.py`, `modes.py`) and B15. Verified by the reviewer on both
adapters: no MCP path changes a record; spoofed actor and source arguments are ignored; `post_feed` makes only `references` suggestions; agents cannot
accept or reject; an accept carries the right actor, source and causation; a stale accept appends only `Proposal.Failed`; three simultaneous accepts
give exactly one accept; the budget holds under 8 concurrent proposals and cannot be evaded by changing scope.
Added after that review (S27, S28): `RemoteClient` feed calls, the feed-pane refresh, keyword factory calls, post ownership, agent source override,
scoped `get_proposal`. These carry their own tests; they have not been through a second review.

## SCHEMA_APPROVALS
`schema/core/proposals.yaml` (S21, commit 4f517e9): `Proposal.Created|Accepted|Rejected|Failed` payload classes and `ProposalRow` (`cur_proposals`).
Delegated under the FANOUT; the orchestrator recorded it in `APPROVALS.md`. No new dependency, so no licence to name.

## Deviations from plan
- `accept_proposal(uow)` raises the command's refusal; `accept_or_fail(factory)` records `Proposal.Failed` in a fresh unit of work (B2, accepted).
- `Proposal.*` events are transparent to feed cards, which edits WS-A's `feed/cards.py` and `tests/test_feed_cards.py` (B6, accepted).
- B3 changed into B15: an `agent:` token is refused on every record-changing command and file write (403 `agent_must_propose`).
- Edited existing tests of other workstreams, each for a stated reason: `tests/webhooks/scenario.py` (the webhook contract needs every catalog event
  type), `test_commands.py` (17 commands), `test_mcp_server.py` (tool surface), `test_ddl.py` and `test_generate.py` (new table), `test_catalog.py`
  (four `NOT_EVENTS` entries removed), `test_remote_client.py` (feed methods now work), `test_live_app.py` (feed refresh),
  `tests/services/test_feed_actions.py` and `test_feed_completion.py` (author-only edit and retract replaces WS-A decision A8).
- `PostgresUowFactory.__call__` takes `readonly` positionally or by keyword (ruling C4); the TUI client files were touched only in `remote.py` and
  `app.py` (feed methods and refresh).

## Escalations and decisions
Orchestrator rulings: B2 and B6 accepted; B3 changed into B15; reviewer fixes B16 (post ownership), B17 (agent source set by the server), B18
(keyword factory calls), B19 (scoped `get_proposal`). A direct-write mode and per-role tool permissions were not built (human gate, ADR-0005).

## Learnings
Appended: L-P0-I6B-1 to L-P0-I6B-7 (webhook scenario after catalog changes; rolled-back dry run; accept-or-fail wrapper; no permission claims in stored
commands and the API rule for agents; bounding free-form JSON; running the long suite in the background; factory call shape). Implementer proposals
declined: the empty-container output of `tl proposal show` (matches the spec; a later ticket may choose to hide them).

## Docs
Created: `docs/tickets/P0-I6/README-B.md`, `docs/runbooks/proposal-review-queue.md`, `dev/demos/P0-I6-B.sh` and `p0_i6_b_demo.py`. Updated: READMEs and
AGENTS of tl-core, tl-api, tl-cli, tl-mcp; README of tl-tui and tl-schema; `docs/runbooks/README.md` and `api-and-mcp-dev.md`;
`docs/reference/openapi.json` (generated).

## Follow-ups filed
- TUI review-queue screen (optional item of the scope) and `RemoteClient` proposal methods: `ClientInterface` has no proposal methods; add them with the screen.
- Agent identity record (display name, owner, enabled, per-agent budget) with the permission model; today an agent is its actor string (B8).
- A feed rate limit: posts have no budget.
- Per-role permissions for who may accept what, a direct-write mode, and record-level confidentiality: the permission model (human gate).
- `tl proposal show`: decide whether empty containers are hidden.
- The 3 s remote call timeout makes `test_a_live_server_answers_reads_commands_queries_and_errors` sensitive to a loaded machine; the P0-I8 hardening
  item that moves TUI calls to workers removes the cause.
