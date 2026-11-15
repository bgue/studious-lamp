# P2-INSP — Inspections and checklists in the quality module

Status: plan check answered (r1b, 2026-11-15; nothing dispatched). 3 pieces, 16 tickets: 11 in the first slice, 5 in
the follow-up slice. **today** marks today's slice (S1 and T00).
Sources: `docs/build-spec/module-designs/inspections.md` (the design; its defaults are the decisions),
`09-phase3-plan.md` Increment 2 (the slice brought forward), `docs/tickets/P2-PUNCH/README.md` (shape and the punch
compatibility table), ADR-0010, ADR-0016. Branch `p2/insp` from the integration branch `p2/ip`. Worktree
`/home/user/wt/p2-insp`. Piece branches `p2/insp-s<n>-<slug>`, ticket branches `p2/insp-t<nn>-<slug>`, worktrees
`/home/user/wt/insp/<id>`. Board: `STATE.md` (round 1 writes it). Cross-increment order: `docs/tickets/P2-QR/README.md`,
last section.

## Objective
After this increment the `quality` module holds two more record types, `quality.Checklist` and `quality.Inspection`.
A QA lead publishes a versioned checklist. A QC inspector plans an inspection against any record (with a point:
hold, witness, review, surveillance), schedules it, runs the checklist question by question, and the result is
computed; failed questions raise punch items in the same step. A controller other than the recorder verifies. The
readiness check `inspections_planned` answers for real. Reads and writes over CLI (`tl insp`, `tl checklist`), API,
client, terminal (log, record, checklist runner) and MCP reads plus `propose_inspection`; CSV and JSONL exports; a
status card for the QR scan page. Nothing about punch items changes. Out of scope: see the design §11.

## Demo
`dev/demos/P2-INSP.sh` (`just demo P2-INSP`, SQLite then Postgres): the eight clauses of the design §10. A
`PASS clause N` line is printed only after a real check returned success. Clause 8 lives in the P2-QR demo.

## Checkpoints
C1: S1 merged to `p2/ip` (schema, words, setting, projectors; APPROVALS). C2: S2 and S3 merged (commands, readiness
check; hooks follow later, see risks). C3: every ticket merged or abandoned. C4: per-folder gates on touched packages, `gate-pg` on touched
directories, demo on both adapters, tour shots, security review closed.

## Items (first slice)
Tier B = builder piece (`kind: piece`); H = implementer ticket. Sec = a row for the wave's security review.
INSP surfaces live where the quality surfaces live (`tl_api.routes`, `tl_cli`, `tl_mcp`; `quality` is in
`IN_TREE_SURFACES`), not in the module package.

| ID | Title | Tier | Depends | Sec | Review | Slice |
|---|---|---|---|---|---|---|
| S1 | Schema: `Checklist`, `Inspection`, events, two workflows, two numbering patterns, six words, one setting, three checklist fixtures, projectors, `ModuleSpec` record types, pins (spec: `S1-schema-and-projectors.md`) | B | `p2/ip` | - | full | today |
| T00 | Pure `tl_mod_quality/insp_rules.py` (`validate_questions`, `validate_answers`, `failed_questions`, `result_of`); ticket `T00-insp-rules.md`, provided test | H | S1 | - | full | today |
| S2 | Commands and engine as handlers with no hook fields: the eleven commands of the design §4 with guards (verifier is not the recorder, published is immutable, hidden subject reads as missing), calls `insp_rules` (T00), punch items raised in the same unit of work, subject part in `confidentiality.py`, `PROPOSABLE` row `propose_inspection`, exclusions, error types that raise core error classes, the provided test of T01; sentinel + at most 5 mutants | B | S1, T00 | yes | full | later |
| S3 | Readiness check `inspections_planned` for real (design §5): `tl_mod_quality/checks.py`, entry point, the placeholder's entry-point line removed from the awp package, registry pin, contract test; paths include `dev/accept/P2-I2/T06b.py` | B->t | S2 | - | full | later (a `t` ticket, full review) |
| T01 | Read views `tl_mod_quality/insp_views.py`: `inspection_list`, `inspection_detail`, `inspection_counts`, `inspections_for(record)`, `checklist_list`, `checklist_detail`, `export_rows(rows, "csv"\|"jsonl")` | H | S2 | yes | full | later |
| T03 | Generator: checklists and inspections in the demo project's `quality` section (`dev/seed/demo_project/quality.py`), pins | H | S2 | - | full | later |
| T04 | CLI group `tl insp` (plan, schedule, record, verify, reinspect, cancel, ls, show, export) in `tl_cli` | H | T01 | - | full | later |
| T05 | CLI group `tl checklist` (create, edit, publish, revise, retire, ls, show) in `tl_cli` | H | T01 | - | full | later |
| T06 | API read routes (five GETs of the design §7) in `tl_api.routes`; five-reader walk | H | T01 | yes | full | later |
| T07 | MCP read tools and `propose_inspection` in `tl_mcp`; closed until listed; walk | H | T01 | yes | full | later |
| T08 | Client methods and fakes | H | T06 | - | full | later |
| T09 | Scan card `quality.Inspection` (`tl_mod_quality/scan_card.py`, entry point) over the frozen card contract | H | T01, QR C1 and QR T03 | yes | full | later |
| T10 | Terminal: `inspection_text.py`, inspection log and record screen with actions | H | T08 | - | full | later |
| T14 | Demo `dev/demos/P2-INSP.sh` and driver (clause 8 lives in the P2-QR demo) | H | T04-T07, T03, T10 | - | full | later |
| T15 | Tour shots (log, record) and docs: module README and AGENTS, `docs/modules/quality/`, runbook `docs/runbooks/inspections.md`, root `AGENTS.md` row | H | T14 | - | lite | later |

