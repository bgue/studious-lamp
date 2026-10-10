# Report — P0-I6 workstream C, simulator v0

Status: complete on `p0/i6c` except the wiring that needs workstream B (see Follow-ups). Written 2026-10-10.

## Outcome
Objective met: yes for everything that does not need workstream B's feed and proposals service; partially for the demo. `sim_create`, `sim_advance`,
`sim_inject`, `sim_status` and `sim_assert` run as a Python API (`tl_sim.api`), as `tl sim` and as an MCP server (`tl_sim.mcp_server`). Three
deterministic actors (document controller, planner, crew) act on generic records, links, workflow transitions and feed posts only through
`ApiClient`. Events carry simulated time. The ground-truth log of one seed is byte-identical on two ledgers. `sim_assert` reads the suite back
through the API and fails closed.

Demo path verified on a clean tree: `dev/demos/P0-I6-C.sh` ran clean on a throw-away merge of `p0/i6c` with `p0/i6b` (all steps, `P0-I6-C demo ok`).
On `p0/i6c` alone it stops at the first post, because `ApiClient.feed_post` and `GET /feed` are workstream B's. It runs as soon as `p0/i6b` is on
the base.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I6-T40 | merged | 1 | document controller; reviewer's Rev Z question ruled: the last revision, never revised |
| P0-I6-T41 | merged | 1 | planner |
| P0-I6-T42 | merged | 1 | crew; ruling: singular and plural in posts |
| P0-I6-T43 | merged | 1 | scenario and template loader |
| P0-I6-T44 | taken by supervisor | n/a | `tl sim` CLI; the reference written to verify the ticket was already the finished code |
| P0-I6-T45 | taken by supervisor | n/a | simulation MCP server; same reason |

## Supervisor-tier pieces (REVIEW-SUPERVISOR-PIECES)
| Piece | Where | Review |
|---|---|---|
| Effective-time contextvar, both ledger adapters, API header | `tl_core/util.py`, `tl_adapters/{sqlite,postgres}/ledger.py`, `tl_api/effective.py`, `tl_api/commands.py` | fresh reviewer: changes requested, fixed in S48 |
| Orchestrator loop and determinism | `tl_sim/orchestrator.py`, `rng.py`, `clock.py`, `state.py`, `injections.py` | fresh reviewer: sound, findings fixed |
| Ground-truth assertion | `tl_sim/assertions.py`, `reader.py`, `groundtruth.py` | fresh reviewer: findings fixed |
| Also supervisor-written, outside the list | `client.py`, `connector.py`, `testing.py`, `cli.py`, `mcp_server.py`, `dev/seed/seed.sh` | not separately reviewed |

## Gates
| Gate | Result |
|---|---|
| `just check` | clean (ruff, pyright, codegen, OpenAPI, licences) |
| `just test` | 3372 passed, 1 failed: `tests/api/test_client_roundtrip.py::test_every_method_exists_with_the_same_parameters`, the known red until workstream B adds the feed methods to `ApiClient` |
| `just test-parity` | not re-run after the review fixes; the adapter change was run on both adapters (17 tests in S40) |
| `just demo P0-I6-C` | clean on the trial merge with workstream B; needs the merge |

## Deviations from plan
- Keys are assigned by the client (`SIM<RUN>-REC-0001`): a `project:sim-<run>` scope cannot be auto-numbered (L-P0-I6C-1; decision C3).
- B15 (orchestrator ruling): the role actors are `user:sim-<role>`; only `agent:sim-assistant` is an agent, and it proposes (decision C9). It has no actor class yet.
- The planner has no proposals in v0; they need the proposals service.
- T44 and T45 were not dispatched (usage limits).
- `tl serve` is used by the demo, since the trunk merge landed.

## Escalations and decisions
README-C decisions C1 to C9. No escalation; no `Command`, `Event`, `Ledger` or `event_hash` change (the hash covers `recorded_at`, not `effective_at`).

## Learnings
L-P0-I6C-1 to L-P0-I6C-9. Implementer proposals declined: none were in conflict; the isort note for T43 and the Bash-tool traps are recorded as L-P0-I6C-8 (traps) and are otherwise tool noise.

## Docs
`packages/tl-sim/README.md` and `AGENTS.md` (new); `docs/runbooks/simulator.md` (new); `packages/tl-core/README.md`, `packages/tl-api/README.md`, `packages/tl-cli/README.md` (updated); `docs/tickets/P0-I6/README-C.md`; `dev/seed/` scenarios and templates.

## Follow-ups filed
When workstream B is merged: swap the end-to-end test's stand-in for the real feed (a prepared version exists), wire `McpCaller` and `HttpReader.proposals`, add the assistant actor and a proposal-accept step, write `dev/demos/P0-I6.sh` and `docs/reports/P0-I6.md`, and run `just test-parity` once.

## Cost notes
Four implementer tickets and four reviews in batch 1, all first-pass.
