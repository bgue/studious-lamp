# P2-I5 — Weekly cycle, rules of credit, progress, IWP pack, closeout (module M3, part 3), CLI and TUI only

Status: r5 (2026-11-09): trimmed scope, both plan checks answered at the end (all accepted); every remaining ticket is written (r5) and the next slice only dispatches (waves below). 4 live pieces (S1-S4b; S5 is roadmap 3c), 20 live tickets (T16 replaces the S6 piece; T17 is the tour, owner 2026-11-09). Nothing is dispatched until P2-INT C2 is on
the trunk (F4); the S1 and S2 specs are written. Plan sources: `docs/build-spec/08-phase2-plan.md` "Increment 5" (re-cut here), `specs/phase2-wave-plan.md`
(wave 3 row), `module-designs/field-work-packaging.md`, `roadmap-2026-11-07.md` (P2-Q1, P2-Q11, P2-Q13, W3-5, W3-6, W3-7), `DEFERRED.md` (wave 3 rows),
ADR-0024 to ADR-0027. Board: `STATE.md`.
Branch `p2/i5` from `p2/wave2-close` @ec3314d (P2-I2 merged); the trunk with P2-INT merged in is merged into `p2/i5` before S1 starts. Worktree `/home/user/wt/p2-i5`.
Runs beside P2-I4-A (`p2/i4a`).

## Objective
After this increment a planner runs the weekly workface-planning cycle from the terminal: look-ahead of the next four weeks (activities, their IWPs, readiness),
constraint review (a person with `core.constraint.waive` may clear a check-raised constraint as waived, with a reason), release, foreman commitments, progress, PPC,
closeout (roadmap 3c, not here). A person who is foreman on any IWP lands on the IWP log filtered to mine (setting `tui.landing`). Earned progress comes from linked record states through
rules of credit held in a schema package chosen per project (`awp.rules_of_credit.set` = `package@version`), rolls up IWP to CWP to WBS node to cost code, and leaves as
a CSV per period. The IWP pack renders as HTML (QR codes as inline SVG when `segno` is installed). Two KPIs, PPC and % constraint-free, agree with the ledger on both adapters.
~~Closeout (actual hours, redlines slot, punch count, feedback), subcontract progress by CSV, the PDF pack and the other five KPI tiles~~: roadmap 3c.
Out of scope: closeout, subcontract CSV, PDF pack and five KPI tiles (roadmap 3c); every web page (deferred), welds and joints as records (Phase 3), permits, model slice, P6 write-back, automatic constraint population (needs I4-B), the WBS node
workflow, the GC's own rules-of-credit edition (data, later), the simulator `foreman` actor (I6).

## Owner answers applied (2026-11-08)
P2-Q1 C: sample rules of credit now as a section of the standards package `co.acme.awp@1.1.0` (F3, F12); the GC's edition later as another package or edition; a project adopts one
with the existing setting `awp.rules_of_credit.set`, which now holds `package@version` (empty = `co.acme.awp@1.1.0`). P2-Q11: HTML always; QR (segno SVG, inline) and PDF
(reportlab, T07c) when installed (both BSD), behind the flag `awp.pack.pdf` (S1; default off). P2-Q13 A: CWP `assigned_party` free text, interface constraints, CSV progress, no accounts.
W3-5: clearing a check-raised constraint needs the new core word `core.constraint.waive` (`controller`) and a reason (cap 300); the clear is shown as waived; no new event (F2; S4 B, a gated
core handler change). W3-6 (interpretation, D7; the owner will be told): there is no foreman account role and none is added; a user-scope setting `tui.landing` (`default`, `iwp_mine`, ...)
decides the landing, and the unset default resolves at sign-in to `iwp_mine` for a person who is foreman on any IWP (T06c2). W3-7: `awp.iwp.ready_lead_weeks` exists with default 4; the look-ahead
reads it. ADR-0025: P2-INT supplies the intent slot; no I5 handler reads intent. ADR-0026 F5: `at` of `IWP.Started`, `IWP.FieldCompleted`, `IWP.ProgressRecorded` carries `tl:valid_time` (S1).
ADR-0027: every new command is a `ProposableCommand` row or an entry in `tests/tools/proposable_exclusions.toml` with a reason (I4-A S2 owns file, test and baseline; I5 only appends, F5); approvals are
excluded; edits take `expected_version`.

