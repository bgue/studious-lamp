# P2-INSP — Inspections and checklists in the quality module

Status: planning (r0 written by the orchestrator, 2026-11-15; nothing dispatched). 3 pieces, 15 tickets.
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
check). C3: every ticket merged or abandoned. C4: per-folder gates on touched packages, `gate-pg` on touched
directories, demo on both adapters, tour shots, security review closed.

## Items
Tier B = builder piece (`kind: piece`); H = implementer ticket. Sec = a row for the wave's security review.

| ID | Title | Tier | Depends | Sec | Review |
|---|---|---|---|---|---|
| S1 | Schema: `Checklist`, `Inspection`, events, two workflows, two numbering patterns, six words, one setting, three checklist fixtures, projectors, `ModuleSpec` record types, pins (spec: `S1-schema-and-projectors.md`) | B | `p2/ip` | — | full |
| S2 | Commands and engine: the eleven commands of the design §4 with guards (verifier is not the recorder, published is immutable, hidden subject reads as missing), pure `insp_rules.py` (`result_of`, `failed_questions`, `validate_answers`; provided test), punch items raised in the same unit of work, subject part in `confidentiality.py`, `PROPOSABLE` row `propose_inspection`, exclusions, hooks (`commands` ref widened to all quality commands); sentinel + ≤ 5 mutants | B | S1, P2-X4 C2 on trunk | yes | full |
| S3 | Readiness check `inspections_planned` for real (design §5): `tl_mod_quality/checks.py`, entry point, the placeholder's entry-point line removed from the awp package, registry pin, contract test | B | S2 | — | full |
| T01 | Read views `tl_mod_quality/insp_views.py`: `inspection_list`, `inspection_detail`, `inspection_counts`, `inspections_for(record)`, `checklist_list`, `checklist_detail`, `export_rows(rows, "csv"\|"jsonl")` | H | S2 | yes | full |
| T02 | Checklist runner model `tl_mod_quality/runner.py` (pure, Textual-free: current question, accept a key, back, review page, computed result through `insp_rules`); provided test | H | S2 | — | lite |
| T03 | Generator: checklists and inspections in the demo project's `quality` section (`dev/seed/demo_project/quality.py`), pins | H | S2 | — | full |
| T04 | CLI group `tl insp` (plan, schedule, record, verify, reinspect, cancel, ls, show, export) in the module package, through the `cli_groups` hook | H | T01 | — | full |
| T05 | CLI group `tl checklist` (create, edit, publish, revise, retire, ls, show) | H | T01 | — | full |
| T06 | API read router (five GETs of the design §7) in the module package through `read_routers`; five-reader walk | H | T01 | yes | full |
| T07 | MCP read tools and `propose_inspection` through `tools`; closed until listed; walk | H | T01 | yes | full |
| T08 | Client methods and fakes | H | T06 | — | full |
| T09 | Scan card `quality.Inspection` (`tl_mod_quality/scan_card.py`, entry point) over the frozen card contract | H | T01, P2-QR C1 and QR T03 | yes | full |
| T10 | Terminal: `inspection_text.py`, inspection log and record screen with actions | H | T08 | — | full |
| T11 | Terminal: run-a-checklist screen over T02's model | H | T08, T02 | — | full |
| T12 | Terminal: `checklist_text.py`, checklist list and record | H | T08 | — | full |
| T13 | Navigation and palette lines for the three screens (the shared one-line files) | H | T10, T11, T12 | — | lite |
| T14 | Demo `dev/demos/P2-INSP.sh` and driver | H | T04–T07, T13, T03 | — | full |
| T15 | Tour shots (log, record, runner, checklist record) and docs: module README and AGENTS, `docs/modules/quality/`, runbook `docs/runbooks/inspections.md`, root `AGENTS.md` row | H | T14 | — | lite |

## Waves (implementer tickets in one wave have disjoint paths; gates name test files, never a whole package)
| Wave | Runs together | Notes |
|---|---|---|
| 1 | S1 | Alone on shared pins and generated files |
| 2 | S2 | The supervisor writes the provided tests of T01 and T02 from S2's names while it builds |
| 3 | S3 ∥ T01 ∥ T02 ∥ T03 | Four different files or folders |
| 4 | T04 ∥ T05 ∥ T06 ∥ T07 | Two CLI files, one routes file, one tools file; none touches a shared list (hooks) |
| 5 | T08 ∥ T09 | |
| 6 | T10 ∥ T11 ∥ T12 | Three new widget files and their text modules; no shared file |
| 7 | T13, then T14, then T15 | |
At most two heavy test runs on the box at once: the gate runner takes tickets two at a time.

## APPROVALS lines needed before merge (the orchestrator never self-approves; the owner or a delegation does)
- S1 · schema merge `schema/modules/quality/{checklist,inspection,events}.yaml`, two workflow fixtures, two numbering
  patterns, `schema/fixtures/quality/checklists/*.yaml` (additive; no existing class or event changes).
- S1 · settings `quality.inspections.required_for_iwp`; six access words `quality.checklist.*`, `quality.inspection.*`.
- S2 · security: `tl_core/confidentiality.py` subject part for `quality.Inspection`; access-worded commands.
- S3 · core interface: readiness registry: `inspections_planned` moves from `tl_mod_awp.checks_na` to the quality
  package (the contract file `tl_core/readiness/types.py` does not change).

## Security rows (one review at C4, range `p2/ip` base..head)
S2 subject join and the two-hop rule; verifier differs from recorder; recorder and planner taken from the context
actor, never an input; answers validated against the pinned version with bounds; punch items inherit the subject;
T01 `viewer=` defaults to the lowest clearance, filter before LIMIT and counts; T06 and T07 walks and no agent write
beyond the proposal; T09 card answers `None` for a hidden record.

## Risks and escalation triggers
- S2 changes the quality `commands` hook reference from the punch table to one table for the module. It needs P2-X4
  C2 on the trunk; until then S2 waits and S1's tickets cannot start.
- The awp entry-point line removed by S3 is in a package another increment may touch: S3 is the only item here that
  edits `packages/tl-modules/awp/pyproject.toml`; P2-PTW S4 edits the neighbouring line and merges after S3.
- T10 to T12 are implementer tickets only because their logic is in Textual-free modules first (`inspection_text.py`, T02's
  runner, `checklist_text.py`; L-P2-WEB1-1). A screen ticket that needs logic stops and goes back to the supervisor.
- Escalate: a frozen contract must change; a word the table lacks; a piece failing twice; S2 needing a `tl_core`
  change beyond the subject part.

## Plan check
Pending (`4 PLANCHK docs/tickets/P2-INSP/README.md`): over 10 items. S1 may be built while it runs; no merge and no
ticket dispatch before each finding is answered here.

## Blocked / Decision
(none yet)
