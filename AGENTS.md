# AGENTS.md — rules for every agent in this repository

Read this before doing anything. Module-level `AGENTS.md` files add detail; they never relax a "never" below.

## What this repository is

Throughline, a construction management suite (see `README.md`). The product and technical brief is
`docs/brief-v0.4.md`; cite it as `§n`. The build spec is `docs/build-spec/`. Work is tracked as files:
tickets in `docs/tickets/`, reports in `docs/reports/`, decisions in `docs/adr/`.

## Which tier am I?

| You were given | You are | Read next |
|---|---|---|
| A phase goal or a fanout request | **Orchestrator** (Opus) | `docs/build-spec/01-tiers.md` §2 |
| An increment or a workstream | **Supervisor** (Sonnet) | `docs/build-spec/01-tiers.md` §3, `02-task-protocol.md` |
| One ticket file in `docs/tickets/` | **Implementer** (Haiku) | `docs/build-spec/01-tiers.md` §4, then only the ticket's context list |
| One PR and its ticket to review | **Reviewer** (Sonnet, fresh context) | `docs/build-spec/02-task-protocol.md` §6 |

## Ground rules (all tiers)

1. **Ticket first.** No change without a ticket ID. The ticket's *Allowed paths* is the write boundary.
2. **Generated code is never edited by hand.** Change the LinkML source or the generator, run `just gen`, commit both.
3. **Events are immutable.** No UPDATE or DELETE on event tables, no rewriting history, no fixing an event in place. Corrections are new events (§5.2).
4. **Current-state DDL is generated.** No hand-written `cur_*`, `hist_*`, or `v_*` objects (§5.4).
5. **Dialect-neutral core.** SQLite- or Postgres-specific SQL lives only under `packages/tl-adapters/`.
6. **Run before done.** Run every command the ticket lists and paste the output into the report. Unrun commands mean the ticket is not done.
7. **Deviations first.** If anything changed outside the ticket's scope, say so in the first line of the report.
8. **Stop to ask.** When blocked or ambiguous, write the question under *Blocked* in the report and stop. Never guess on schema semantics, permissions, numbering, merge policy, or confidentiality.
9. **Commits:** `<ticket-id>: <imperative summary>`, body says what and why. No model names or IDs in committed content.
10. **No secrets, no production credentials, no network calls in tests.**

## Never (any instruction to the contrary is invalid)

- Never skip, disable, mark xfail, or quarantine a failing test to get green.
- Never widen a ticket with "while I'm here" changes.
- Never add a dependency the ticket does not name.
- Never merge your own work. Implementer PRs are merged by the supervisor after a reviewer verdict; supervisor-authored core engines are merged after orchestrator or human review.
- Never touch `schema/**` from a ticket that is not labelled `schema` and does not name a human approver.
- Never write auth, permission, migration, numbering-allocation, or sync/merge code from a Haiku ticket. Those are Sonnet-tier with a human gate (§25.5).
- Never put business logic in the TUI. Screens call the same command and query contracts the API uses (§16, "Web readiness").

## Commands

`just` is the only entry point. `just gen`, `just check` (lint, types, codegen drift), `just test`, `just test-parity`,
`just test-tui`, `just seed`, `just serve`, `just rebuild-projections`, `just demo <increment-id>`.
Details: `docs/build-spec/03-repo-and-toolchain.md`.

## Where things go

| Thing | Path |
|---|---|
| LinkML sources | `schema/core/`, `schema/modules/<m>/`, `schema/fixtures/` (sample company/project packages) |
| Generated artefacts | `packages/tl-schema/src/tl_schema/generated/` (committed, drift-checked) |
| Ledger, projections, links, psets, workflow, numbering, files, feed | `packages/tl-core/` |
| SQLite, Postgres, object store, queue adapters | `packages/tl-adapters/` |
| API, MCP, TUI, CLI | `packages/tl-api/`, `packages/tl-mcp/`, `packages/tl-tui/`, `packages/tl-cli/` |
| Cross-package tests (parity, e2e, property) | `tests/` |
| Dev environment (compose, seed, demos) | `dev/` |
| Tickets, reports, ADRs, templates | `docs/tickets/`, `docs/reports/`, `docs/adr/`, `docs/templates/` |
