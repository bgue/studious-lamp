# Report — P0-I6 workstream C, simulator v0

Plan and decisions C1 to C10: `docs/tickets/P0-I6/README-C.md`. Branch `p0/i6c` (base `p0/i6`, merged again at 353db71). Runbook: `docs/runbooks/simulator.md`.
Part of the increment report `docs/reports/P0-I6.md`; the sibling workstream reports are `P0-I6-A.md` and `P0-I6-B.md`.

## Outcome
Objective met: yes. `sim_create`, `sim_advance`, `sim_inject`, `sim_status` and `sim_assert` run as a Python API (`tl_sim.api`), as `tl sim` and as an MCP server
(`tl_sim.mcp_server`). Three deterministic actors (document controller, planner, crew) act as `user:sim-*` identities on generic records, links, workflow
transitions and feed posts, only through `ApiClient`; one agent (`agent:sim-assistant`) files proposals over MCP and one person (`user:sim-approver`) decides them.
Events carry simulated time. One seed gives a byte-identical ground-truth log on two ledgers. `sim_assert` reads the suite back through the API, fails closed
and names every difference. Demo path verified on the final tree: `just demo P0-I6-C` and `just demo P0-I6` both ran clean; `just seed xs` on a fresh ledger ended
`ok: 530 checks` and left no server running.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I6-T40 document controller | merged | 1 | reviewer's Rev Z question ruled: Rev Z is the last revision and is never revised |
| P0-I6-T41 planner | merged | 1 | |
| P0-I6-T42 crew | merged | 1 | ruling: singular and plural in posts (applied to all three actors) |
| P0-I6-T43 scenario and template loader | merged | 1 | |
| P0-I6-T44 `tl sim` CLI | taken by supervisor | n/a | the reference written to verify the ticket was already the finished code; usage limits |
| P0-I6-T45 simulation MCP server | taken by supervisor | n/a | same reason |
Batch 1 returned first-pass on all four. T44 and T45 were reviewed by a fresh reviewer after the fact (changes requested, fixed in S49).

## Supervisor-tier pieces (REVIEW-SUPERVISOR-PIECES)
| Piece | Where | Review |
|---|---|---|
| Effective-time contextvar, both ledger adapters, API header | `tl_core/util.py`, `tl_adapters/{sqlite,postgres}/ledger.py`, `tl_api/effective.py`, `tl_api/commands.py` | fresh reviewer: changes requested, fixed in S48 (overflow and range, 500 to 400) |
| Orchestrator loop and determinism | `tl_sim/orchestrator.py`, `rng.py`, `clock.py`, `state.py`, `injections.py` | fresh reviewer: sound; `created_at` no longer reads the wall clock |
| Ground-truth assertion | `tl_sim/assertions.py`, `reader.py`, `groundtruth.py` | fresh reviewer: fail closed, per-event actor check, boundary test hardened (S48) |
| CLI and MCP server | `tl_sim/cli.py`, `mcp_server.py`, `scenario_loader.py` (bundled names) | fresh reviewer: file read through MCP (HIGH), injection caps, leaked server, authorise hook (S49) |
| Not separately reviewed | `client.py`, `connector.py`, `mcp_caller.py`, `testing.py`, the assistant and approver actors, the proposal assertions (S50), `dev/seed/seed.sh`, both demos | covered by the end-to-end tests and the demos |

## Gates (final tree, 3e406cb after the merge of p0/i6 at 353db71)
| Gate | Result |
|---|---|
| `just check` | clean (ruff, format, pyright, codegen drift, OpenAPI drift, licences) |
| `just test` | 3893 passed |
| `just test-tui` | 480 passed, 24 snapshots |
| `just test-parity` | 1645 passed (3057 deselected), SQLite and Postgres |
| `just demo P0-I6` | `P0-I6 demo ok` |
| `just demo P0-I6-C` | `P0-I6-C demo ok` |
| `packages/tl-sim` | 256 tests, of which 8 end-to-end against the real API, MCP server and feed |

## Deviations from plan
- Keys are assigned by the client (`SIM<RUN>-REC-0001`): a `project:sim-<run>` scope cannot be auto-numbered, and loosening the rule is a human gate (C3, L-P0-I6C-1).
- B15 (orchestrator ruling): role actors are `user:sim-<role>`; the only agent is `agent:sim-assistant` (C9). The assistant and approver exist but are off in the seed scenarios.
- MCP calls and the accept route do not read `X-TL-Effective-At`, so a proposal and its decision carry real time; `sim_assert` time-checks only the simulator's own `sim:<run>` events.
- T44 and T45 were not dispatched (usage limits).
- `tl_sim.api` does not wrap the lake or `lake_query`; the MCP server of the suite has them and the simulator does not use them.

## Escalations and decisions
README-C decisions C1 to C10. No escalation; no change to `Command`, `Event`, `Ledger` or `event_hash` (the hash covers `recorded_at`, not `effective_at`).
Rulings received: B15 (agents propose, people accept), Rev Z, plural forms, the review fixes for S40 to S43 and T44/T45.

## Learnings
L-P0-I6C-1 to L-P0-I6C-11. Implementer proposals: the isort note for T43 and the Bash-tool traps (kept as L-P0-I6C-8); the rest were tool noise.

## Docs
`packages/tl-sim/README.md` and `AGENTS.md` (new); `docs/runbooks/simulator.md` (new); `packages/tl-core`, `tl-api`, `tl-cli` READMEs (updated); `docs/tickets/P0-I6/README-C.md`;
`dev/seed/` scenarios, templates and `seed.sh`; `dev/demos/P0-I6-C.sh`, `P0-I6.sh`, `p0_i6_demo.py`.

## Dependencies
Declared by `tl-sim`: pyyaml (MIT), typer (MIT), mcp (MIT), httpx2 (BSD-3-Clause), tl-mcp and tl-api (workspace). All were already in the lockfile closure; `just check` runs the licence gate.

## Follow-ups
- A permission model decides which people may accept which proposals (human gate); the simulator uses one approver.
- LLM role agents (§29.5) behind the same `Actor` interface; per-seed output caching.
- Stamp simulated time on MCP and decision events if the MCP server and the accept route ever read the header.
- More record types than `core.Record` once the modules exist (welds, spools, ITRs).

## Cost notes
Four implementer tickets and four reviews in batch 1, all first-pass; four fresh reviews of supervisor pieces (three found real defects).