## Demo clauses (`dev/demos/P2-I5.sh`, SQLite then Postgres; spec of record is `08-phase2-plan.md` I5 plus these)
1. The rules of credit in `co.acme.awp@1.1.0` publish through the schema registry (scope item steps 30/60/10); a package whose weights do not sum to 100 is refused by the package lint with a
   fixed message; a project adopts it with the setting; a plain user cannot publish a package.
2. A new XER snapshot is published; the look-ahead lists the next four weeks of activities with their IWPs and readiness (`n/m`), need-by dates from `awp.iwp.ready_lead_weeks`.
3. Constraint review: a check-raised constraint is cleared as waived by a person holding `core.constraint.waive` with a reason (a plain user is refused, the reason is required, the IWP
   shows it as waived with who and why); then release of the Ready IWPs (I2 sign-off).
4. A blocking constraint raised on an Issued IWP puts it On hold (the rule left open in P2-I2; Issued only; a replay changes nothing); foremen commit IWPs for the week (stale `expected_version` refused).
5. Progress: scope items move state, earned % per IWP follows the rules (S2 math rules), PPC (committed IWPs done / committed) follows the commitments and miss reasons; the rollup job writes earned
   quantities per CWP and WBS node; `tl awp export progress --period 2026-W45` writes the CSV by cost code (a cell starting with `=`, `+`, `-` or `@` is quoted).
6. The pack renders as HTML (cover, scope and steps, drawings with QR as inline SVG, MTO, safety and quality placeholders, permits and scaffold tags as "not tracked yet", sign-off sheet); with a
   library missing the command says so and writes what it can. ~~PDF with the flag: roadmap 3c (T07c).~~ No base-URL setting: links are relative paths and record keys. Stored in file slot `pack`.
7. ~~Closeout: roadmap 3c.~~ (was: actual-hours CSV read in the envelope (a bad file is refused whole), redlines slot, remaining punch, feedback; the KPIs (backlog weeks, % constraint-free, constraint aging, schedule
   compliance, PPC, earned vs burned, stale-pin issues) equal a ledger recount on both adapters.) Only PPC and % constraint-free are checked against a ledger recount (T09).
8. ~~A CWP assigned to a party records progress by CSV; an interface constraint shows in the report~~: roadmap 3c.
9. A person who is foreman on an IWP lands on the IWP log filtered to mine (`tui.landing` unset); `default` lands as before.
10. Agents: a proposal to record progress or commit an IWP is accepted by a person with the access; waived clears and weekly close are refused to agents (excluded, with reasons). Same reads
    over CLI, TUI, API and MCP; the five-reader walk passes.

