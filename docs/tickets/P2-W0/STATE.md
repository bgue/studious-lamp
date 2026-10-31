# P2-W0 STATE  r=2 base=eb69853 C=C1 ck=- gate=n/a wt=/home/user/wt/p2-w0
Read first: docs/build-spec/specs/wave0.md (plan, "Plan check" at the end), README.md here. Branch p2/w0 (trunk claude/wizardly-allen-m2v96s @0a69e0a). Builders branch from p2/w0 HEAD (after the r2 state commit).
## BOARD
RM-S1 p mrg f 55931f7 module roles table, grants, resolver, company grants; C1
W0-B1 p mrg f 4824bf6 readiness, reserved, 11 keys, access words; C1
A3 t mrg l 266e29a dev/relay-lint; justfile recipe added r2
A1 t esc l - output caps; implementer finishing; merge before r3
A2 t esc l - 60-line limit, problem lines never hidden; merge before r3
RM-S2 p disp f - S3-roles-wiring.md; slot A; owner/orch gate; Sec Y
W0-B2 p disp f - S4-load-publish-targets.md; slot B; not module.py
OC-S1 p disp f - S5-offline-annotation.md; slot C; schema, orch gate
RM-S3 p todo f - r3 slot C (roles admin surfaces + module roles log)
RM-S4 p todo f - r3 slot A; codemod dev/tools/gate_sweep.py + AST pin; needs RM-S2
OC-S2 p todo f - r3 slot B; needs OC-S1, RM-S2
OC-T1 t todo f - r4; OC-T2 after T1; OC-T3 lite, one workflow
TA p todo f - r4-5 tests for RM-S1..S4 + access words (Sonnet)
TB p todo f - r5 tests for W0-B1, W0-B2, OC, reserved, keys, A1-A3 tools
DOC t todo l - r5 with DEMO, one workflow
DEMO t todo l - r5; also dev/tour/phase1.py rows (F8)
## DEC
D1 2026-10-30 plan check wave0 go-with-fixes F1-F10 all accepted; applied in wave0.md "Plan check" (st: 4ce6874)
D2 2026-10-30 owner: tests and tours deferred to one end run; pieces leave acceptance scripts dev/accept/P2-W0/<id>.py; no pytest in piece acceptance
D3 2026-10-30 piece acceptance = just check + dev/accept script + named smoke; pytest/gate lines in wave0 §6 run at the end (TA/TB/C4)
D4 2026-10-30 file names: S1 RM-S1, S2 W0-B1, S3 RM-S2, S4 W0-B2, S5 OC-S1, T01..T03 = A1..A3; README table maps plan ids; later pieces continue S6..
D5 2026-10-30 A1-A3 tests live in tests/tools/ (F5), written not run; A1 WT_ROOT env (default /home/user/wt); A3 item id class allows '-'
D6 2026-10-30 F9 applied to m3-wbs-cwp.md (tl:offline_reason dropped); OC split into OC-S1/OC-S2 (F3)
D7 2026-10-30 RM-S1 does not import access_words; command_index returns words as declared; RM-S2 normalises fine->table in command_index() (spec S3 delta 1)
D8 2026-10-30 company grants: project pattern ^(company|project:..)$, needs ModuleSpec.company_roles, else NoCompanyRolesError 422 no_company_roles
D9 2026-10-31 orch: A1 default base `main` (= trunk), total <= 40 lines; A2 60-line limit, problem lines never hidden; both merge before r3
D10 2026-10-31 orch: schema merges (RM-S1, W0-B1) approved under P2-Q10, logged APPROVALS eb69853; owner policy unchanged: tests/tours at increment end; acceptance = just check + dev/accept/P2-W0/<id>.py + smoke
D11 2026-10-31 RM-S2 owns every API-side seam + one function require_command_access; CLI/embedded gates stay RM-S4; command_index passes admin/company/read/user/controller through, table_word() for the rest
D12 2026-10-31 test files for RM-S2, W0-B2, OC-S1 are named in each spec but written by TA/TB at the end run; pieces report guard sites (file:line)
D13 2026-10-31 W0-B1 types.py wraps one line (ruff format); deviation accepted as is (whitespace only, no config change)
## SEC
Not run (owner: only if asked). Rows recorded: RM-S1 Y, RM-S2 Y, RM-S3 Y, RM-S4 Y, W0-B1 Y, W0-B2 Y. Range 0a69e0a..P2-W0 head.
## OPEN
Q1 orchestrator: ADR-0022, Phase 2 decisions ADR, accept ADR-0021 (contracts §1/§7 frozen per W0-B1 merge) needs orch raised wave0 §9
Q2 owner/orch confirm awp.release.signoff_roles default [superuser] (W0-B1 wrote it as proposed) needs owner raised wave0 §9
Q3 orch follow-up outside wave 0: extypes.names.RESERVED_NAMESPACES lacks awp, materials, scaffold (W0-B1 learning) needs orch raised W0-B1
Q4 end run: TUI settings list snapshot (test_snapshots_settings) will differ after 11 keys; review --snapshot-update needs builder(TA) raised W0-B1
## NEXT
1. Merge RM-S2, W0-B2, OC-S1 when P (orch approves RM-S2 permission path and OC-S1 schema, log APPROVALS); record shas.
2. Merge A1, A2 when their implementers finish (D9); add justfile recipes state, review-pack (glue; relay-lint done).
3. Round 3 slots: RM-S4 (needs RM-S2; codemod dev/tools/gate_sweep.py), OC-S2 (needs OC-S1, RM-S2), RM-S3 (RM-S1 only). Retry any 2s/gr first.
4. RM-S3 spec = roles-mvp §9 S3 + T1 paths; RM-S4 = §9 S4; OC-S2 = offline-classes §7 S2 (offline_drafts lines after RM-S2's command_words).
5. Rounds 4-6 per wave0.md §7: OC-T1..T3 workflow, TA, TB (incl. tests/tools A1-A3 and the RM-S2/W0-B2/OC-S1 files named in S3/S4/S5), DOC+DEMO, C4 by orchestrator (also P1-I3/P1-I8 demos on both adapters).
## REFS
Specs wave0.md, roles-mvp.md (§2-4 RM-S1, §5 RM-S2, §9 paths), offline-classes.md (§7), phase2-wave-plan.md, OWNER-DECISIONS-2026-10-30.md. Reports docs/reports/P2-W0/{RM-S1,W0-B1,A3}.md (RM-S1 lists mutation guard sites). Fixtures docs/tickets/P2-W0/provided/relay-{ok,bad}.txt. Acceptance scripts dev/accept/P2-W0/.
## TRAPS
Worktree /home/user/wt/p2-w0 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. After pyproject entry-point edits (W0-B2) run uv sync once.
