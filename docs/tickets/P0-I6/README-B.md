# Increment plan: P0-I6 workstream B, MCP write tools and the proposal review queue

Status: in-progress
Supervisor session: 2026-10-10
Brief sections: §11.3, §18.12, §21.3, §21.1 (feed over the API)
Branch: `p0/i6b` (worktree `/home/user/wt/p0-i6b`), based on `p0/i6`; fanout plan `docs/tickets/P0-I6/FANOUT.md`

## Objective
An MCP agent can read the ledger and post to a project feed, and it can *propose* record changes. A proposal is checked with the rules
that apply when it is accepted, lands in a review queue, and does nothing until a person accepts it from the CLI or the API; the change is
then made by that person, tagged `source=mcp:<agent>` with the proposal as its cause. Each agent has a daily proposal budget. No tool can be
switched to a direct-write mode: that is the permission model, a human gate (ADR-0005, FANOUT D4). The feed that WS-A built is also served
over the API and `ApiClient`.

## Demo
```
just demo P0-I6-B
```
`dev/demos/P0-I6-B.sh` (driver `dev/demos/p0_i6_b_demo.py`): a scratch ledger and API; an MCP agent (`agent:triage`) in process calls
`create_record` and `post_feed`; the record does not exist yet, the post is in the feed labelled `agent:triage`; `tl proposal ls|show|accept`
makes the record, whose first event has actor `user:alice` and source `mcp:triage`; a third proposal with the budget set to 2 is refused with
the budget message; `GET /proposals` and the API accept/reject routes are shown; asking for tool mode `write` prints the human-gate message.

## Published for other workstreams and increments
| Surface | Where | Notes |
|---|---|---|
| Feed reads | `GET /feed`, `/feed/complete`, `/feed/posts/{id}` | OpenAPI committed; the four writes are the generated `POST /commands/PostToFeed|EditPost|RetractPost|ReactToPost` |
| `ApiClient` feed methods | `tl_api.client.feed.FeedApi` | `feed_page`, `feed_post`, `feed_edit`, `feed_retract`, `feed_react`, `feed_complete`: same names, kinds and defaults as `ClientInterface` |
| Proposals service | `tl_core.services.proposals` | `propose`, `submit`, `precheck`, `accept_proposal`, `accept_or_fail`, `reject_proposal`, `fail_proposal`, `list_proposals`, `get_proposal`, `proposals_today`, `daily_budget`, `source_for` |
| Proposal routes | `GET /proposals`, `GET /proposals/{id}`, `POST /proposals/{id}/accept`, `POST /proposals/{id}/reject` | no propose route: agents propose through MCP |
| `ApiClient` proposal methods | `tl_api.client.proposals.ProposalsApi` | `list_proposals`, `get_proposal`, `accept_proposal`, `reject_proposal` (not on `ClientInterface`, see B12) |
| MCP tools | `tl_mcp.write_tools` | `create_record`, `update_psets`, `link_records`, `transition_workflow` (propose) and `post_feed` (direct) |
| CLI | `tl proposal ls\|show\|accept\|reject` | |
| Schema | `schema/core/proposals.yaml` | `Proposal.Created\|Accepted\|Rejected\|Failed` catalog payloads, table `cur_proposals` |
| Budget knob | `TL_AGENT_DAILY_PROPOSALS` | default 500 (`AGENT_DAILY_PROPOSALS`); 0 refuses everything |