## Pieces (builder, `kind: piece`, review full; specs `S<n>-<slug>.md`)
| Id | Piece | Spec | Depends | Sec |
|---|---|---|---|---|
| S1 | Schema and package (human gate, P2-Q10): `rules_of_credit` section of the schema-package content (package lint refuses weights not summing to 100), standards package `co.acme.awp@1.1.0` (sample rules, `MissReason`, `Interface` constraint type), `awp.WeeklyPlan` record and commitment rows, IWP progress table, closeout and CWP fields, awp file-slot fixtures for IWP and `IWPCloseout` (`pack`, `redlines`, `actuals`), events with valid-time tags, access words, settings `awp.pack.pdf`, `tui.landing` and a pattern change for `awp.rules_of_credit.set`, optional extra `pack`. No rules record class, no bespoke loader | written | wave 2 close, P2-INT C2 on trunk | schema, package lint, dependency |
| S2 | Engine and field lifecycle: `earned_fraction`, scope item moves, `RecordManualProgress`, `IWP.ProgressRecorded`, `StartIwpWork`, `CompleteIwpField`, edition from the adopted package, ADR-0027 rows, the four math rules (F9). Owns `module.py`, `names.py`, `AWP_COMMANDS` edits | written | S1 | quantities, state moves |
| S3 (r3 spec written) | Rollup and export (computed on read, no stored figure, D17): `awp.rollup` progress measure (IWP to CWP to WBS to cost code; `cost.CostCode` read, never written), `export_progress(conn, scope, period)` CSV, formula-safe cells, `tl awp export progress`. Pairs with S4 A | at C1 | S2 | money, export |
| S4 (r3: specs `S4a-weekly-plan.md`, `S4b-waive-hold.md`) | Weekly cycle and hold rule, two ordered phases. A (orchestrator APPROVALS only, F9): `OpenWeeklyPlan`, `CommitIwpToWeek`, `RecordWeekOutcome`, `CloseWeek` (PPC). B (human gate, owner approver: core constraint handler, `core.constraint.waive`, `awp.worker.run`; plus orchestrator APPROVALS): clearing a check-raised constraint needs `core.constraint.waive` and a reason, shown as waived (`tl_core/constraints/handlers.py`); the hold-on-new-constraint rule in the awp follower worker (Issued only, state re-checked on apply, idempotent on replay); the `tl awp worker` access word. A pairs with S3, B with S5 | at C1 | S2 | access words, guard, hold rule |
| ~~S5~~ **abn (roadmap 3c)** | Closeout and subcontract: `CloseOutIwp`, actual-hours reader and `RecordSubcontractProgress` CSV reader in `run_in_envelope`, `AssignCwpToParty`. APPROVALS by the orchestrator (parsers) | at C1 | S2 | parsers, envelope |
| S6 **replaced by T16** | Was a tests piece; now the Haiku ticket T16 (five-reader walk of every new route and tool, after T11c). Per-piece tests stay in each piece | - | - | - |
Policy kept: cross-piece tests deferred to T16; each piece leaves `dev/accept/P2-I5/<id>.py`; tour once at C4. Never more than one builder and one ticket workflow in a round (F7).

