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
The fresh-context review (of dd92d42 plus 1636181) came back changes-requested: no Critical or High, 3 Medium, 6 Low. Every finding is fixed with a test (14f7f06, ec2c23f, 5b2072e); the focused re-check of M1 and M2 is the orchestrator's.

| Finding | Fix (commit) |
|---|---|
| M1 a replayed preview token re-ran a side-effecting plan (a dispatch does not bump the record version) | The token also hashes the number of dispatches of the thread, so the dispatch's own message spends it; replay is `dispatch_stale` on both adapters (14f7f06). Counting dispatches rather than the stream version keeps previews and proposals valid across ordinary chat |
| M2 the accept path forced `holds("user")` true; effects had no account check | `holds` passes through and is required; `holds("user")` false leaves the proposal pending; the engine calls `require_access` before an effect; an access refusal never fails a proposal; the CLI uses `account_holds` for a dispatch proposal (14f7f06) |
| M3 CLI thread fixture dead on Postgres (the account had no password) | `thread_env` creates `dev` with the sign-in password; the three CLI thread files pass on both adapters (14f7f06) |
| L1 a bad `expires_at` was a 500 | Validated in `DispatchBody` (422) and bounded by the service (ec2c23f) |
| L2 the unknown-verb echo raised on a lone surrogate; the verb fold was not ASCII | ASCII-only lookup and echo (ec2c23f) |
| L3 forbidden fields were checked at the top level only | Recursive to depth 32 (ec2c23f) |
| L4 `read_thread` returned messages while threads were off; edit and retract were open | Empty page while off; post, edit and retract refused (ec2c23f) |
| L5 an agent's `/remind` with no mention could never be accepted | The plan names nobody; the job reads the setter from the message (5b2072e) |
| L6 reminder bounds | `threads.reminders.max_pending` per thread and per person; the job drops a reminder for a closed thread; the missing scheduler is stated here and in the runbook (5b2072e) |
| N1 (re-check) someone without the dispatch role could permanently fail an agent's proposal | A role, an account or a not-permitted refusal on acceptance is a `ProposalAccessError`: the proposal stays pending for an admin; tested on both adapters (this commit). The confirmation also requires an account for `/notify`, which plans no command |
| Question: why `by_module` on the `dispatched_from` link? | To set the reserved link source, not to bypass anything; it did skip the generic-command allow-list of the new record. Now `system_source="thread_dispatch"` (14f7f06) |
| Embedded TUI `thread_post` | `thread_post`, `thread_edit`, `thread_retract` require the signed-in person as actor (ec2c23f) |
| L7 thread data reachable through proposals and key resolution outside `readable_record` | Noted on the orchestrator's P1-I5 merge checklist; no action here |

Also found by WS-B itself after the merge, before the review: the proposal accept route and `tl proposal accept` passed no runner, so no proposed dispatch could be accepted (1636181, with an API and a CLI test).

There is no scheduler in the server for the `thread.reminder` job. Something must run `tl thread reminders` (or the P1-I7 job runner); until it does, a reminder is queued and not posted. The runbook says so.

## Gates
Run on the final tree of `p1/i7b` under `/home/user/locks/suite.lock`.

| Gate | Result |
|---|---|
| `just check` (ruff, format, pyright strict, generated files up to date, openapi, licences) | pass at the final commit (7e636ac plus this report) |
| Scoped parity, SQLite and Postgres: `tests/threads`, the API thread, walk and proposal tests, the MCP thread tools, propose-dispatch and walk tests, the three CLI thread files, the embedded TUI thread tests | 301 passed, 1 skipped at 31c50a4 (the skip is the CLI account-less-accept test on Postgres, where the test wrapper signs any named actor in; core and API cover it); 287 passed, 1 skipped at 5b2072e on a clean checkout under the suite lock; after N1 the thread, proposal and MCP files pass on both adapters (56 passed in the last targeted run) |
| Full suites on a clean checkout of 5b2072e, under the lock | tl-core, tl-adapters, tl-lake, tl-schema: 1963 passed. tl-api: 813 passed, 2 failed (stale pinned settings counts in `test_client_settings`, fixed in 4a71fb4). `tests/`: 2260 passed, 3 failed: one was the webhook parity test expecting the undelivered thread edit and retract events (fixed in 6efa658); two are WS-A's `test_int_actions` job-executor cases, red until WS-A's ticket T02a (the `job` executor stub) lands |
| tl-cli, tl-sim, tl-mcp at 5b2072e | 1311 passed, 3 failed, 268 errors. The errors are the `/tmp` disk filling up during the run (ENOSPC, 18 GB of old pytest directories, cleaned); the 3 failures were pinned lists in MCP tests (settings count, the tool set, the proposing tools), fixed in 7e636ac and re-run: 34 passed |
| Full re-run of tests/, tl-api, tl-cli/tl-sim/tl-mcp, tl-modules, tl-tui and the demo at 7e636ac | queued under the lock behind other supervisors' runs; results are appended to this section by a follow-up commit if they arrive before the merge, otherwise the integrated `p1/i7` gate covers them (orchestrator ruling) |
| `just demo P1-I7B` | SQLite: all eight clauses pass (run in the build container during development); the run on both backends is part of the queued locked run |
| `just test-tui` (tl-tui) | the thread tab, composer, text and embedded tests pass (3 + 13 + 6 + 7 + 5), and the settings screen, remote, embedded and fake settings tests and snapshots pass with 17 keys; the whole `packages/tl-tui` suite is in the queued run |


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
