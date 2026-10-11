# Increment plan — P0-I8 workstream E: Exit (demo, audit, risks, phase report)

Status: done
Supervisor session: 2026-10-11
Brief sections: §16 Phase 0 and its Exit line, §15 (targets), §17 (risks), §24 (operations, for the audit of upgrade tooling), §7 (cross-reference operations)
Branch: `p0/i8e` (base `p0/i8`; worktree `/home/user/wt/p0-i8e`). Fanout: `docs/tickets/P0-I8/FANOUT.md` (workstream E, decision D14).

## Objective
Demonstrate each clause of the §16 Phase 0 exit on a simulated project, and record honestly what Phase 0 did and did not build. Deliverables: `dev/demos/P0-I8.sh` (`just demo P0-I8`), `docs/reports/PHASE-0-AUDIT.md`, `docs/reports/RISKS.md`, `docs/reports/PHASE-0.md`, `docs/reports/P0-I8.md` (the increment report covering workstreams A to E), and a check of every `04-gates.md` §1 gate on the merged branch.

## Demo
```
just demo P0-I8
```
Takes about 90 seconds. It starts `tl serve` over a temporary ledger, seeds a simulated project (`tl sim seed --scale xs`), then prints one `PASS` line for each of: `exit-1 TUI`, `exit-1 API`, `exit-1 MCP`, `exit-2 live`, `extension types`, `settings live`, `exit-3 webhook`, `exit-4 restore` (and `exit-4 restore (postgres)` when a Postgres server answers at `TL_PG_URL`). It exits non-zero and prints `DEMO FAILED: ...` when any clause is missing. The driver is `dev/demos/p0_i8_demo.py`. The `extension types` step (added after workstream B merged) registers the example packages while the server runs, creates an object-backed and a managed instance, links, filters, reads the body over MCP and checks the second TUI.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S80 | Exit demo script and driver | It composes six surfaces and needs judgment about what counts as evidence (an independent receiver, equal `cur_*` tables across dialects) | none yet (a reviewer pass is requested in the relay) | built |
| S81 | `PHASE-0-AUDIT.md`, `RISKS.md` | Needs the code read, not only the reports | none (documents) | built |
| S82 | `PHASE-0.md` draft | Consolidates every report | none (document) | built, final numbers pending |
| S85 | Extension-type demo step | Needs B | | built |
| S86 | B rows of audit, risks, phase report | Needs B | | built |
| S88 | D rows of audit, risks, phase report | Needs D | | built |
| S89 | Gate check on the merged branch, increment report | Needs D merged | | built |

## Tickets
None dispatched. The Haiku-ability checklist (`01-tiers.md` §6) was run on the candidate "a demo step helper": it fails items 2 and 7 (the helper's interface is the demo's, which is not yet stable, and a reviewer cannot verify an evidence claim from a diff). The documents fail item 5's spirit (judgment about status and risk). Fewer agents were also safer: usage limits cut earlier sessions three times.

| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| (none) | | | | | |

## Order of work (all done)
1. Read the reports, learnings and code behind each §16 bullet (done).
2. Demo skeleton on `p0/i8` (A and C only): the four clauses, the settings extra (done, S80).
3. Audit, risk register, phase report draft (done, S81, S82).
4. When B lands: merge `p0/i8`, add the extension-type leg to the demo, update the audit and risk rows marked pending.
5. When D lands: merge `p0/i8`, bring the performance figures into the audit, risks and phase report.
6. Run every `04-gates.md` §1 gate on the merged branch; write `docs/reports/P0-I8.md`; append learnings.

## Risks and escalation triggers
- The demo exposes a real defect: report it BLOCKED to the coordinator; do not widen scope. (None so far.)
- The container is shared, so timings in the demo vary; the live-update budget (2 s) has a 20-fold margin in the measured runs (about 0.1 s).
- A usage limit stops the session: everything is committed after each deliverable.

## Blocked / Decision
(none)