## Tickets (Haiku; `review` lite or full; specs written when their dependencies are in the tree)
| Id | Title | Rev | Depends |
|---|---|---|---|
| T01 | CLI `tl awp roc ls\|show\|set` over the adopted package content and the setting (provided test `provided/T01_test_awp_roc.py`; ready r4) | full | S1 |
| T03 | `look_ahead_view(conn, scope, snapshot, viewer)`: `look_ahead` joined with the IWPs linked to each activity, readiness counts and blocking counts through the viewer filter, ids only (stub `look_ahead_view.py` and provided test `provided/T03_test_look_ahead_view.py`; ready r4) | full | S2 |
| T04 | CLI `tl awp look-ahead --schedule` and `tl awp week open\|ls\|show\|commit\|outcome\|close\|ppc\|reasons` (print keys, L-P2-I3-3; `week ppc` is the T09 tile; provided test `provided/T04_test_awp_week.py`; ready r5) | full | T03, S4a, T09 |
| T04b | CLI for the S2 writes: `tl awp iwp start-work\|complete-field\|item-move\|step\|progress` (provided test `provided/T04b_test_awp_progress.py`; ready r4, after T01) | full | S2 |
| T05 **abn (roadmap 3c)** | Interface-constraint helper: raise an `Interface` constraint on a CWP for a party (over the frozen `raise_constraint`) and its report | full | S5 |
| T06a | TUI weekly cycle steps 1 to 3 (look-ahead, constraint review with Waive, release with Sign off and Issue): `weekly_text.py` (stub and provided test `provided/T06a_test_weekly_text.py` in the tree), `widgets/weekly_screen.py`, palette entry `week` | full | T11b, S4b, T09 |
| T06b | TUI weekly cycle steps 4 and 5: commitments, progress and PPC; adds the `actions.RULES` rows for `StartIwpWork` and `CompleteIwpField` (Q-o2, here by name; closeout step deferred, roadmap 3c) | full | T06a |
| T06c1 | IWP log extras: Ready and Blocking counts and Since (`IWP_COUNT_COLUMNS`; the web page keeps `IWP_COLUMNS`), discipline and text filters in the summary, backlog read past 200, `mine=` constructor flag (the `m` key already exists) | full | T11b |
| T06c2 | Landing: setting `tui.landing` read at sign-in, unset default `iwp_mine` for a person who is foreman on any IWP (one read over IWP foreman fields) | full | T06c1 |
| T07a | Pack data assembly over committed read views, HTML by `string.Template` + `html.escape` (no Jinja2, D26), segno QR as inline SVG when installed; `tl awp iwp pack [--attach]`; slot `pack`; template is a repository file | full | S2 |
| T07b | Pack template: cover, scope and steps, drawings, MTO, safety, ITP, permits, scaffold placeholders, sign-off sheet; snapshot test (provided test `provided/T07b_test_pack_template.py`, written when T07a merges) | lite | T07a |
| T07c **abn (roadmap 3c)** | Pack PDF with reportlab behind `awp.pack.pdf`; says so when the library or the flag is missing | full | T07b |
| T08 **abn (roadmap 3c)** | Closeout reads, closeout routes, `redlines` slot view, `tl awp closeout show\|do` over S5 | full | S5 |
| T09 | KPI functions and tiles (two: PPC pooled over the last 4 closed weeks, and % constraint-free; five deferred to roadmap 3c) with a ledger-recount test (provided test `provided/T09_test_kpis.py`, stub `kpis.py` in the tree); `tl awp report kpi_ppc\|kpi_constraint_free` | lite | S4a |
| T10 **abn (roadmap 3c)** | Subcontract reads, routes and `tl awp subcontract assign\|import\|ls` over S5 | full | S5, T05 |
| T11a1 | API read routes: IWP progress, roll-up, KPIs, IWP counts (Ready, blocking, state-since) and the record hash (D30), embedded and remote | full | S2, S3, T09 |
| T11a2 | API read routes: weekly plans, miss reasons, look-ahead | full | S4a, T03, T11a1 (file order) |
| T11b | `ApiClient`, `ClientInterface`, embedded client and fake: eleven reads and the two command doors `awp_command` and `constraint_command` (D28) | full | T11a1, T11a2, S4b |
| T11c | MCP read tools: `list_weekly_plans`, `get_weekly_plan`, `get_iwp_progress`, `get_progress_rollup`, `list_kpis` (look-ahead off MCP, D29); closed-list lines | full | T09 |
| T12 | `dev/demos/P2-I5.sh`, clauses 1-6, 9, 10 (7, 8 roadmap 3c; 6 without PDF; 5 as D17; 10 without close-out), both adapters | full | T06c2, T06b, T07b, T09, T16, S4b |
| T17 | Highlights tour steps: Activity, Insights, intent, IWP landing and the weekly loop, the pack (runs last, owner 2026-11-09) | full | T12, T06c2, T06b, T07a, T09 |
| T13 | Docs: awp README and AGENTS rows, runbooks `weekly-cycle`, `rules-of-credit`, `iwp-pack`, reference page | lite | T12 |
| T15 | Registrations as one ticket only if glue passes 50 lines: `add_typer`, `MCP_ACTIONS`, palette | full | S4, T11c |
| T16 | Five-reader walk (CLI, TUI, API, MCP, embedded) of every new route and tool: a test that walks as the five kinds of reader (AGENTS.md); replaces the S6 tests piece | full | T11c, T11b, T04, S4b |
Trimmed r3 (owner 2026-11-09, STATE D-o1): 17 live tickets (T01, T03, T04, T06a, T06b, T06c1, T06c2, T07a, T07b, T09, T11a1, T11a2, T11b, T11c, T12, T13, T15) and S6; T05, T07c, T08, T10 and piece S5 are `abn` with "roadmap 3c". Demo clauses 7 and 8 and the PDF half of 6 move to 3c; clause 5's "rollup job writes" is read as "the rollup reads" (D17). T16 replaces S6 (r4, F8). T14 (simulator `ForemanDesk`, actor `foreman`) goes to I6, where the roster is registered (F12). Every screen ticket needs its text module in the tree first (L-P2-WEB1-1).

