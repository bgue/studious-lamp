# P2-I1 — Work breakdown, cost-code mapping, path of construction, CWA and CWP (module M3, part 1)

Status: in-progress (round 1). Spec: `docs/build-spec/specs/m3-wbs-cwp.md` (v0.2, plan-checked, it wins). Wave order and
registries: `docs/build-spec/specs/phase2-wave-plan.md`. Board and next steps: `STATE.md`.

## Objective
After this increment a new `awp` module holds the general contractor's work breakdown structure (WBS), maps each leaf
node to cost codes in percent, keeps the path of construction as a versioned ordered list of construction work areas
(CWAs), and lets planners create, allocate, link and move construction work packages (CWPs) through development; a
superuser releases a CWP for work-package development. A background job rolls CWP budget hours up to WBS nodes and cost
codes. The same data reads over the terminal, web, API and MCP. Out of scope: installable work packages, scope items,
constraints, readiness, credit rules, progress.

## Demo
`just demo P2-I1` (SQLite, then Postgres, nine clauses in spec §11): load the WBS and CWA spreadsheets, re-sequence the
path, create and release CWPs with the right roles, run the rollup, and see the same CWP in the API, the terminal and
MCP. `just tour` runs once at the end.

## Order of work
Critical path: S2 -> S3 -> S4 -> T10 -> T03a -> T03b -> T05a -> T05b/T05c -> T11 -> T08. S5 (rollup job) runs beside S4.
Checkpoints: C1 = S2, S3; C2 = S4, S5, T10, T03a, T03b; C3 = all tickets (tests last); C4 = demo green on both adapters.
Process: tests are deferred to one test piece (T11) at C3; each piece leaves an acceptance script in
`dev/accept/P2-I1/<id>.py` and no pytest; no security review unless the owner asks; the schema piece is a human gate
(owner, or the orchestrator under P2-Q10). M3 merges before the parallel materials increment; registry files are
regenerated on the later side, never hand-merged.

## Pieces and tickets (file names)
| Spec id | File | Kind | Review | Depends on | Round |
|---|---|---|---|---|---|
| S2 | `S2-awp-schema.md` | piece (schema, gate) | full | wave 0 | 1 |
| S3 | `S3-awp-package-wbs-path-cwa.md` | piece | full | S2 | 2 |
| S4 | `S4-awp-cwp-packages-actions.md` | piece | full | S3 | 3 |
| S5 | `S5-awp-rollup-job.md` | piece | full | S3 | 3 |
| T02 | `T02-load-targets.md` | ticket | full | S3 | 3 |
| T01 | `T01-samples-loaders.md` | ticket | lite | T02 | 4 |
| T10 | `T10-views.md` | ticket | full | S4 | 4 |
| T03a, T03b | `T03a-api-routes.md`, `T03b-clients.md` | tickets | full | T10, T03a | 5 |
| T04 | `T04-cli-reports.md` | ticket | full | S5, T10 | 5 |
| T05a, T05b, T05c | `T05a-cwp-register.md`, `T05b-wbs-cwa-screens.md`, `T05c-path-package-screens.md` | tickets | full | T03b, T05a | 6 |
| T06, T07 | `T06-mcp-tools.md`, `T07-sim-actor.md` | tickets | full, lite | T03a; T03b, T06 | 6 |
| T11 | `T11-tests.md` | tests piece | full | S2-S5, T01-T07, T10 | 7 |
| T08, T09 | `T08-demo.md`, `T09-docs.md` | tickets | full, lite | T11, T05, T06, T07; T04, T05 | 8 |

## Risks and escalation
Spec §12. Rollup scale (5 000 nodes by 2 000 CWPs) is benchmarked in S5 before C4. Deferred tests mean a defect shows
at T11, so every gate runs the existing suites for the directories a diff touches. Escalate: an interface another
stream consumes must change; a schema semantic is unclear; the same piece fails twice.
