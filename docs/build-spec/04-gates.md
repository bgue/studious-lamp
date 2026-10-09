# Build spec 04 — Gates

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

- Implementer PR → reviewer (Sonnet, fresh context) → supervisor merges.
- Supervisor engine PR (the Sonnet-authored list in `01-tiers.md` §3) → reviewer → orchestrator or human → supervisor merges.
- Orchestrator never reviews implementer PRs.

## 4. Merge order inside an increment

1. Interfaces and test scaffolds (supervisor).
2. Tickets in dependency order from the plan; independent tickets in any order.
3. Demo script and report last.

## 5. Merge order across workstreams (fanout)

Fixed in the fanout plan. Default: platform core → schema → adapters → API/MCP → TUI → sim/lake → docs. The later-merging workstream's supervisor resolves conflicts with a merge commit.

## 6. What a red gate means per posture

- Red on a ticket branch: the implementer fixes it or reports *Blocked*. Never skip or mark xfail.
- Red on the increment branch after a merge: the supervisor owns it immediately; no new tickets dispatched until green.
- Red on `main` or the integration branch: orchestrator decides revert vs fix-forward within the day; an ADR if the cause was a contract.
