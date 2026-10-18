# Increment plan — P1-I7 workstream B: record threads with dispatch

Status: in-progress
Supervisor session: 2026-10-18
Brief sections: §21.5 (threads with dispatch), §10.6 sketch 13, §8 and §18.12 (access, agents propose), §7.1 (links)
Branch: `p1/i7b` (from `p1/i7`; ticket branches are siblings, `p1/i7b-t<nn>-<slug>`)
Fanout: `docs/tickets/P1-I7/FANOUT.md` (decisions D1 to D20; this workstream owns D9, D10 and the thread rows of D12)
ADR: `docs/adr/0018-record-threads-and-dispatch.md` (proposed)

## Objective
A record can have a message thread. People discuss it and dispatch work from it with slash commands
(`/assign /dispatch /raise /link /status /hold /release /due /notify /remind /summarise`). A command line is parsed
(pure), previewed with the caller's own access and confirmed with a token; the confirmation runs exactly the
previewed commands in one transaction, ledgered with the server-set source `thread:<record id>`, and posts the
result as a card. Agents read and post, and only propose dispatches. The thread is as visible as its record.

## Demo
`just demo P1-I7` is WS-A's script; its thread part (FANOUT D20 item 4) runs these steps, on SQLite and Postgres:

1. `tl thread post <KEY> "Flanges short for W019 @lchen"` then `tl thread show <KEY>`.
2. `tl thread preview <KEY> "/link <OTHER>"`, then `/raise record #<OTHER> Clash at grid C4`: the preview lists
   `CreateRecord` and `AddLink`, with the token; `tl thread dispatch <KEY> "<same line>" --token <token>` runs it.
   A new record exists, linked `dispatched_from` the thread's record.
3. `/summarise` posts the deterministic summary; `/remind +1h` queues a job that `tl thread reminders --once` runs.
4. An agent's `propose_dispatch` (MCP) is accepted by a person with `tl proposal accept`.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `schema/core/threads.yaml`, five settings, events, projector, message commands, reads, visibility | schema gate; permission-adjacent (D12) | orchestrator (SCHEMA_APPROVALS) | built, commit aea611c |
| S2 | parser, resolve, targets frame, planner and token, engine, `DispatchFromThread` | security: access through `holds`, token, rolled-back dry run | fresh-context security review (D18) | built, commit aea611c |
| S3 | `propose_dispatch` accept check, `AGENT_ACTIONS`, `MCP_ACTIONS`, `PROPOSABLE_TOOLS`, API command table, routes, client plumbing, MCP propose tool | permission code (D12) | fresh-context security review | built, commit aea611c |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T10a | Targets `/link` and `/dispatch` | haiku | S1, S2 | merged | passed review |
| T10b | Targets `/status` and `/raise record` | haiku | S1, S2 | merged | passed review |
| T10c | Deterministic `/summarise` text | haiku | S1, S2 | merged | passed review |
| T10d | `thread.reminder` job kind | haiku | S1, S2, T10a | merged | blocked by order on the first run (L-P1-I7B-6); passed after T10a merged |
| T12a | MCP `read_thread` and `post_thread_message` bodies | haiku | S3 | ready (batch 2) | |
| T09a | CLI `tl thread show / post / edit / retract` | haiku | S1, S3 | ready (batch 2) | |
| T09b | CLI `tl thread preview / dispatch / reminders` | haiku | S2, S3, T10a to T10d | ready (batch 2) | |
| T11a | TUI thread tab: messages, participants, result cards | haiku | S3, T11b (`action_compose` opens `ThreadComposer`) | ready (batch 3) | |
| T11b | TUI composer: `/` verbs, `@`, `#` completion; preview and confirm | haiku | S3 | ready (batch 2) | |
| T12b | Webhook scenario and catalog for `Thread.*` | supervisor | S1 | done in S1 (pins, scenario) | merged in aea611c |

The plan's T09 (stream, events, settings) and T10 (parser) are supervisor pieces S1 and S2 (FANOUT D15); the Haiku
tickets above are the rest of T09 to T12. T11 is split by screen (L-P1-I3-6).

## Order of work
1. S1 to S3 (done), then ticket batch 1 (T10a to T10d), batch 2 (T12a, T09a, T09b, T11b), batch 3 (T11a).
2. Review each PR with a fresh reviewer; merge on a pass and green `just check && just test` for the package.
3. When WS-A T01 to T03 are on `p1/i7`: merge `p1/i7` into `p1/i7b`, swap `tl_api/thread_runner.py` for
   `command_runner()`, wire `InvokeAction` access (`holds`) for `/dispatch`, add the walking test of reserved
   identifiers (D2), then the fresh-context security review and the merge into `p1/i7`.
4. Report `docs/reports/P1-I7-B.md` with a Showcase section.

## Risks and escalation triggers
- `/dispatch` needs WS-A's `InvokeAction`; until it is on `p1/i7` the planner answers `dispatch_unavailable`.
  `InvokeAction`'s handler checks the action's `access` with `holds`, which `CommandRunner.run(uow, command)` does not
  carry: raise with the orchestrator at the merge if the runner contract cannot pass it (a contract change).
- Dispatched workflow transitions cannot satisfy a `roles` guard until P1-SEC1 (ADR-0018 item 12).
- Thread events reach the events API, the SSE stream and webhook subscribers by scope, not by record: P1-I5's
  confidentiality filters must cover them at the trunk merge (FANOUT D17, step 4).
- A frozen contract needing a change: write it under *Blocked* and escalate.

## Blocked / Decision
None so far. Deviations from FANOUT, all recorded in ADR-0018: event payload classes live in `threads.yaml`
(the feed and proposals precedent) instead of `events.yaml`; `/link` keeps the default link source (item 7).
