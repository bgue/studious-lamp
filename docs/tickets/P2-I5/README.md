# P2-I5 — Weekly cycle, rules of credit, progress, IWP pack, closeout (module M3, part 3), CLI and TUI only

Status: round-1 plan, waiting for the planner-tier check (`4 PLANCHK`). 6 pieces (5 builder + tests), 17 tickets: far over the
~10-ticket line, so nothing is dispatched in round 1; the S1 and S2 specs are written ahead. Plan sources:
`docs/build-spec/08-phase2-plan.md` "Increment 5" (re-cut here), `specs/phase2-wave-plan.md` (wave 3 row),
`module-designs/field-work-packaging.md`, `roadmap-2026-11-07.md` (owner questions P2-Q1, P2-Q11, P2-Q13, W3-5, W3-6, W3-7),
`DEFERRED.md` (wave 3 rows), ADR-0024 to ADR-0027. Board: `STATE.md`.
Branch `p2/i5` from `p2/wave2-close` @ec3314d (P2-I2 merged). Worktree `/home/user/wt/p2-i5`. Runs beside P2-I4-A (`p2/i4a`).

## Objective
After this increment a planner runs the weekly workface-planning cycle from the terminal: look-ahead of the next four weeks
(activities, their IWPs, readiness), constraint review (a superuser may waive a check-raised constraint with a reason),
release, foreman commitments, progress, PPC, closeout. A foreman signs in and lands on the IWP log filtered to mine. Earned
progress comes from linked record states through a rules-of-credit package chosen per project (`awp.rules_of_credit.set`), rolls up
IWP to CWP to WBS node to cost code, and leaves as a CSV per period. The IWP pack renders as HTML (PDF and QR codes when
`reportlab` and `segno` are installed and the flag is on). Closeout takes the actual hours, redlines slot, punch count and feedback.
A subcontracted CWP records progress by CSV; there are no subcontractor accounts. KPIs agree with the ledger on both adapters.
Out of scope: every web page (deferred, below), welds and joints as records (Phase 3), permits, model slice, P6 write-back,
automatic constraint population (needs I4-B), the WBS node workflow, the GC's own rules-of-credit edition (data, later).

## Owner answers applied (2026-11-08)
P2-Q1 C: a sample package `co.acme.awp-roc@1.0.0` now; the GC's edition later as another package; a project picks one with the
existing setting `awp.rules_of_credit.set` (empty = company standard). P2-Q11: HTML always; PDF and QR when `reportlab` and `segno`
(both BSD) are installed, behind the flag `awp.pack.pdf` (S1 adds it; default off). P2-Q13 A: party assignment on a CWP (free text),
interface constraints, progress by CSV import. W3-5: waiver is a superuser act with a reason, ledgered, shown on the IWP (core
word `core.constraint.waive` in `controller`; S4). W3-6: the foreman account role lands on the mine-filtered IWP log (T06c; the
role is data in `module-roles.yaml`, S1). W3-7: `awp.iwp.ready_lead_weeks` already exists with default 4; the look-ahead reads it
(no change). ADR-0025: the intent slot lands via P2-INT before wave 3; no I5 command reads intent, the boundary carries it (S2
greps and says). ADR-0026 F5: `at` of `IWP.Started`, `IWP.FieldCompleted`, `IWP.ProgressRecorded` carries `tl:valid_time` (S1). ADR-0027:
every new command is a `ProposableCommand` row or an entry in `tests/tools/proposable_exclusions.toml` with a reason (default below);
approvals are excluded; edits take `expected_version`.

## Demo clauses (`dev/demos/P2-I5.sh`, SQLite then Postgres; spec of record is `08-phase2-plan.md` I5 plus these)
1. Package `co.acme.awp-roc@1.0.0` loads (scope item steps 30/60/10); a package whose weights do not sum to 100 is refused with a
   fixed message; a project selects it with the setting; a plain user cannot load a package.
2. A new XER snapshot is published; the look-ahead lists the next four weeks of activities with their IWPs and readiness
   (`n/m`), need-by dates from `awp.iwp.ready_lead_weeks`.
3. Constraint review: a check-raised constraint is waived by a superuser with a reason (a plain user is refused, the reason is
   required, the IWP shows it as waived with who and why); then release of the Ready IWPs (I2 sign-off).
