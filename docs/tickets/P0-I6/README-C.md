# Increment plan: P0-I6 workstream C, simulator v0

Status: in-progress
Supervisor session: 2026-10-10
Brief sections: §29.5, §29.1, §5.1, §18.1 to §18.3
Branch: `p0/i6c` (worktree `/home/user/wt/p0-i6c`, base `p0/i6` at 037f4da), fanout plan `docs/tickets/P0-I6/FANOUT.md`

## Objective
A seeded, deterministic project team plays working days against a running suite and a ground-truth log says what it meant to do.
`sim_create`, `sim_advance`, `sim_inject`, `sim_status` and `sim_assert` run as a Python API and as `tl sim`; the actors (document
controller, planner, crew) act on generic records, links, workflow transitions and feed posts only through `ApiClient` and MCP; the
events they write carry simulated time (`effective_at`); `sim_assert` reads the suite back through the API and names every difference.

## Demo
```
just demo P0-I6-C
```
Starts `python -m tl_api` on a temporary ledger, creates a run, advances one day, shows the crew's posts and records through the API,
runs `sim_assert` (green), re-runs the same seed on a fresh ledger and compares the ground-truth digest, then tampers and shows
`sim_assert` fail. `just demo P0-I6` composes workstreams A, B and C after the merge.

## Decisions
| # | Decision |
|---|---|
| C1 | The simulator never opens the ledger. `ApiClient` carries every read and write; `tests/test_contract_and_boundary.py` reads the imports of `src/tl_sim` and fails on a ledger, unit of work, projection, adapter, SQL or `handle_*` import (brief 29.1). |
| C2 | D5 as built: `tl_core.util.effective_time(dt)` is a context variable; both ledger adapters use it when `NewEvent.effective_at` is None. `event_hash` covers `recorded_at`, not `effective_at`, so the hash, `Command` and `Event` of 03 §7 are unchanged. The API reads `X-TL-Effective-At` on `POST /commands/*` only, and only for `project:sim-*` scopes (HTTP 400 `effective_time_forbidden` otherwise, `invalid_effective_time` for a value without an offset). Uploads and MCP do not read it. |
| C3 | A simulation scope `project:sim-<run>` cannot be numbered (the `{project}` segment takes letters and digits only, and the scope has a dash), so `HttpSimClient` assigns the keys: `SIM<RUN>-REC-0001`. They fit the registered pattern, so `#SIMR3FA91C-REC-0007` in a post resolves to the record and suggests a `references` link. The counters live in the run state. Loosening the `{project}` rule instead would change numbering allocation, which is a human gate. |
| C4 | Ground truth never holds a server-made id. A record is its key, a link `from relation to`, a post `post:<actor>:<time>:<n>`. Two runs of one seed on two ledgers therefore write byte-identical logs, and the digest in `sim_status` compares them. |
| C5 | Each actor works in its own time slot (06:00 seed, then 07:00, 07:30, 08:00, then injections), each write moves the clock one minute, and a day is a working day on the scenario calendar (Monday to Friday by default). |
| C6 | `sim_assert` checks the latest intent per field against the `cur_*` view the API serves, then three negatives: no record the log does not name, every event in the scope has `source` `sim:<run>` (or an MCP proposal), and every simulator event has `effective_at` on a day that was played. |
| C7 | A step that dies leaves `in_progress` in the run state, because the writes already made are not in the log. The run then refuses to continue. |
| C9 | Orchestrator ruling from WS-B decision B15 (2026-10-10): the API refuses record-changing commands from any `agent:*` token with 403 `agent_must_propose` (FANOUT D4). The deterministic role actors stand in for people, so they act as `user:sim-<role>` (`user:sim-document_controller`, `-planner`, `-crew`, and `user:sim-orchestrator` for the seed), each with its own dev token and `source=sim:<run_id>`. One agent identity, `agent:sim-assistant`, exists for proposals: once WS-B is merged it calls `SimClient.propose` over MCP and a `user:sim-*` actor accepts the proposal through the API. `sim_create` already provisions its token. The `identity` comment in `types.py` (`agent:sim-<name>`) is documentation in the frozen text and is left as is; the identities in the ledger are the ones in this row. `sim_assert` now also fails any event whose actor is not `user:sim-*` or `agent:sim-*`. |
| C8 | `propose` is behind the `McpCaller` Protocol. Until workstream B is on the base it raises `ProposeUnavailableError`; the planner has no proposals in v0 and they are added when the proposals service is wired. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S40 | `effective_time`, adapter use, `X-TL-Effective-At`, parity tests | touches the ledger adapters and the API contract (D5) | orchestrator | done |
| S41 | `tl-sim` package: types, rng, clock, ground truth, scenario models, run state, `HttpSimClient`, reader, assertions, orchestrator loop, injections, `FakeWorld`, actor base and `Recorder` | orchestrator loop and determinism, ground-truth assertion | orchestrator | done |
| S42 | Stubs and provided tests for T40 to T43, reference implementations kept in the scratchpad | scaffolds | | done |
| S43 | Roles act as `user:sim-<role>`, `agent:sim-assistant` provisioned, actor check in `sim_assert` (C9) | identity of the simulator | orchestrator | done |
| S44 | After batch 1: identities and plural fixes, Rev Z rule | reviewer rulings | | done |
| S45 | End-to-end tests: the real actors against the real API app | determinism and the ground-truth assertion in practice | orchestrator | done (posts use a stand-in until WS-B is merged) |
| S46 | `tl sim`, `tl_sim.mcp_server`, `just seed` (`dev/seed/seed.sh`) | wiring | | done |
| S47 | Demo `P0-I6-C`, merge of WS-B, `P0-I6` demo and report | closing work | | pending |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I6-T40 | Document controller actor (13 provided tests) | haiku | S41 | merged | pass, 1 round. Reviewer question answered: Rev Z is the last revision and is never revised (documented in the docstring and `DocumentControllerParams`, with a test) |
| P0-I6-T41 | Planner actor (12 provided tests) | haiku | S41 | merged | pass, 1 round |
| P0-I6-T42 | Crew actor (12 provided tests) | haiku | S41 | merged | pass, 1 round. Reviewer ruling: singular and plural in posts (`1 valve`); applied to the three actors in S44 |
| P0-I6-T43 | Scenario and template loader (25 provided tests) | haiku | S41 | merged | pass, 1 round |
| P0-I6-T44 | `tl sim` CLI group | supervisor | S41, T43 | taken by supervisor | not dispatched: the reference (`tl_sim/cli.py`, 18 tests with the five operations faked) was written to verify the ticket and is two hundred lines of formatting; usage limits (L-P0-I5-O4) |
| P0-I6-T45 | Simulation MCP server, five tools | supervisor | S41 | taken by supervisor | not dispatched, same reason; `tl_sim/mcp_server.py`, 11 tests |