## Next slice: waves (r5; rounds between waves are supervisor rounds that check reports and write what the next wave needs)
Each wave is one ticket workflow of 2-3 tickets with disjoint files; no builder is left. Shared one-line files (`awp.py`, `app.py`, `openapi.json`) are touched by one ticket per wave.
- R-A: T09, T07a (kpis.py + awp_report.py; pack.py + awp_pack.py).
- R-B: T11a1, T04, T11c (routes + app.py + openapi; awp_week.py; mcp). Between A and B the supervisor writes `provided/T07b_test_pack_template.py`.
- R-C: T11a2, T07b.   R-D: T11b.   R-E: T06a, T16 (screens; tests only).   R-F: T06b, T06c1.   R-G: T06c2.   R-H: T12.   R-I: T13, T17.   T15 only if glue passes 50 lines.

## Order of work and checkpoints
Trunk with P2-INT C2 merged in (F4) -> S1 -> S2 -> S4a (running) -> S4b -> S3 (after S4a merges; F4, F6) with T01, T03 -> T04, T04b, T11a1, T11a2 -> T11b -> T06a, T06c1, T07a, T09, T11c -> T06b, T06c2, T07b -> T16 -> T12 -> T13. Struck (roadmap 3c): S5, T05, T07c, T08, T10.
Each round runs at most one builder and one ticket workflow; the pairs say which piece shares a round with which.
- C1: S1, S2 merged. C2: S3, S4a, S4b, T11a1, T11a2, T11b merged and registrations done.
- C3: every ticket merged or abandoned, T16 merged. C4: per-folder gate on touched packages (`uv sync --extra pack` before the licence check, F11), demo green on both adapters, tour once, SR3 (I5 rows) closed.
Merge order: after I4-A's merge; S1 to S4b, then T11a1; this increment regenerates pinned lists and `openapi.json` last.

## Seams with P2-I4-A (parallel rounds; no overlapping paths)
I4-A owns `schema/modules/requisitions/`, `packages/tl-modules/requisitions/`, `tl_cli/{req,wo}*.py`, its text, widget and MCP files. I5 owns only `schema/modules/awp/`, `packages/tl-modules/awp/`, the new awp
CLI, text and widget files, `schema/fixtures/standards/co.acme.awp@1.1.0.yaml`, `schema/fixtures/files/awp-*.yaml`, `packages/tl-schema/src/tl_schema/{packages,lint}.py` (rules section, S1) and
`packages/tl-core/src/tl_core/constraints/` (waive word, S4 B). Shared files, edited by adding lines only, each side re-runs `just gen`: `schema/settings/{access-words,module-roles,platform}.yaml`,
`schema/fixtures/numbering/patterns.yaml` (I5 adds none), root `pyproject.toml` and `uv.lock` (I5: an extra on the awp package, no new member), `tl_api/commands.py` splat lines, `openapi.json`,
`tl_cli/main.py`, `tl_tui/{client,embedded,remote,app,commands}.py` and the fake, `tl_mcp/identity.py`, pinned lists in `08-phase2-plan.md` 0.3, `tests/tools/proposable_exclusions.toml` (I4-A S2 owns file,
test and baseline; I5 appends). Rule: I4-A merges first and owns conflicts; I5 merges last and regenerates, never hand-merges. I4-B (wave 4) edits `awp/checks_na.py`: I5 does not. The pack shows scaffold
tags as "not tracked yet" until I4-B; T07a reads them by link type so I4-B needs no change.