For workstream C (the simulator): an actor proposes by calling the MCP tools above (in process with `build_server`, or over stdio); it reads the
queue with `ApiClient.list_proposals` and a human step (or the sim's "reviewer" actor, acting as a `user:` token) accepts with
`ApiClient.accept_proposal`. An `agent:` token is refused with 403 `proposal_decider`. The budget day is the UTC day of the proposal event's
`effective_at`, so a simulated day (D5) counts against that day; pass `now=` to `proposals.submit` from code that knows the simulated time.

## Decisions
| # | Decision |
|---|---|
| B1 | **Propose validates by running the command to the end in a unit of work that is rolled back** (`proposals.precheck`), then records the proposal in a fresh one (`proposals.submit`). The handlers interleave reads and writes, so there is no honest "non-writing pre-check"; a rolled-back run reuses the handler's own rules, writes no event, publishes nothing, and gives an allocated number back. Under Postgres a rolled-back run still burns sequence values (`seq` gaps, which consumers already tolerate, L-P0-I4-A2). A transition refused only by a *role* guard passes, because an agent has no roles; every other guard must pass at proposal time. |
| B2 | **`accept_proposal(uow)` raises the command's refusal; `accept_or_fail(factory)` records `Proposal.Failed`.** The frozen contract says a failure is recorded "in a fresh unit of work", which a function given only an entered `uow` cannot open. The signatures of `types.py` are unchanged; the CLI and the API call `accept_or_fail`. A failure that is transient (`RetryableTransactionError`) is not recorded: the proposal stays pending and the caller retries. A race between two people accepting ends in `ProposalNotPendingError` for the loser. |
| B3 | **Only `user:<id>` decides** (`ProposalDeciderError`, HTTP 403 `proposal_decider`). This is what "a person accepts" means, not a permission model: it grants no one anything. |
| B4 | **A proposal carries no workflow roles.** `TransitionWorkflow.actor_roles` is trusted input, so an agent claiming `manager` in a proposal would have a person's click run it with that role. `propose` refuses a non-empty list; the accepting person passes their own (`tl proposal accept --role`, the accept body's `roles`). |
| B5 | **Budget:** `AGENT_DAILY_PROPOSALS` proposals created per actor per UTC day (of `effective_at`), counted from `cur_proposals`; accepted, rejected and failed proposals still count. Environment override `TL_AGENT_DAILY_PROPOSALS` (about:config arrives in P0-I8). The cheap checks and the budget run before the dry run, so an agent over budget costs nothing. Under Postgres two simultaneous proposals may overshoot by one (the count is a read). Posts have no budget (follow-up: a feed rate limit). |
| B6 | **`cur_proposals` is a projection** (`ProposalProjector`, a default projector); `Proposal.*` events are transparent to feed cards, so accepting 14 proposals still reads "alice created 14 records". |
| B7 | **Source tagging:** everything done for an agent carries `source=mcp:<id>` (`@` in an id becomes `_`). Proposal events are authored by the agent with that source; the accepted command's events are authored by the person with that source and `causation_id` = the `Proposal.Created` event; `correlation_id` is the proposal id throughout. The decision event's source is `cli` or `api`. |
| B8 | **Agent identity is minimal:** an agent *is* its actor string `agent:<id>` (ADR-0005 dev tokens, `--actor`). No identity record exists; the budget, the source tag and the feed label key on the string. A record (display name, owner, enabled, budget override) belongs with the permission model and is listed as a follow-up. |
| B9 | **Tool modes:** `propose` is the only mode. `build_server(tool_modes=...)` and `python -m tl_mcp --tool-mode T=MODE` raise `ToolModeError` with `HUMAN_GATE_MESSAGE` for `write`, and reject unknown modes, unknown tools and `post_feed` (it has no mode: it always writes directly, labelled). |
| B10 | **`expected_version` defaults to the version at proposal time** for `update_psets` and `transition_workflow`. If the record changes before a person accepts, the proposal fails (stale), never applies blindly. |
| B11 | **A failed accept is HTTP 200** (the decision was recorded) whose body has `status: failed` and the error in `reason`; the CLI prints `failed <id>` and exits 1. |
| B12 | **`ClientInterface` is not extended** with proposal methods: P0-I4 WS-D owns the TUI client files and is mid-flight. `ApiClient` has them as extras (like files and events). The TUI review-queue screen and `RemoteClient` feed and proposal methods are follow-ups for the P0-I4/P0-I6 integration. |
| B13 | **Feed over the API:** the four feed writes join the generated command table (the token's actor is recorded; a body carrying `actor` is a 422); reads are three GET routes over the WS-A services. Feed errors were already in the error table; five proposal rows were added (`proposal_not_found` 404, `proposal_not_pending` 409, `invalid_proposal` 422, `budget_exceeded` 429, `proposal_decider` 403). |
| B14 | **Bounds:** every string input of a write tool has a `maxLength` (scope and ids 128, title 500, description and post body 10 000, summary 300, notes and reasons 1 000); free-form JSON (`psets`, `values`) is bounded as text (64 000 characters), and the numbering map to 20 entries. A schema test fails if any string in any tool schema lacks a limit. |
| B15 | **Orchestrator ruling: an `agent:` token cannot change a record over REST** (FANOUT D4 says agents propose). Every `POST /commands/*` except `PostToFeed`, `EditPost`, `RetractPost` and `ReactToPost`, and the file writes (`/uploads`, `/uploads/{id}/content`, `/uploads/{id}/complete`, `/files/attach`), answer 403 `agent_must_propose` ("agents propose record changes through MCP (P0-I6 D4); a human accepts them") when the token's actor starts with `agent:`. The rule is `guard(..., changes_records=True)` beside `authorize` (`tl_api.auth.refuse_agent_writes`); the code is in `HTTP_ERRORS`. It is a fixed invariant of the brief, not a permission model: it grants no one anything, and per-role permissions stay a human gate (ADR-0005). Agents still read and post. Workstream C's deterministic actors use `user:sim-<role>` tokens in `project:sim-*` scopes. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S20 | Feed routes, command-table entries, `FeedApi`, round-trip tests | error mapping and the client contract; turns the known-red round-trip test green | orchestrator | done |
| S21 | `schema/core/proposals.yaml`, generated output | schema (delegated approval) | orchestrator | done |
| S26 | B15: agents cannot change records over REST (`guard(changes_records=True)`, test over every command route) | enforces FANOUT D4 at the API | orchestrator | done |
| S22 | Proposals service, `ProposalProjector`, review-queue routes, error rows | accept-or-fail semantics, budget, source tagging | orchestrator | done |
| S23 | MCP write tools, tool modes, bounds | propose-only enforcement, the hook, the human-gate message | orchestrator | done |
| S24 | Stubs and provided tests for T20, T21 | scaffolds | | done |
| S25 | Demo, runbook, READMEs, report | closing work | | pending |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I6-T20 | `tl proposal ls\|show\|accept\|reject` (14 provided tests) | haiku | S22 | ready | |
| P0-I6-T21 | ApiClient review-queue methods (9 provided tests) | haiku | S22 | ready | |

Haiku-ability (`01-tiers.md` §6) for both: (1) four to five files to read; (2) the service, the routes, the stubs and the sibling modules are
in the repository; (3) each ships a provided test (14 and 9) verified against a scratch reference with `ruff`, `pyright` and the OpenAPI
check; (4) diffs of 100 to 130 lines plus the copied test; (5) none is in the Sonnet-authored table (a CLI group and a client mixin, each a
one-call wrapper; who may decide and what accepting runs are in the service); (6) no schema, migration, dependency or public-interface change
(the wiring in `main.py` and `client/__init__.py` is committed); (7) a reviewer verifies from the diff and the commands. Independence
(L-P0-I6A-5): T20's test calls `proposals.submit` and the CLI; T21's calls `proposals.submit` and the routes; neither calls the other's code.

## Order of work
1. Round 1 (done): feed over the API (S20), schema (S21), service and routes (S22), MCP tools (S23), stubs and provided tests (S24), tickets T20 and T21; DISPATCH.
2. Round 2: merge T20 and T21 after review; the demo, the runbook, READMEs and AGENTS, the learnings, the gates, the report (S25).

## Risks and escalation triggers
- **Propose-only has two enforcement points**: the MCP tools (no write tool exists) and, by B15, the REST command and file routes for `agent:` tokens. Which *people* may write what is still the permission model (human gate); `authorize` allows everything.
- The dry run holds the write lock for the length of a handler under SQLite; fine for a dev server, a point to measure in the P0-I8 performance pass.
- `Proposal.Created` carries the whole command; the 64 000-character bound on free-form JSON keeps an event small enough, but a high-volume agent grows the ledger by one event per proposal (budget 500 per day).
- Escalate for: any change to `Command`, `Event`, `Ledger`, `UnitOfWork`, `Projector` or `Bus` (03 §7), a decision on who may write directly, or on agent identity records.

## Blocked / Decision
Orchestrator rulings (2026-10-10): B2 accepted. B6 accepted, with a cards test (`packages/tl-core/tests/test_feed_cards.py`, the four `Proposal.*` types are ignored by the card rules). B3 changed into B15 above.
