# P2-W0 STATE  r=5 base=0c2c99d C=C2 ck=0 gate=n/a wt=/home/user/wt/p2-w0
Read first: docs/build-spec/specs/wave0.md (plan, "Plan check" at the end), README.md here. Branch p2/w0 (trunk claude/wizardly-allen-m2v96s @0a69e0a). Builders and tickets branch from p2/w0 HEAD (the r5 state commit).
## BOARD
RM-S1 p mrg f 55931f7 module roles table, grants, resolver, company grants; C1
W0-B1 p mrg f 4824bf6 readiness, reserved, 11 keys, access words; C1
A1 t mrg l 8dbe138 dev/state.sh; justfile recipe added r3
A2 t mrg l 484337c dev/review-pack.sh; justfile recipe added r3
A3 t mrg l 266e29a dev/relay-lint; justfile recipe added r2
RM-S2 p mrg f 2ee1c0e API-side module-role gates, D1-D3 orch; APPROVALS 9563763
W0-B2 p mrg f bfd4629 load/publish targets by entry point
OC-S1 p mrg f fc09ce7 offline annotation, tables; APPROVALS b203322
RM-S3 p mrg f bdff740 admin surfaces; agent pin, keymap m widened; 26 PASS; APPROVALS 672d87d
RM-S4 p mrg f 97f3436 gate sweep; 3 attempts; ADR-0016 fix class; gate_sweep 0 ungated; APPROVALS ac9c0d2
OC-S2 p mrg f 41353f7 capture hook, load checks, node kind; 43 PASS
OC-T1 t mrg f 1de9428 T04 GET /record-types + record_types(); merge 5d0442c
OC-T2 t mrg f b2b3f2d T05 Offline class row, technical mode; merge 65cc353
OC-T3 t mrg l c6dbfd9 T06 scaffold tl:offline none + expected pin
RM-S3L t mrg l d8cd917 T07 four lows F1-F4
OC-T4 t mrg l 2dddcb7 T08 InboundDelivery none; orch regen models.py 1eedbeb; APPROVALS 6d7f35f
TA p stg f - S9-tests-roles.md; RM-S1..S4 tests, T07 tests, pins, 6 snapshots, Q6, Q7
TB p stg f - S10-tests-core.md; W0-B1/B2, OC-S1/S2, T04-T06/T08, A1-A3 tests, Q4
DOC-1 t stg l - T09-docs-roles-words.md; runbook section, access-words reference
DOC-2 t stg l - T10-docs-targets-offline.md; legacy-load, tl-core README, module-designs §3
DEMO t stg l - T11-demo-p2-w0.md; demo 11 clauses + tour rows (F8)
## DEC
D1 2026-10-30 plan check wave0 go-with-fixes F1-F10 all accepted; applied in wave0.md "Plan check" (st: 4ce6874)
D2 2026-10-30 owner: tests and tours deferred to one end run; pieces leave acceptance scripts dev/accept/P2-W0/<id>.py; no pytest in piece acceptance
D3 2026-10-30 piece acceptance = just check + dev/accept script + named smoke; pytest/gate lines in wave0 §6 run at the end (TA/TB/C4)
D4 2026-10-30 file names: S1 RM-S1, S2 W0-B1, S3 RM-S2, S4 W0-B2, S5 OC-S1, T01..T03 = A1..A3; S6 RM-S3, S7 RM-S4, S8 OC-S2
D5 2026-10-30 A1-A3 tests live in tests/tools/ (F5), written not run; A1 WT_ROOT env (default /home/user/wt); A3 item id class allows '-'
D6 2026-10-30 F9 applied to m3-wbs-cwp.md (tl:offline_reason dropped); OC split into OC-S1/OC-S2 (F3)
D7 2026-10-30 RM-S1 does not import access_words; command_index returns words as declared; RM-S2 normalised fine->table in command_index() (done)
D8 2026-10-30 company grants: project pattern ^(company|project:..)$, needs ModuleSpec.company_roles, else NoCompanyRolesError 422 no_company_roles
D9 2026-10-31 orch: A1 default base `main` (= trunk), total <= 40 lines; A2 60-line limit, problem lines never hidden (merged)
D10 2026-10-31 orch: schema merges approved under P2-Q10, logged APPROVALS; owner policy unchanged: tests/tours at increment end
D11 2026-10-31 RM-S2 owns every API-side seam + require_command_access; CLI/embedded gates are RM-S4's (spec S7)
D12 2026-10-31 test files for RM-S2, W0-B2, OC-S1 named in each spec, written by TA/TB at the end run; pieces report guard sites (file:line)
D13 2026-10-31 W0-B1 types.py wraps one line (ruff format); whitespace only, accepted
D14 2026-10-31 orch: proposal accept = AND (account role + module word); RM-S4 wires the opt-in holder at in-process callers; sim/MCP go through the API
D15 2026-10-31 RM-S2 orch rows: D1 RoleAuthorizer needs controller word; D2 dev-ledger user words live in core holder_for_actor; D3 derive document_controller -> user in every module
D16 2026-10-31 r3 glue: justfile recipes `state` and `review-pack`; fake tl-tui/tests/fakes_admin.py allowed in RM-S3
D17 2026-10-31 OC-S2: extension class read from type.yaml annotation `tl:offline` (default none); offline_class IO-free; extype test in tests/extypes/
D18 2026-10-31 T04: RecordTypeRow + record_type_rows() in tl_core/offline.py; action reference.read; extension types not listed
D19 2026-10-31 T05: offline row added in details_for + generic.py, technical mode, panel=False
D20 2026-10-31 Q5 decided by orch: InboundDelivery offline class none (T08, schema, orch approves under P2-Q10)
D21 2026-10-31 r4 file names T04..T08 = OC-T1, OC-T2, OC-T3, RM-S3L, OC-T4; relay ids T04..T08; T06 updates expected weld_inspection.yaml (rule 12)
D22 2026-10-31 r5 names: S9=TA, S10=TB, T09/T10=DOC split in two (one ticket would read >6 files), T11=DEMO. Report path = file id (S9.md, S10.md, T09.md..T11.md): ends the id/report mismatch seen in r4
D23 2026-10-31 r5 TA/TB run only own new/changed files (targeted gate, one part at a time) + named run-once files; orch runs the whole suite once after. Snapshots regenerated only when a merged ticket explains the diff, each listed
D24 2026-10-31 r5 every ticket says: no discussion of the commit trailer in the report; no model names in committed files
D25 2026-10-31 RESERVED_NAMESPACES already holds awp, materials, scaffold (a13daf6); TB pins it in tests/extypes/test_names_and_lock.py
D26 2026-10-31 T07 text `1 of 1 modules` kept as specified (no pluralisation change); T04 reader of /record-types is a plain `user` (no viewer account role exists)
## SEC
Not run (owner: only if asked). Rows recorded: RM-S1 Y, RM-S2 Y, RM-S3 Y, RM-S4 Y, W0-B1 Y, W0-B2 Y. Range 0a69e0a..P2-W0 head.
## OPEN
Q1 orchestrator: ADR-0022, Phase 2 decisions ADR, accept ADR-0021 (contracts §1/§7 frozen per W0-B1 merge) needs orch raised wave0 §9
Q2 owner/orch confirm awp.release.signoff_roles default [superuser] (W0-B1 wrote it as proposed) needs owner raised wave0 §9
Q4 TB reviews and regenerates the settings list snapshot only if the diff is the 11 keys needs builder(TB) raised W0-B1 (in S10)
Q6 TA reads RM-S2 unaudited tests (tl-sim, tests/auth/test_authorizer_and_seed.py) and predicted pins needs builder(TA) raised RM-S2 (in S9)
Q7 TA seeds real records in test_cli_corr.py::SITES and the test_cli_domains.py comm loop needs builder(TA) raised RM-S4 (in S9)
Q8 W0-B2: derived-document publish target choice needs schema change (target_kind Literal, names.TARGET_KINDS, mapping JSON schema); M4 needs it needs orch raised W0-B2
Q9 W0-B2: a company load run opened with --company cannot advance (extract..show take --project); follow-up in wave 1; docs/modules/legacy/README.md still says tags|documents needs orch raised W0-B2
## NEXT
1. Dispatch r5: one workflow, S9 (TA) and S10 (TB) in parallel (disjoint test files, snapshots split: TA admin, TB settings); then T09, T10, T11 (lite) in a second workflow. Branches p2/w0-s9-tests-roles, p2/w0-s10-tests-core, p2/w0-t09-docs-roles-words, p2/w0-t10-docs-targets-offline, p2/w0-t11-demo.
2. Merge order on P: S9, S10, T09, T10, T11. Retry any 2s/gr first. Source defects found by tests come back as Blocked with a test id: next round re-specs a Haiku ticket or builder fix.
3. C3 after merge. C4 by orchestrator: just check, whole just gate once, gate-pg on tests/auth + packages/tl-core/tests/auth, P1-I3/P1-I8/P2-W0 demos on both adapters, just tour 1 once (tour rows from T11), increment report.
4. Orchestrator at C4: Q1, Q2, Q8, Q9; APPROVALS lines for the schema merges are logged through T08.
## REFS
Specs wave0.md, roles-mvp.md (§6 RM-S3, §5/§11 RM-S4), offline-classes.md (§5, §7), phase2-wave-plan.md, OWNER-DECISIONS-2026-10-30.md. Reports docs/reports/P2-W0/{RM-S1,RM-S2,RM-S3,RM-S3-L,RM-S4,W0-B1,W0-B2,OC-S1,OC-S2,OC-T3,OC-T4,T04,T05,A1-A3}.md (guard sites for mutants). Old-text pins: T05 test_details_registry.py:43 (S10); T07 none (S9 pins the new text); T08 none found (S10 pins OFFLINE_STREAMS); RM-S4 gates/SITES/comm loop/xercli GATE (S9). Fixtures docs/tickets/P2-W0/provided/relay-{ok,bad}.txt. Acceptance scripts dev/accept/P2-W0/.
## TRAPS
Worktree /home/user/wt/p2-w0 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: run it in the background. `DisplayMode()` takes no args (set .technical). A route reading project from the body is 422 before 403 for an empty body. Module record from Record.Created alone is hidden (ADR-0016) except to system_view(). Tagging a core class changes generated/models.py (list it in Allowed paths). packages/tl-core/tests/auth/ is the one new test dir (no __init__, importlib mode).