4. A blocking constraint raised on an Issued IWP puts it On hold (the rule left open in P2-I2); foremen commit IWPs for the week
   (`expected_version` stale write refused).
5. Progress: scope items move state, earned % per IWP follows the rules, PPC follows the commitments and miss reasons; the rollup
   job writes earned quantities per CWP and WBS node; `tl awp export progress --period 2026-W45` writes the CSV by cost code (a
   cell that starts with `=`, `+`, `-` or `@` is quoted).
6. The pack renders as HTML (cover, scope and steps, drawings with deep links, MTO, safety and quality placeholders, permits and
   scaffold tags as "not tracked yet", sign-off sheet); with the flag and both libraries it also writes PDF with QR codes; with
   either missing the command says so and writes HTML only. Stored in file slot `pack`.
7. Closeout: actual-hours CSV read in the envelope (a bad file is refused whole), redlines slot, remaining punch, feedback; the
   KPIs (backlog weeks, % constraint-free, constraint aging, schedule compliance, PPC, earned vs burned, stale-pin issues) equal
   a ledger recount on both adapters.
8. A CWP assigned to a party records progress by CSV (`RecordSubcontractProgress`); an interface constraint shows in the report.
9. A foreman account lands on the IWP log filtered to mine; others land as before.
10. Agents: a proposal to record progress or commit an IWP is accepted by a person with the access; waiver, close-out and
    weekly close are refused to agents (excluded, with reasons). Same reads over CLI, TUI, API and MCP; the five-reader walk passes.

## Pieces (builder, `kind: piece`, review full; specs `S<n>-<slug>.md`)
| Id | Piece | Spec | Depends | Sec |
|---|---|---|---|---|
| S1 | Schema and package (human gate, P2-Q10): `awp.RulesOfCredit` class, `co.acme.awp-roc@1.0.0` fixture, loader function with weight and bounds checks; `awp.WeeklyPlan` record and commitment rows, workflow, key; IWP progress table; closeout fields; CWP `assigned_party`; events with valid-time tags; access words (`awp.week.*`, `awp.progress.record`, `awp.closeout.*`, `core.constraint.waive`); settings `awp.pack.pdf` and `api.public_base_url` (absent today); `foreman` account role data; `MissReason` code list; ConstraintType code `Interface` (absent today); optional extra `pack` (reportlab, segno) | written | wave 2 close | schema, loader, roles, dependency |
| S2 | Engine and field lifecycle: `earned_fraction(conn, iwp_id)`, scope item moves (`InstallScopeItem`, `ReturnScopeItem`, `VerifyScopeItem`), `RecordManualProgress`, `IWP.ProgressRecorded`, `StartIwpWork`, `CompleteIwpField`, per-project edition resolution, ADR-0027 rows, `awp.progress.*` access. Owns `module.py`, `names.py`, `AWP_COMMANDS` edits for I5 | written | S1 | quantities, state moves |
| S3 | Rollup and export: `awp.rollup` job gains the progress measure (IWP to CWP to WBS to cost code, figures read from `cost.CostCode`, never written there); `export_progress(conn, scope, period)` CSV with the reserved source prefix, formula-safe cells; `tl awp export progress` | at C1 | S2 | money, export |
| S4 | Weekly cycle and constraint rules: `OpenWeeklyPlan`, `CommitIwpToWeek`, `RecordWeekOutcome`, `CloseWeek` (PPC), `look_ahead_view` (joins `tl_mod_schedule.lookahead.look_ahead` with `visible_readiness`, ids only), then phase B: `WaiveConstraint` (core, controller) and the hold-on-new-constraint rule | at C1 | S2 | access words, guard, hold rule |
| S5 | Closeout and subcontract: `CloseOutIwp`, actual-hours reader and `RecordSubcontractProgress` CSV reader both in `run_in_envelope`, `AssignCwpToParty`, interface constraint helper | at C1 | S2 | parsers, envelope |
| S6 | Tests piece at C3: schema, engine arithmetic, weights refusal, waiver and hold guards, week arithmetic and stale write, both CSV readers hostile cases, export injection, five-reader walk of every new route and tool, sentinel + <= 5 mutants per piece | at C3 | all, T11b | - |
Policy kept: tests deferred to S6; each piece leaves `dev/accept/P2-I5/<id>.py`; tour once at C4. Six pieces is over the five-piece mark: S4 carries two
ordered phases (weekly cycle, then constraint rules) and S6 is the tests piece; the cut is a PLANCHK point (splitting phase B out makes seven).

