# P2-I3 — M4 materials: item library, locations, receipts, ledgered stock, MTO, reservations

Status: in-progress (round 1). Spec: `docs/build-spec/specs/m4-materials.md` (v0.2, plan-checked; §9 is the piece and ticket list).
Wave plan: `docs/build-spec/specs/phase2-wave-plan.md` §1 and §3. Board and next steps: `STATE.md`. Branch `p2/i3`.

## Objective
After P2-I3 the `materials` module runs on the ADR-0010 seam: a company item library, project items, a five-level location
tree, PO-line mirrors, receipts with heat numbers and MTRs, stock as the projection of `StockLot.Moved` events (never negative),
MTO lines published from derived documents, reservations against MTO lines, and the `materials_reserved` readiness check; with
API, CLI, TUI logs, MCP tools and a simulator actor. M4 is the wave-1 registry owner and merges last (after P2-I1); it
regenerates the pinned lists, never hand-merges them.

## Demo
`just demo P2-I3` (SQLite then Postgres, one PASS each), eleven clauses: spec §10. Clause 6 needs P2-I1 merged. `just tour 1` once at C4.

## Pieces and tickets
Spec §9 with one split: T01 becomes T01a (sample CSVs, independent of S2, round 1) and T01b (mappings and loaders, after S2).
| ID | File | Kind | Review | Depends |
|---|---|---|---|---|
| S1 | `S1-schema.md` | piece, human gate (schema) | full | wave 0 |
| T01a | `T01a-samples.md` | ticket | lite | — |
| S2 | `S2-package-library.md` | piece | full | S1 |
| S3, S4 | receipts and movements; MTO publish target | pieces | full | S2 (S3), S2 (S4) |
| T01b, T03, T04a-b, T05, T06a-e, T07, T08 | as spec §9 | tickets | per spec | per spec |
| T11 | tests (Sonnet), mutants of S1-S4 | piece | full | S1-S4, T01-T08 |
| T09, T10 | demo; docs | tickets | full, lite | per spec |

## Order of work
Critical path S1 -> S2 -> S3 -> T04a -> T04b -> T06a -> T06b -> T06e -> T11 -> T09. Round 1: S1 and T01a. Checkpoints (spec §9):
C1 = S1, S2; C2 = S3, S4, T04a-b; C3 = all tickets, T11 last; C4 = T09 green on both adapters, tour once.
Process: tests deferred to T11 at C3 (pieces leave `dev/accept/P2-I3/<id>.py` plus a named smoke, no pytest); no security
review unless the owner asks (Sec rows recorded); Haiku for every ticket passing `01-tiers.md` §6; schema merges approved by the
orchestrator under P2-Q10 (APPROVALS line at merge).

## Risks and escalation
Spec §11. Stock correctness (R-P2-7): the S3 acceptance script carries the rebuild and concurrent-issue checks until T11.
Pinned lists and generated files: the later-merging side regenerates. ADR-0022 (movements as events) must exist before S1 merges.
