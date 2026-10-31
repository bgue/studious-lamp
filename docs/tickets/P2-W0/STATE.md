# P2-W0 STATE  r=3 base=9563763 C=C1 ck=- gate=n/a wt=/home/user/wt/p2-w0
Read first: docs/build-spec/specs/wave0.md (plan, "Plan check" at the end), README.md here. Branch p2/w0 (trunk claude/wizardly-allen-m2v96s @0a69e0a). Builders branch from p2/w0 HEAD (the r3 state commit).
## BOARD
RM-S1 p mrg f 55931f7 module roles table, grants, resolver, company grants; C1
W0-B1 p mrg f 4824bf6 readiness, reserved, 11 keys, access words; C1
A1 t mrg l 8dbe138 dev/state.sh; justfile recipe added r3
A2 t mrg l 484337c dev/review-pack.sh; justfile recipe added r3
A3 t mrg l 266e29a dev/relay-lint; justfile recipe added r2
RM-S2 p mrg f 2ee1c0e API-side module-role gates, D1-D3 orch; APPROVALS 9563763
W0-B2 p mrg f bfd4629 load/publish targets by entry point
OC-S1 p mrg f fc09ce7 offline annotation, tables; APPROVALS b203322
RM-S3 p stg f - S6-roles-admin-surfaces.md; API/CLI/TUI grants + roles log; orch gate; Sec Y
RM-S4 p stg f - S7-gate-sweep-cli-embedded.md; codemod gate_sweep.py + AST pin; orch gate; Sec Y
OC-S2 p stg f - S8-offline-capture-hook.md; hook, load checks, node kind; no gate
OC-T1 t todo f - r4; OC-T2 after T1; OC-T3 lite, one workflow
TA p todo f - r4-5 tests for RM-S1..S4 + access words (Sonnet)
TB p todo f - r5 tests for W0-B1, W0-B2, OC, reserved, keys, A1-A3 tools
DOC t todo l - r5 with DEMO, one workflow
DEMO t todo l - r5; also dev/tour/phase1.py rows (F8)
## DEC
D1 2026-10-30 plan check wave0 go-with-fixes F1-F10 all accepted; applied in wave0.md "Plan check" (st: 4ce6874)
D2 2026-10-30 owner: tests and tours deferred to one end run; pieces leave acceptance scripts dev/accept/P2-W0/<id>.py; no pytest in piece acceptance
D3 2026-10-30 piece acceptance = just check + dev/accept script + named smoke; pytest/gate lines in wave0 §6 run at the end (TA/TB/C4)
D4 2026-10-30 file names: S1 RM-S1, S2 W0-B1, S3 RM-S2, S4 W0-B2, S5 OC-S1, T01..T03 = A1..A3; S6 RM-S3, S7 RM-S4, S8 OC-S2; later pieces continue S9..
D5 2026-10-30 A1-A3 tests live in tests/tools/ (F5), written not run; A1 WT_ROOT env (default /home/user/wt); A3 item id class allows '-'
D6 2026-10-30 F9 applied to m3-wbs-cwp.md (tl:offline_reason dropped); OC split into OC-S1/OC-S2 (F3)
D7 2026-10-30 RM-S1 does not import access_words; command_index returns words as declared; RM-S2 normalised fine->table in command_index() (done)
D8 2026-10-30 company grants: project pattern ^(company|project:..)$, needs ModuleSpec.company_roles, else NoCompanyRolesError 422 no_company_roles
D9 2026-10-31 orch: A1 default base `main` (= trunk), total <= 40 lines; A2 60-line limit, problem lines never hidden (merged)
D10 2026-10-31 orch: schema merges approved under P2-Q10, logged APPROVALS; owner policy unchanged: tests/tours at increment end; acceptance = just check + dev/accept/P2-W0/<id>.py + smoke
D11 2026-10-31 RM-S2 owns every API-side seam + require_command_access; CLI/embedded gates are RM-S4's (spec S7)
D12 2026-10-31 test files for RM-S2, W0-B2, OC-S1 named in each spec, written by TA/TB at the end run; pieces report guard sites (file:line)
D13 2026-10-31 W0-B1 types.py wraps one line (ruff format); whitespace only, accepted
D14 2026-10-31 orch: proposal accept = AND (account role + module word) kept; RM-S2 deviation 4 closed; RM-S4 wires the opt-in holder at in-process callers (CLI proposal.py, embedded allowed_actions); sim/MCP go through the API
D15 2026-10-31 RM-S2 orch rows: D1 RoleAuthorizer needs controller word (derived or granted); D2 dev-ledger user words live in core holder_for_actor, so RM-S4 adds NO CLI-side dev fallback; D3 derive row document_controller -> user in every module
D16 2026-10-31 r3 glue: justfile recipes `state` and `review-pack` added (A1/A2 merged); fake tl-tui/tests/fakes_admin.py is allowed in RM-S3 (a fake, not a test)
D17 2026-10-31 OC-S2: extension class read from type.yaml key `offline` (default none); offline_class stays IO-free, optional `conn` only as disclosed deviation; its extype test goes to tests/extypes/ (the spec's packages/tl-core/tests/extypes does not exist)
## SEC
Not run (owner: only if asked). Rows recorded: RM-S1 Y, RM-S2 Y, RM-S3 Y, RM-S4 Y, W0-B1 Y, W0-B2 Y. Range 0a69e0a..P2-W0 head.
## OPEN
Q1 orchestrator: ADR-0022, Phase 2 decisions ADR, accept ADR-0021 (contracts §1/§7 frozen per W0-B1 merge) needs orch raised wave0 §9
Q2 owner/orch confirm awp.release.signoff_roles default [superuser] (W0-B1 wrote it as proposed) needs owner raised wave0 §9
Q4 end run: TUI settings snapshot (test_snapshots_settings) differs after 11 keys; accounts-screen/admin snapshots differ after RM-S3; review --snapshot-update needs builder(TA) raised W0-B1
Q5 orch: core.InboundDelivery stream has no tl:stream_type/class (OC-S1 open question); follow-up, stream_class() answers none meanwhile needs orch raised OC-S1
Q6 end run: RM-S2 unaudited tests (tl-sim, tests/auth/test_authorizer_and_seed.py) and its predicted extra pins may break; TA reads them needs builder(TA) raised RM-S2
## NEXT
1. r3 dispatch (one workflow of 3, slots A/B/C): RM-S3 (S6), RM-S4 (S7), OC-S2 (S8). Branches p2/w0-rm-s3, p2/w0-rm-s4, p2/w0-oc-s2, all from p2/w0 HEAD.
2. Merge order on P: OC-S2, RM-S3, RM-S4 (RM-S3 and RM-S4 both edit embedded.py in different hunks; RM-S3 and OC-S2 both add rows to tl_api/errors.py; regenerate openapi.json by python -m tl_api.openapi on conflict). Orch approves RM-S3/RM-S4 permission paths, logs APPROVALS. C2 after all three.
3. Retry any 2s/gr first. Round 4: OC-T1/T3 then T2 (one workflow, specs from offline-classes §7 T1-T3) + TA (S9, tests for RM-S1..S4 and access words, mutants from roles-mvp §9).
4. Round 5: TB, DOC+DEMO (one workflow). C4 by orchestrator (also P1-I3/P1-I8 demos on both adapters, just tour 1 once).
5. Specs for round 4 are written in r4 from RM-S3/S4/OC-S2 reports (guard sites listed there).
## REFS
Specs wave0.md, roles-mvp.md (§6 RM-S3, §5/§11 RM-S4), offline-classes.md (§5, §7), phase2-wave-plan.md, OWNER-DECISIONS-2026-10-30.md. Reports docs/reports/P2-W0/{RM-S1,RM-S2,W0-B1,W0-B2,OC-S1,A1-A3}.md (guard sites for TA in RM-S1, RM-S2). Fixtures docs/tickets/P2-W0/provided/relay-{ok,bad}.txt. Acceptance scripts dev/accept/P2-W0/.
## TRAPS
Worktree /home/user/wt/p2-w0 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. After pyproject entry-point edits (W0-B2, merged) run uv sync once. A route reading project from the body is 422 before 403 for an empty body (RM-S2 learning). Module record from Record.Created alone is hidden (ADR-0016) except to system_view().