## Deferred rows folded in, and not
Folded: hold-on-new-constraint rule (S4 B; closes P2-I2 Q1); the P2-I2 small follow-ups on the IWP log (T06c1); the W3-5 waive word (S4 B); the `tl awp worker` access word (S4 B, F10).
Not folded, left in `DEFERRED.md`: WBS node workflow and constraint opt-in (no demo clause needs it; progress rolls up through the existing WBS); automatic constraint population (needs I4-B and
purchase orders; I4-A raises its own shortage constraint); the six materials screens' technical rows, `--for-line`, `@N` display (materials work); the `-` versus em dash mark and `Rfi` label.
Added at close: web pages for the weekly cycle, look-ahead, progress, pack and closeout, the landing setting, to the web increment row; the simulator `foreman` actor to I6.

## Security rows (SR3, I5 part; owner-optional beyond these; one range)
Scope when run: commit range `ec3314d..p2/i5` head, <= 450k tokens, findings `F<n> <HI|MD|LO> file:line`. S1 package lint bounds (weights, size, NUL, ASCII digits), settings pattern, new dependency; S2 earned
arithmetic (Decimal, rounding, cap 100), viewer filter on read, state-move words; S3 CSV export (formula cells, source prefix, no write to `cur_cost_*`); S4a week words (`awp.week.plan|commit|close`, stale `expected_version`, agent proposals); S4 B waive word on clearing a check-raised
constraint (word, required reason, ledger, agents refused), hold rule (Issued only, no loop, idempotent, `by_module`), `expected_version`, look-ahead ids only for a viewer who cannot read some blockers;
T07a template input (repository files only, autoescape, QR payload a relative path or key, hidden records omitted); T11a1 and
T11a2 routes (word before read; the hash route, D30) and the five-reader walk; T06a release actions (sign-off with the read hash); T11c agent tools and the row-or-exclusion test.

## Process lessons applied (P2-I2 STATE)
Gates name test files or one package (L-P2-I1-2); dialect-neutral tests; provided tests pass ruff; pinned lists written as the union; a check name used twice is an error; readiness is read by ids only
(D20, D32); a read that filters per viewer is batched, never one statement per row (T06a3); agent grants for core words stay deferred, so agent tools are the awp ones only (D37); product gaps in the demo
project are fixed at the generator; one text module, then one screen; no new F-keys.

## Risks and escalation
- Weights: the package lint refuses a sum other than 100 per entry; integers only. If the package content model is closed to new sections S1 escalates with the shape that works.
- Hold rule: raising a constraint through the frozen `raise_constraint` must not call the hold in the same unit of work (loop); S4 B runs it from the follower worker (D39 of I2), re-reads the state when it applies and does nothing on replay.
- P2-INT C2 is a start condition for S1 (F4); there is no untagged fallback.
- `reportlab` or `segno` licence checks failing `tests/tools/test_check_licences.py`: S1 escalates.
- Escalate: a frozen contract change; an access word the table lacks; a piece failing twice.

## r5 decisions (2026-11-09; STATE D26-D31)
D26 pack without Jinja2 (not a dependency of the awp package; `string.Template` plus one escape helper). D27 `week ppc` and the PPC tile are one definition (pooled over the last 4 closed weeks). D28 the TUI writes through two client doors, `awp_command` and `constraint_command` (T11b). D29 look-ahead is not an MCP tool this increment. D30 a route and client read for the IWP record hash (the remote release step needs what `tl awp iwp hash` prints; handlers stay the gate). D31 the web page keeps `IWP_COLUMNS`; the TUI log has `IWP_COUNT_COLUMNS`.

