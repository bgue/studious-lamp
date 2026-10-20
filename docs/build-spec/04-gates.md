# Build spec 04 — Gates

> **Process v2.** How and how often the gates run (one `just gate` per branch by the gate-runner, the full gate once
> at DONE, parity on touched directories, capped mutation checks, one security review per wave) is defined in the
> `subagent-throughput-process` skill rules 3, 4 and 7. This file says what must be green and who approves.

## 1. CI gates (every PR, every tier)

| Gate | Command / job | Blocks | Owner when red |
|---|---|---|---|
| Lint, format, types | `just check` | merge | ticket author |
| Codegen drift | part of `just check` | merge | ticket author (regenerate, commit) |
| Unit + integration tests (SQLite) | `just test` | merge | ticket author |
| Parity (SQLite + Postgres) | `just test-parity` | merge when `packages/tl-adapters/**` or `tl_core/ledger/**` changed; nightly otherwise | supervisor |
| Projection determinism | `pytest tests/property -k projection` | merge when projections changed | supervisor |
| TUI snapshots | `just test-tui` | merge when `packages/tl-tui/**` changed | ticket author |
| Contract tests (API, MCP, webhooks vs catalog) | `pytest tests/contract` | merge from increment 4 | supervisor |
| Schema classification | `tl schema classify --base origin/main` | merge of any `schema/**` change; `breaking` needs upcaster + ADR + human | supervisor + human |
| Security scan | dependency audit, secret scan | merge | supervisor |

"Green" means every applicable row passes on the PR head after merge-simulation with the increment branch.

**How the rows run.** `just gate <base>` (`dev/gate.sh`, being added) runs the applicable rows for a branch in
sequence, each part in its own `--basetemp`, and writes `.gate/summary.txt` (≤ 12 lines, last line `GATE: green|red`).
It is run once per branch by the `gate-runner` inside the ticket workflow and read by the reviewer; `just gate --full`
runs every row plus parity of the touched directories once per increment, at DONE, by the orchestrator. Until the
recipe lands, the gate-runner runs `just check` and the package suites the ticket names. Nobody polls a log.

| Check | Cap (skill rule 4) |
|---|---|
| Mutation on a core piece | sentinel + ≤ 5 targeted mutants, by the builder, in its worktree, 3 lines in the report; the full sweep is phase-exit work |
| Security review | one per wave, scoped to the `Sec` rows and a commit range, ≤ 450 k tokens; fixes as pieces or tickets; one re-check of the fix commits |
| Parity | touched directories per increment; the whole parity suite at phase exit on dedicated time |
| Full suite | once per increment at DONE; never on a ticket branch |

## 2. Human gates (from §25.5)

| Change | Approver | How recorded |
|---|---|---|
| Any `schema/**` merge | Named human schema owner | Ticket label `schema`, approver in header, PR approval |
| Migration or data conversion job | Named human | ADR + PR approval |
| Auth, permissions, confidentiality filters | Named human | PR approval |
| Contractual workflow or clock definitions (M10) | Commercial/legal lead | PR approval |
| New dependency with copyleft or unclear licence (e.g. xeokit, Q9) | Human | ADR |
| Spend above the phase budget | Human | Note in phase report |

The supervisor marks a PR `needs-human` and stops; the orchestrator never substitutes for a human gate.

## 3. Review separation

- Implementer branch → gate-runner → reviewer (`lite` Haiku or `full` Sonnet per the ticket header, fresh context) → orchestrator merges.
- Builder piece branch (the supervisor-tier list in `01-tiers.md` §3) → gate-runner → `full` reviewer → orchestrator or human sign-off → orchestrator merges.
- Orchestrator never reviews implementer branches; it reads gate summaries and verdicts.
- A big plan → `plan-check` (strongest tier) → answered under `## Plan check` → dispatch.

## 4. Merge order inside an increment

1. Interfaces, test scaffolds and builder pieces (checkpoint C1, then C2 for commands and registrations).
2. Tickets in dependency order from the plan; independent tickets in any order (C3 when all are merged).
3. Demo script ticket, full gate, security review, report last (C4, DONE).

## 5. Merge order across workstreams (fanout)

Fixed in the fanout plan. Default: platform core → schema → adapters → API/MCP → TUI → sim/lake → docs. The later-merging workstream's supervisor resolves conflicts with a merge commit.

## 6. What a red gate means per posture

- Red on a ticket branch: the gate-runner's summary goes back to the implementer once (`gate-fix`); still red (`gr`) → the supervisor round re-specs or splits it. Never skip or mark xfail.
- Red on the increment branch after a merge: the supervisor round writes a fix piece or ticket first; no new tickets dispatched until green. An environment failure (`ge`: Postgres down, disk full, OOM) is the orchestrator's: re-run the session hook, then re-run the gate once.
- Red on `main` or the integration branch: orchestrator decides revert vs fix-forward within the day; an ADR if the cause was a contract.
