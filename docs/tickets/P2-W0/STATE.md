# P2-W0 STATE  r=1 base=4ce6874 C=C0 ck=- gate=n/a wt=/home/user/wt/p2-w0
Read first: docs/build-spec/specs/wave0.md (plan, "Plan check" at the end), README.md here. Branch p2/w0 (trunk claude/wizardly-allen-m2v96s @0a69e0a). Builders branch from p2/w0 HEAD.
## BOARD
RM-S1 p disp f - S1-roles-grants.md; slot A; schema, orch gate
W0-B1 p disp f - S2-readiness-words-keys.md; slot B; settings, orch gate
A1 t disp l - T01-state-sh.md; slot C workflow
A2 t disp l - T02-review-pack.md; slot C workflow
A3 t disp l - T03-relay-lint.md; slot C workflow
RM-S2 p todo f - r2 slot A; needs RM-S1, W0-B1 merged
W0-B2 p todo f - r2 slot B; not tl_mod_legacy/module.py (F4)
OC-S1 p todo f - r2 slot C; schema annotation + generator, no RM dep (F3)
RM-S3 p todo f - r3 slot C (roles admin surfaces + module roles log)
RM-S4 p todo f - r3 slot A; codemod dev/tools/gate_sweep.py + AST pin
OC-S2 p todo f - r3 slot B; needs OC-S1, RM-S2
OC-T1 t todo f - r4; OC-T2 after T1; OC-T3 lite, one workflow
TA p todo f - r4-5 tests for RM-S1..S4 + access words (Sonnet)
TB p todo f - r5 tests for W0-B1, W0-B2, OC, reserved, keys
DOC t todo l - r5 with DEMO, one workflow
DEMO t todo l - r5; also dev/tour/phase1.py rows (F8)
## DEC
D1 2026-10-30 plan check wave0 go-with-fixes F1-F10 all accepted; applied in wave0.md "Plan check" (st: 4ce6874)
D2 2026-10-30 owner: tests and tours deferred to one end run; pieces leave acceptance scripts dev/accept/P2-W0/<id>.py; no pytest in piece acceptance
D3 2026-10-30 piece acceptance = just check + dev/accept script + named smoke; pytest/gate lines in wave0 §6 run at the end (TA/TB/C4)
D4 2026-10-30 file names: S1 = RM-S1, S2 = W0-B1, T01..T03 = A1..A3; later S<n> follow creation order, README table maps plan ids
D5 2026-10-30 A1-A3 tests live in tests/tools/ (F5), written not run; A1 WT_ROOT env (default /home/user/wt); A3 item id class allows '-'
D6 2026-10-30 F9 applied to m3-wbs-cwp.md (tl:offline_reason dropped); OC split into OC-S1/OC-S2 (F3)
D7 2026-10-30 RM-S1 must not import access_words (W0-B1 parallel); command_index returns words as declared, RM-S2 normalises fine->table (F1)
D8 2026-10-30 company grants: project pattern ^(company|project:..)$, needs ModuleSpec.company_roles, else NoCompanyRolesError 422 no_company_roles
## SEC
Not run (owner: only if asked). Rows recorded: RM-S1 Y, RM-S2 Y, RM-S3 Y, RM-S4 Y, W0-B1 Y, W0-B2 Y. Range 0a69e0a..P2-W0 head.
## OPEN
Q1 orchestrator before merge: freeze phase2-contracts-draft §1/§7 (W0-B1 copies §1 verbatim); ADR-0022, Phase 2 decisions ADR, accept ADR-0021 needs orch raised wave0 §9
Q2 owner/orch confirm awp.release.signoff_roles default [superuser] (W0-B1 writes it as proposed) needs owner raised wave0 §9
## NEXT
1. Merge RM-S1, W0-B1 (orch approves schema/settings, log APPROVALS), A1-A3 when P; record shas on the board.
2. Round 2 supervisor: write RM-S2 (S3), W0-B2 (S4), OC-S1 (S5) specs; RM-S2 paths per wave0 §6 incl. F7 pins; RM-S2 normalises fine words in command_index() and widens Access.
3. Add justfile recipes state, review-pack, relay-lint (glue) once A1-A3 merge; run relay-lint on this round's relay.
4. Retry any 2s/gr from round 1 before round-2 slots fill.
5. W0-B2 spec: targets via pyproject entry points only; acceptance `uv run tl load targets`, `just demo P1-I3`, `just demo P1-I8`.
6. Rounds 3-6: see wave0.md §7 (RM-S4 codemod, OC-S2, RM-S3, TA, OC-T1..T3, TB, DOC+DEMO, C4 by orchestrator).
## REFS
Specs wave0.md, roles-mvp.md (§2-4 for RM-S1, §9 paths), offline-classes.md (§7), phase2-wave-plan.md, OWNER-DECISIONS-2026-10-30.md. Contract draft docs/build-spec/phase2-contracts-draft.md §1, §7. Fixtures docs/tickets/P2-W0/provided/relay-{ok,bad}.txt. Acceptance scripts land in dev/accept/P2-W0/ (created by the pieces); reports in docs/reports/P2-W0/.
## TRAPS
Worktree /home/user/wt/p2-w0 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill.