## Plan check (2026-11-08) and answers
Planner-tier check F1-F12, all accepted by the orchestrator; each answer is the change made in round 2.
- F1 no foreman account role exists: accepted. W3-6 is the user-scope setting `tui.landing`; unset resolves to `iwp_mine` for a person who is foreman on any IWP (T06c2); no auth change (D7, owner to be told).
- F2 WaiveConstraint and Constraint.Waived dropped: accepted. Clearing a check-raised constraint needs `core.constraint.waive` (`controller`), shown as waived; reason cap 300 everywhere (S1 had 500); the core handler change is S4 B, gated.
- F3 rules of credit as schemareg package content: accepted. The `RulesOfCredit` class and the bespoke loader are gone; the setting holds `package@version` (S1 changes its pattern).
- F4 hold S1 until P2-INT C2 is on the trunk: accepted; trunk merged first; the untagged fallback is dropped.
- F5 proposable exclusions file: accepted; I4-A S2 owns file, test and baseline; I5 appends only.
- F6 file slots: accepted; S1 adds `schema/fixtures/files/awp-iwp.yaml` and `awp-iwp-closeout.yaml` (`pack`, `redlines`, `actuals`).
- F7 pairing: accepted; S3 with S4 A, S5 with S4 B, T11a after S2 and S4 A, closeout and subcontract routes in T08 and T10; one builder plus one workflow per round.
- F8 tiers: accepted; `look_ahead_view` is T03 and the interface helper T05 (Haiku); S4 is weekly commands plus the hold rule (6 pieces); T11a and T06c each split in two.
- F9 math rules: accepted, written in S2 and noted for S3 and S4.
- F10 hold rule: accepted; Issued only, state re-checked on apply, idempotent on replay; the `tl awp worker` access word folded into S4 B.
- F11 approvers: accepted; S4 and S5 get orchestrator APPROVALS, S4 also a human gate; the S1 gate runs `uv sync --extra pack` before the licence check; one SR3 range.
- F12 trims: accepted; `api.public_base_url` dropped, QR is segno SVG inside the HTML, PDF is T07c behind the flag, T14 deferred to I6, the sample package is `co.acme.awp@1.1.0`.

## Plan check (2026-11-09, trimmed set)
4 PLANCHK docs/tickets/P2-I5/README.md, answers by the orchestrator:
- F1 HI accepted: S4b reads `handlers/signoff.py:207` `handle_hold_iwp` (extract only); fix Context and Allowed paths.
- F2 HI accepted: S4b allows `openapi.json` and `tl-api/tests/test_auth_review.py` (AGENT_MAY_NOT) as pins; S4b added to the Depends of T06a, T11b, T12.
- F3 HI accepted: add `week open` to T04; new Haiku ticket T04b for the CLI of the S2 writes (progress, scope-item moves, StartIwpWork, CompleteIwpField).
- F4 MD accepted in effect: S4a (already dispatched) keeps `progress_world.py`; S3 runs after S4a merges, so there is no parallel edit; `openapi.json` regenerated at merge.
- F5 MD accepted: T01 and T03 can run as a ticket workflow now; drop S3 from T09's Depends.
- F6 MD accepted: order S4a (running), then S4b, then S3; at most 3 heavy agents.
- F7 MD accepted: strike or mark "roadmap 3c" every cut item in the Objective, demo clauses 7-8, the order of work, SR3's S5 row and S6's CSV-reader tests; T12 clause 10 drops close-out.
- F8 MD accepted: S6 becomes a Haiku five-reader-walk ticket after T11c.
- F9 MD accepted: S4a is orchestrator APPROVALS only; S4b's human gate (core constraint handler, `core.constraint.waive`, `awp.worker.run`) recorded in STATE with the owner as approver; SR3 Sec list drops S5 and adds the S4a week words.
- F10 LO accepted: S3 pins name `test_cli_awp.py`, `test_reports.py`, `docs/reference/awp.md`.
- F11 MD accepted for S4b (drop `S1.md`, cite `require_word` at `tl_cli/constraint_read.py:52`); S4a was dispatched before the check and keeps its context.
- F12 LO accepted: T03, T07b and T09 name their provided tests under `provided/`; the `actions.RULES` rows (Q-o2) go to T06b by name.

All twelve answers of 2026-11-09 are applied in r4 (STATE D22): F1, F2, F11 in `S4b-waive-hold.md`; F3 in T04 and the new T04b; F5 in T01, T03, T09; F7 in the Objective, clauses 7, 8, 10, the order of work and SR3; F8 as T16; F9 in STATE gate rows; F10 in `S3-rollup-export.md`; F12 provided tests under `provided/` (T01, T03, T04b written; T07b, T09 and the T04 test are written when their dependencies merge) and the `actions.RULES` rows in T06b.