## Tickets (Haiku; `review` lite or full; specs written when their dependencies are in the tree)
| Id | Title | Rev | Depends |
|---|---|---|---|
| T01 | CLI `tl awp roc load\|ls\|show\|set` over the S1 loader and the setting | full | S1 |
| T04 | `look_ahead_view` CLI `tl awp look-ahead` and `tl awp week ls\|show\|commit\|outcome\|close\|ppc`, miss reasons view (print keys, L-P2-I3-3) | full | S4 |
| T06a | TUI weekly cycle steps 1 to 3: `weekly_text.py` (Textual-free), look-ahead, constraint review (waive action), release | full | T11b |
| T06b | TUI weekly cycle steps 4 to 6: commitments, progress and PPC, closeout | full | T06a |
| T06c | IWP log extras: `m` mine filter, Ready and Constraints counts, state-since, discipline and text filters feed the counts; foreman landing default (W3-6); backlog read past 200 (folds P2-I2 follow-ups) | full | T11b |
| T07a | Pack data assembly over committed read views, Jinja2 to HTML, deep links from `api.public_base_url`, PDF and QR behind the flag, stored in slot `pack`; templates are repository files, autoescape on | full | S2, T11b |
| T07b | Pack template: cover, scope and steps, drawings, MTO, safety, ITP, permits, scaffold placeholders, sign-off sheet; snapshot test | lite | T07a |
| T08 | Closeout reads, `redlines` slot view, `tl awp closeout show\|do` over S5 | full | S5 |
| T09 | KPI report functions and tiles (seven) with a ledger-recount test; `tl awp report` names | lite | S3, S4 |
| T10 | Subcontract reads and `tl awp subcontract assign\|import\|ls`, interface constraints report | full | S5 |
| T11a | API read routes for S2 to S5 models (access word before any read; hidden looks like missing), embedded and remote | full | S2-S5 |
| T11b | `ApiClient` and TUI client methods with the fakes (the P1-I4 S9 pattern) | full | T11a |
| T11c | MCP read tools and proposable rows (`propose_progress`, `propose_week_commitment`), closed list lines | full | T11b |
| T12 | `dev/demos/P2-I5.sh`, ten clauses, both adapters | full | T06b, T07b, T09, T10 |
| T13 | Docs: awp README and AGENTS rows, runbooks `weekly-cycle`, `rules-of-credit`, `iwp-pack`, reference page | lite | T12 |
| T14 | Simulator `ForemanDesk` and actor `foreman` (commit, progress, closeout feedback; user acts only) | lite | T11b |
| T15 | Registrations as one ticket only if glue passes 50 lines: `add_typer`, `MCP_ACTIONS`, palette, ADR-0027 baseline | full | S4, T11c |
17 tickets. Every screen ticket needs its text module in the tree first (L-P2-WEB1-1). Splitting T11 in three follows P2-I2 plan check F8.

## Order of work and checkpoints
S1 -> S2 -> S3 beside S4 beside S5 (disjoint handlers; S2 owns `module.py`, the others append at list ends) -> T01 beside T11a -> T11b -> T04, T06a, T06c, T07a, T08, T10, T11c, T14 -> T06b, T07b, T09 -> T12 -> T13; S6 beside T12.
- C1: S1, S2 merged (plan C1 also named the engine; S3-S5 specs are written once S2 is in the tree). C2: S3, S4, S5, T11a, T11b merged and registrations done.
- C3: every ticket merged or abandoned, S6 merged. C4: per-folder gate on touched packages, demo green on both adapters, tour once, SR3 (I5 rows) closed.
Merge order: after I4-A's merge; S1 to S5, then T11a; this increment regenerates pinned lists and `openapi.json` last.

