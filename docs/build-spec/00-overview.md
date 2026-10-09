# Build spec 00 — Overview: three-tier agent delivery

Status: v0.1. Companion to the brief v0.4 (`docs/brief-v0.4.md`); `§n` cites the brief.

## 1. What this spec is for

The brief says what Throughline is. This spec says how it gets built by a tiered set of AI coding agents,
with humans on the gates the brief already requires (§25.5): schema merges, migrations, security,
contractual workflows and clocks, and spend.

| Tier | Model | Role | Target share of agent calls | Unit of work |
|---|---|---|---|---|
| **Orchestrator** | Opus, occasional | Decomposes a phase into workstreams, writes the contracts between them, fans out supervisors, decides cross-cutting questions, writes ADRs | ≤ 5% | A phase, a fanout, an ADR, a hard escalation |
| **Supervisor** | Sonnet | Owns an increment or workstream end to end: plans, writes tickets with context packs, builds the core engines itself, dispatches implementers, gets reviews, integrates, reports | 20–30% | One increment (§29.3) or one workstream inside a fanout |
| **Implementer** | Haiku | Executes one bounded ticket: code, tests, docs, wiring of generated artefacts | 65–75% | One ticket: ≤ 5 files, ≤ 400 diff lines, one session |

A fourth hat, **reviewer**, is Sonnet in a fresh context that never shares the author's context (§25.5).

## 2. Why this split fits Throughline

Most of the product's surface is generated from LinkML (§6.1, §25.1). That produces a large volume of
mechanical, well-specified work: wire a generator output, implement a handler for a known event, build
a Textual widget from a sketch, write a contract test, add a CLI subcommand. That is implementer work.

A small set of engines carry subtle behaviour: the ledger append + inline projector transaction (§5.4),
the effective-schema compiler (§27.3), workflow guards (§8), numbering allocation (§8), the query language,
sync and merge (§22), ABAC (§8). Those are supervisor work, reviewed by the orchestrator or a human.

A few decisions cut across packages: contracts between workstreams, event-schema evolution, adapter
boundaries, phase sequencing. Those are orchestrator work, recorded as ADRs.

## 3. The loop

```
Human ─ phase goal, brief, gate approvals, phase-exit demo
  │
  ▼
Orchestrator (Opus) ─ phase plan: workstreams, contracts, increment DAG, merge order  [fanout]
  │
  ├─► Supervisor A (Sonnet, worktree) ─ increment plan → tickets + context packs
  │       ├─► Implementer (Haiku, worktree, one ticket) ─ diff + report
  │       ├─► Implementer (Haiku) …  (≤ 4 in parallel, non-overlapping paths)
  │       ├─► Reviewer (Sonnet, fresh) ─ verdict per PR
  │       └─ merge to increment branch, gates, increment report, demo script
  ├─► Supervisor B …
  │
  └─ integrate workstreams in merge order, phase retro, next fanout
```

- The orchestrator is called at phase start, for any fanout with two or more workstreams, for
  escalations that reached it, and at phase exit. Between those points supervisors run alone.
- Single-workstream increments (Phase 0 increments 1 and 3) skip the orchestrator: the human hands
  the increment to a supervisor directly.

## 4. Cadence and budgets

| Item | Value |
|---|---|
| Increment | The §29.3 unit. One supervisor, 10–25 implementer tickets, 0–1 orchestrator fanout |
| Parallel implementers per supervisor | ≤ 4, only when their *Allowed paths* do not overlap |
| Supervisors per fanout | ≤ 5 |
| Orchestrator calls per phase | Phase start, each fanout, each escalation, phase exit; expect 4–8 for Phase 0 |
| Implementer ticket | ≤ 5 files touched, ≤ 400 diff lines, ≤ 6 context files, tests or executable acceptance given |
| Two-strikes rule | A ticket that fails review twice becomes the supervisor's; a workstream the supervisor fails twice escalates |
| Demo | Every increment ends with `just demo <increment-id>`, runnable by a human |

## 5. Reading order per tier

| Tier | Read, in order |
|---|---|
| Orchestrator | `AGENTS.md`; this file; `01-tiers.md`; `05-phase0-plan.md` or `06-later-phases.md`; the whole brief; `docs/adr/`; latest `docs/reports/` |
| Supervisor | `AGENTS.md`; this file; `01-tiers.md` §3; `02-task-protocol.md`; `03-repo-and-toolchain.md`; `04-gates.md`; the increment section of the plan; the brief sections it cites |
| Implementer | `AGENTS.md`; the ticket; the ticket's *Context* files only |
| Reviewer | `AGENTS.md`; the ticket; the diff; `02-task-protocol.md` §6 |

## 6. Principles carried from the brief into the build

- **Ledger first.** The build is itself ledgered: tickets, reports, verdicts, and ADRs are files in git. Nothing is decided in chat only.
- **Schema is the product.** Schema tickets are a separate class with a named human approver.
- **Dev small, prod big.** Everything runs on SQLite + MinIO first; the parity suite gates Postgres (§15).
- **Spec-driven.** No ticket without tests or an executable demo. No generated file edited by hand.
- **Same core, many faces.** The TUI, API, and MCP call the same command and query contracts; a ticket that puts logic in a screen fails review.

## 7. File map

| File | Contents |
|---|---|
| `01-tiers.md` | Role contracts for orchestrator, supervisor, implementer, reviewer; suitability matrix; Haiku-ability checklist; escalation ladder; fanout mechanics |
| `02-task-protocol.md` | Ticket lifecycle and anatomy, context packs, reports, review checklist, two-strikes rule, branches and commits, definitions of done |
| `03-repo-and-toolchain.md` | Monorepo layout, toolchain, `just` recipes, generated-code policy, Phase 0 core interfaces and event types |
| `04-gates.md` | CI gates, human gates, merge order, what "green" means |
| `05-phase0-plan.md` | Phase 0 increments 1–8 decomposed into supervisor work and implementer tickets |
| `06-later-phases.md` | Fanout seeds for Phases 1–5 |
