# Report — P1-I7 workstream B (record threads with dispatch)

Branch `p1/i7b` (base `p1/i7`, with `p1/i7` at e34ef79 merged in). Plan: [docs/tickets/P1-I7/README-B.md](../tickets/P1-I7/README-B.md). Fanout: [docs/tickets/P1-I7/FANOUT.md](../tickets/P1-I7/FANOUT.md) (D1 to D20, mainly D2, D9, D10, D12). Decision record: [ADR-0018](../adr/0018-record-threads-and-dispatch.md). Operations: [docs/runbooks/record-threads.md](../runbooks/record-threads.md).

## Outcome
Objective met: yes. A record can have a thread. People and agents post to it, and a person can run existing commands from it with a slash line, after a preview and with the access they already have.

- A thread is the stream `thread:<record id>` (type `core.Thread`, the record's scope). A message never bumps the record, never appears in the activity feed, and reaches webhooks only as `Thread.MessagePosted` and `Thread.Dispatched`. Visibility is the record's: a record the viewer cannot read has no readable thread, in the API, in `/events` and `/stream`.
- The gate is `threads.enabled`, a listed record type (`threads.enabled_types`), `threads.dispatch.enabled`, `threads.dispatch.roles` and `threads.agents.can_dispatch` (`propose` or `none`, risk `advanced`).
- Eleven verbs parse (`/assign /dispatch /raise /link /status /hold /release /due /notify /remind /summarise`). Seven have targets today: `/link`, `/status`, `/raise record`, `/dispatch <action>` (an `InvokeAction`), `/notify`, `/remind`, `/summarise`. `/assign`, `/due`, `/hold`, `/release` and `/raise rfi` answer `dispatch_unavailable` until a module registers a target.
- A preview plans the command line as the caller (nothing is written; each planned command shows the access it needs and whether the caller holds it, and a separate rolled-back dry run shows what the handler would refuse). The token is the SHA-256 of the record id and version, the line and the planned commands, so it excludes the viewer and the clock. A confirmation re-plans as the caller, compares the token in constant time, refuses a plan with problems, and runs everything in one unit of work with source `thread:<rid>`, correlation `dispatch:<message id>` and `dispatched_from` links.
- Agents never preview or confirm. `propose_dispatch` files a proposal with the plan's token (planned with nothing run); a person's acceptance re-plans as that person and fails the proposal if the plan changed or the person lacks access. Agents post messages directly (`post_thread_message`, in `AGENT_DIRECT_COMMANDS`) and read (`read_thread`).
- The command runner is WS-A's `command_runner()`: each command runs only if its actor holds the access the table declares, read from the actor's account. A person without an account holds nothing, on a dev ledger too.
- Entry points: API (`GET /records/{id}/thread`, `POST .../thread/preview`, `POST .../thread/dispatch`, the three message commands), MCP (`read_thread`, `post_thread_message`, `propose_dispatch`), CLI (`tl thread show|post|edit|retract|preview|dispatch|reminders`), TUI (the record view's Thread tab, key `T`, and the thread composer, key `c`).

## Tickets
| ID | Outcome | Review | Notes |
|---|---|---|---|
| S1 to S4 (supervisor) | merged into `p1/i7b` (aea611c, 27658b9 and the hardening commits) | orchestrator and the security pass | Schema, parser, planner, confirm, API, MCP, client plumbing, visibility filter, references of batch 2 |
| T10a `/link` and `/dispatch` | merged (031521d) | 1 (pass) | |
| T10b `/status` and `/raise record` | merged (452c9fc) | 1 (pass) | |
| T10c `/summarise` text | merged (d97ca4b) | 1 (pass) | |
| T10d `thread.reminder` job | merged (5a604c1) | review-only pass (pass) | Blocked by order on the first run (its test dispatched `/link`); L-P1-I7B-6 |
| T12a MCP `read_thread` and `post_thread_message` | merged (8342f0c) | 1 (pass) | 8 tests |
| T09a CLI `tl thread show|post|edit|retract` | merged (7293f2f) | 1 (pass) | 11 tests (the ticket said 10) |
| T09b CLI `tl thread preview|dispatch|reminders` | merged (b5f05e3) | the security pass | Blocked by order on the first run (its tests call T09a's commands); L-P1-I7B-9. 10 tests |
| T11b TUI thread composer | merged (eb6e838) | 1 (pass) | 3 + 13 tests |
| T11a TUI thread tab | merged (d11a2ea) | 1 (pass) | 6 + 7 tests |
| T12b catalog and webhook scenario | done in S1 | | |

No ticket was taken over or abandoned. Two tickets came back blocked by order and one provided test was extended by the supervisor after the merge.

## Mutation checks
Every provided test was checked against a mutated reference before dispatch. The first checks proved nothing: the script ran its command under dash, where `${PIPESTATUS[0]}` is a bad substitution, so every mutant looked killed (L-P1-I7B-7). The script now runs under bash and first runs the command unmutated. After the fix, survivors were closed with a new test each: the MCP message id against the stream id, the CLI dispatch outcome line, the CLI "not permitted" preview state, the summary limit boundary, a plain message that reads like a `/remind`, a client with no threads in the tab, and a slash line with leading spaces in the composer. Two mutants remain and are equivalent (`.strip()` in `/raise`, and the `retracted` guard of the reminder job, since a dispatch message cannot be retracted).

## Security review
@@SECURITY@@

## Gates
Run on the final tree of `p1/i7b` under `/home/user/locks/suite.lock`.

@@GATES@@

## Showcase
`just demo P1-I7B` is the thread part of the increment demo (FANOUT D20 item 4; the whole `just demo P1-I7` is WS-A's). It runs once on SQLite and once on Postgres with the real CLI and two signed-in people, and ends each clause with a PASS line:

1. Threads are off until an admin switches them on; a message is posted and read back.
2. `/link #KEY as requires` is previewed (nothing written, the plan names the access) and confirmed with the preview's token; the link exists and the thread shows `-> link: ...`.
3. `/raise record Clash at grid C4 --yes` previews, prints and runs: a new record, linked from the thread's record (`dispatched_from`), in one transaction.
4. `/summarise` posts a summary that says the system counted it, no model.
5. A different line, or a made-up token, is refused: "the plan is not the one you previewed".
6. A message that starts with `/` is only text.
7. With `threads.dispatch.roles` set to `admin`, a plain user is refused and the admin may dispatch.
8. An agent proposes a dispatch; nothing changes until a person accepts it with `tl proposal accept`; the commands run as that person; with `threads.agents.can_dispatch` set to `none` the proposal is refused.

Item 5 of D20 (`/dispatch send_to_nde`) needs the webhook action of WS-A and is in `just demo P1-I7`.

## Learnings
L-P1-I7B-1 to L-P1-I7B-9 in `docs/memory/LEARNINGS.md`: helper names, the dry run is not a savepoint, the token hashes the plan, five places for a client call, verify in a second worktree, two Depends misses (T10d, T09b), the mutation-script bug, and the account every actor needs once the runner enforces access.

## Open risks and known limits
- Dispatched workflow transitions cannot satisfy a `roles` guard until the workflow layer derives roles from the principal (P1-SEC1); the preview shows the failed guard (ADR-0018 item 12).
- The P1-I5 read filter plugs in at `visibility.readable_record` and `SubscriptionFilter.visible` when the trunk merge brings it. Until then thread events follow the scope rules of the existing filter; the test that they stay hidden once it is plugged is in `packages/tl-api/tests/test_api_threads.py`.
- `/assign`, `/due`, `/hold`, `/release` and `/raise rfi` are parsed and answer `dispatch_unavailable`.
- The pinned count of settings keys (16) and the settings snapshot change with every new key; whoever merges next updates them.