## Seams with P2-I4-A (parallel rounds; no overlapping paths)
I4-A owns `schema/modules/requisitions/`, `packages/tl-modules/requisitions/`, `tl_cli/{req,wo}*.py`, its text, widget and MCP files. I5 owns only
`schema/modules/awp/`, `packages/tl-modules/awp/`, the new awp CLI, text and widget files, `schema/fixtures/standards/co.acme.awp-roc@1.0.0.yaml`,
and `packages/tl-core/src/tl_core/constraints/` (waiver, S4 B). Shared files, edited by adding lines only, each side re-run `just gen`:
`schema/settings/{access-words,module-roles,platform}.yaml`, `schema/fixtures/numbering/patterns.yaml` (I5 adds none), root `pyproject.toml` and `uv.lock`
(I5: an extra on the awp package, no new member), `tl_api/commands.py` splat lines, `openapi.json`, `tl_cli/main.py`, `tl_tui/{client,embedded,remote,app,commands}.py` and the fake,
`tl_mcp/identity.py`, pinned lists listed in `08-phase2-plan.md` 0.3, `tests/tools/proposable_exclusions.toml`. Rule: I4-A merges first and owns conflicts; I5 merges last
and regenerates, never hand-merges. I4-B (wave 4) edits `awp/checks_na.py` (labour check): I5 does not touch it. The pack shows scaffold tags as "not tracked
yet" until I4-B; T07a reads them by link type so I4-B needs no change.

## Deferred rows folded in, and not
Folded: hold-on-new-constraint rule (S4 B; closes P2-I2 Q1); the P2-I2 small follow-ups on the IWP log (T06c: counts, state-since, filters, backlog limit);
W3-5 waiver (S4 B). Not folded, left in `DEFERRED.md`: WBS node workflow and constraint opt-in (no demo clause needs it; progress rolls up through the existing WBS
without a node state); automatic constraint population (needs I4-B and purchase orders; I4-A raises its own shortage constraint); the six materials screens' technical
rows, `--for-line`, `@N` display (materials work, not I5); `tl awp worker` access word; the `-` versus em dash mark and `Rfi` label.
Added at close: web pages for the weekly cycle, look-ahead, progress, pack and closeout (and the foreman landing page) to the web increment row.

## Security rows (SR3, I5 part; owner-optional beyond these)
Scope when run: commit range `ec3314d..p2/i5` head, <= 450k tokens, findings `F<n> <HI|MD|LO> file:line`. S1 loader bounds (weights, size, NUL, ASCII digits) and
roles data; S2 earned arithmetic (Decimal, rounding, cap 100) and state-move words; S3 CSV export (formula cells, source prefix, no write to `cur_cost_*`);
S4 waiver (word, required reason, ledger, agents refused), hold rule (no loop, `by_module`), `expected_version`, look-ahead ids only for a viewer who cannot read some
blockers; S5 both CSV readers in the envelope (size, rows, hostile text), party scope; T07a template input (repository files only, autoescape, QR base URL from a setting,
hidden records omitted); T11a routes (word before read) and the five-reader walk; T11c agent tools and the row-or-exclusion test.

## Process lessons applied (P2-I2 STATE)
Gates name test files or one package (L-P2-I1-2); dialect-neutral tests; provided tests pass ruff; pinned lists written as the union; a check name used twice is an error;
readiness is read by ids only (D20, D32); hidden-SQL cost: a read that filters per viewer is batched, never one statement per row (T06a3); agent grants for core words stay deferred, so
agent tools are the awp ones only (D37); product gaps in the demo project are fixed at the generator, not in the demo; one text module, then one screen; no new F-keys.

## Risks and escalation
- Weights schema: the loader refuses a sum other than 100 per step list; a fractional weight design is out (integers only).
- Hold rule: raising a constraint through the frozen `raise_constraint` must not call the hold in the same unit of work (loop); S4 B runs it from the follower worker (D39 of I2).
- P2-INT not on the trunk: tags and intent plumbing wait; S1 leaves `at` untagged and reports it if the annotation is absent; the orchestrator confirms P2-INT C2 before I5 merges.
- `reportlab`/`segno` licence checks failing `tests/tools/test_check_licences.py`: S1 escalates.
- Escalate: a frozen contract change; an access word the table lacks; a piece failing twice.

## Plan check
(left empty; the orchestrator pastes the planner-tier findings here and round 2 answers each)