## Order of work
1. Round 1 (this round): S40 to S42, DISPATCH T40 to T43.
2. Round 2: merge batch 1, then change `IDENTITY` in the three provided actor tests (`provided/c-test_actor_*.py.txt`, T40 to T42 texts) and in the merged `test_actor_*.py` to `user:sim-<role>` (C9; batch 1 was dispatched before the ruling, and `BaseActor.identity` already answers `user:sim-<name>`, so the three identity tests fail until then); real-actor end-to-end tests against the API (reference check); T44 and T45 with stubs and provided tests; DISPATCH.
3. Round 3: merge batch 2; `just seed`, demo `P0-I6-C`; docs; gates. Then, when told workstream B is on `p0/i6`: merge it, wire `post` (`feed_post`), proposals (`McpCaller`) and the review-queue read, then `dev/demos/P0-I6.sh` and `docs/reports/P0-I6.md`.

## Review of S40 to S43 (fresh reviewer, changes requested; fixed in S48)
| # | Finding | Fix |
|---|---|---|
| 1 | `X-TL-Effective-At` at the ends of the calendar gave 500 (`OverflowError`) | caught and 400 `invalid_effective_time`; accepted years 1970 to 2100, checked in UTC |
| 2 | `sim_assert` passed on an empty log | fails closed: `empty_ground_truth`, `nothing_checked` |
| 3 | The actor check was a prefix test | each record, pset, link, transition, post and proposal intent is compared with the actor of the ledger event that fulfilled it (`actor_mismatch`); readers return `stream_id` and `payload` |
| 4 | The import-boundary test missed `from x import y` and aliases | dotted-name check, alias attribute chains, `importlib`/`__import__`, negative fixtures |
| 5 | `RunState.created_at` read the wall clock; a docstring named the wrong test file | the caller supplies it (the scenario start at 00:00 UTC); docstring fixed |
| 6 | `HttpReader.proposals()` returns `[]` until WS-B merges | accepted (fails closed: a logged proposal is then reported missing) |

## Review of T44 and T45 (fresh reviewer, changes requested; fixed in S49)
| # | Finding | Fix |
|---|---|---|
| 1 | HIGH: `sim_create` over MCP read any YAML path, and errors echoed paths and parser text | MCP accepts a bundled name matching `[a-z0-9._-]{1,64}` only (`load_bundled_scenario`, real path inside the scenarios directory, symlinks followed); `ScenarioError.public` and path-free `RunError` text; tests for absolute paths, `../`, `.yaml`, symlinks |
| 2 | MEDIUM: injection arguments unbounded (`count` of 10**9) | `InjectSpec`: count at most 20, strings 2000 characters, 16 keys, scalars only; 100 queued per run (`RunError`) |
| 3 | MEDIUM: `seed.sh` left `tl serve` running (`$!` was the wrapper) | `setsid` and a group kill, then wait until `/health` stops answering; same in the demo. Checked on the failure path (the run dies at the first post, the server is gone) |
| 4 | LOW: no authorise hook in the sim MCP tools | `sim.create|advance|inject|status|assert` hook first, deny-all test |

## Risks and escalation triggers
- The feed post and feed read need workstream B (`ApiClient.feed_post`, `feed_page`, the `PostToFeed` route). Until it is merged the real-API tests cover every write except `post`, and `HttpReader.posts` is only exercised on `FakeWorld`.
- A change to `Command`, `Event`, `Ledger` or `event_hash` would be a stop condition. D5 needed none.
- The real workflow guard is stricter than the fake in places not yet met (conformance guard on `approve`). The end-to-end test with the real actors shows it.

## Blocked / Decision
(none)