### Follow-up slice (not scheduled; each waits for the first slice to merge and for a fresh plan round)
| ID | Title | Why it waits |
|---|---|---|
| T02 | Checklist runner model `runner.py` (pure; provided test) | Only the runner screen uses it |
| T11 | Terminal: run-a-checklist screen over T02 | Behind T02 |
| T12 | Terminal: `checklist_text.py`, checklist list and record | Checklists are read over CLI, API and MCP first |
| T13 | Navigation and palette lines for the screens (shared one-line files) | Nav work waits for the screens |
| - | Hook declaration of the module surfaces (`commands` widened to the quality table) | Needs P2-X4 C2 in `p2/ip` |

## Waves (workflows of at most 3 items; gates name test files, never a whole package)
| Wave | Runs together | Notes |
|---|---|---|
| 1 | S1 (with QR S1) and, once S1 is merged, T00 | **today**; T00 is a one-ticket workflow with PTW T00 and QR T02/T03 as the slots allow |
| 2 | S2 | Writes the provided test of T01 under `provided/` while it builds (F8) |
| 3 | S3 (a `t`, full) and workflow {T01, T03} | |
| 4 | workflow {T04, T05, T06}, then {T07, T08, T09} | Surfaces in `tl_cli`, `tl_api.routes`, `tl_mcp`: disjoint files |
| 5 | T10 | |
| 6 | T14, then T15 | |
At most two heavy test runs on the box at once.

## APPROVALS lines needed before merge (the orchestrator never self-approves; the owner or a delegation does)
Approvers: the owner for the schema merge, the security lines and the core interface; no safety-lead line here.
- S1 - schema merge `schema/modules/quality/{checklist,inspection,events}.yaml`, two workflow fixtures, two numbering
  patterns, `schema/fixtures/quality/checklists/*.yaml` (additive; no existing class or event changes).
- S1 - settings `quality.inspections.required_for_iwp`; six access words `quality.checklist.*`, `quality.inspection.*`.
- S2 - security: `tl_core/confidentiality.py` subject part for `quality.Inspection`; access-worded commands.
- S3 - core interface: readiness registry: `inspections_planned` moves from `tl_mod_awp.checks_na` to the quality
  package (the contract file `tl_core/readiness/types.py` does not change).

## Security rows (one wave review over `d4e92ffc..<p2/ip head>` with the union of the Sec rows of the three increments)
S2 subject join and the two-hop rule; verifier differs from recorder; recorder and planner from the context actor,
never an input; answers validated against the pinned version with bounds; punch items inherit the subject; T01
`viewer=` defaults to the lowest clearance, filter before LIMIT and counts; T06 and T07 walks and no agent write
beyond the proposal; T09 card answers `None` for a hidden record.

## Risks and escalation triggers
- S2 is built without hook fields (F2): it needs no X4 code. The hook declaration (the quality `commands` reference
  widened to one table, at most 5 lines) is a later small ticket after X4 C2 reaches `p2/ip`. Module error types
  raise core error classes (the errors hook is DEFERRED).
- The awp entry-point line removed by S3 is in a package another increment may touch: S3 is the only item here that
  edits `packages/tl-modules/awp/pyproject.toml`; P2-PTW S4 edits the neighbouring line and merges after S3
  (shared-file owner rule in the P2-QR fan-out).
- T10 is an implementer ticket only because its logic is in a Textual-free module first (`inspection_text.py`;
  L-P2-WEB1-1). A screen ticket that needs logic stops and goes back to the supervisor.
- Escalate: a frozen contract must change; a word the table lacks; a piece failing twice; S2 needing a `tl_core`
  change beyond the subject part.
- Fan-out rules (merge order, shared files, heavy runs, today's slice): P2-QR README, last section.

## Blocked / Decision
(none yet)

## Plan check
Answered 2026-11-15 (r1b); the orchestrator accepted every finding.
| F | Sev | Finding | Answer here |
|---|---|---|---|
| F1 | HI | QR URL under `/web` | Applies to QR; the inspection card's `open_path` starts with `/web/` as the contract demands |
| F2 | HI | Hooks need X4 C2 | S2 has no hook fields; hook declaration later; errors hook DEFERRED |
| F3 | HI | At most 2 heavy runs | INSP S1 runs with QR S1; PTW S1 after one ends |
| F4 | HI | Shared files beyond the pins | Owner rule extended (QR README fan-out); INSP appends its lines to `SUBJECT_LINKS`, awp entry points, nav, MCP allowlist, seed list, `AGENTS.md` |
| F5 | MD | S1 merge order | First signed S1 merges first; later ones merge `p2/ip`, `just gen`, re-pin |
| F6 | MD | Surfaces and deps | INSP surfaces stay in `tl_api.routes`, `tl_cli`, `tl_mcp`; no new deps |
| F7 | MD | Pure rules out of S2; tiers | `insp_rules.py` is T00 (Haiku, full, provided test); S3 is a `t` with full review |
| F8 | MD | Provided tests | The S2 builder writes T01's provided test under `provided/`; T00's test exists now |
| F9 | MD | Scope | T02, T11, T12, T13 moved to the follow-up slice (T12 here: checklist screens) |
| F10 | MD | Workflows of 3 | Waves above |
| F11 | MD | Today's slice | S1 and T00 (with QR S1, QR T02/T03, PTW S1 and T00) |
| F12 | MD | QR label rule and rate limit | QR only |
| F13 | LO | Approvers | Owner for schema, security and core-interface lines; one wave security review |
| F14 | LO | Demo clauses; T06b | QR demo clause 8 covers the inspection card; `dev/accept/P2-I2/T06b.py` added to S3's paths |
