# P2-W0 STATE  r=4 base=9563763 C=C2 ck=0 gate=n/a wt=/home/user/wt/p2-w0
Read first: docs/build-spec/specs/wave0.md (plan, "Plan check" at the end), README.md here. Branch p2/w0 (trunk claude/wizardly-allen-m2v96s @0a69e0a). Builders and tickets branch from p2/w0 HEAD (the r4 state commit).
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
OC-T1 t stg f - T04-record-types-route.md; GET /record-types + record_types() on clients; r4
OC-T2 t stg f - T05-offline-row.md; technical-mode row; after T04 (needs record_types)
OC-T3 t stg l - T06-scaffold-offline.md; template tl:offline none + expected pin; r4
RM-S3L t stg l - T07-roles-lows.md; review lows F1-F4; r4
OC-T4 t stg l - T08-delivery-class.md; InboundDelivery none (schema, orch approves); r4
TA p todo f - r5 tests for RM-S1..S4 + access words (Sonnet)
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
D18 2026-10-31 T04: row model RecordTypeRow + record_type_rows() in tl_core/offline.py (one copy for route and embedded); action reference.read (exists, agent-allowed; not record.read); extension types not listed; remote needs no code (__getattr__)
D19 2026-10-31 T05: spec path details/technical.py is the RFI renderer; the offline row is added in details_for (details/__init__.py) + generic.py, technical mode, panel=False
D20 2026-10-31 Q5 decided by orch: InboundDelivery offline class none. Not folded into the lows ticket: it is a schema change (tl:offline + tl:stream_type, just gen) -> own ticket T08, label schema, orch approves under P2-Q10
D21 2026-10-31 r4 file names T04..T08 = OC-T1, OC-T2, OC-T3, RM-S3L, OC-T4; relay ids T04..T08 (relay-lint id class has no '-'); T06 updates tests/expected/record_type/weld_inspection.yaml (rule 12)
## SEC
Not run (owner: only if asked). Rows recorded: RM-S1 Y, RM-S2 Y, RM-S3 Y, RM-S4 Y, W0-B1 Y, W0-B2 Y. Range 0a69e0a..P2-W0 head.
## OPEN
Q1 orchestrator: ADR-0022, Phase 2 decisions ADR, accept ADR-0021 (contracts §1/§7 frozen per W0-B1 merge) needs orch raised wave0 §9
Q2 owner/orch confirm awp.release.signoff_roles default [superuser] (W0-B1 wrote it as proposed) needs owner raised wave0 §9
Q4 end run: TUI settings snapshot (test_snapshots_settings) differs after 11 keys; accounts-screen/admin snapshots differ after RM-S3; review --snapshot-update needs builder(TA) raised W0-B1
Q6 end run: RM-S2 unaudited tests (tl-sim, tests/auth/test_authorizer_and_seed.py) and its predicted extra pins may break; TA reads them needs builder(TA) raised RM-S2
Q7 TA: test_cli_corr.py::SITES and test_cli_domains.py comm loop use made-up ids; now 'no item' before forbidden after RM-S4 (ADR-0016 order); TA seeds real records needs builder(TA) raised RM-S4
## NEXT
1. r4 dispatch, one workflow (T04, T06, T07, T08 independent; T05 after T04 merged or branched from T04 head). Branches p2/w0-t04-record-types-route, -t05-offline-row, -t06-scaffold-offline, -t07-roles-lows, -t08-delivery-class.
2. Merge order on P: T04, T05, T06, T07, T08. T08 is a schema change: orch approves under P2-Q10 and logs APPROVALS. T04 regenerates docs/reference/openapi.json (python -m tl_api.openapi on conflict).
3. Retry any 2s/gr first. Tests and tours stay deferred to the end run (D2). Each ticket leaves dev/accept/P2-W0/<id>.py or a named smoke.
4. Round 5: TA (S9: tests RM-S1..S4 + access words, mutants roles-mvp §9; read Q6, Q7 first), TB (OC §7 tests incl. T04/T05/T06 files, W0-B2, reserved, keys, A1-A3), DOC + DEMO one workflow. TA/TB briefs list the old-text pins named in T05/T07/T08 reports.
5. C4 by orchestrator (also P1-I3/P1-I8 demos on both adapters, just tour 1 once).
## REFS
Specs wave0.md, roles-mvp.md (§6 RM-S3, §5/§11 RM-S4), offline-classes.md (§5, §7), phase2-wave-plan.md, OWNER-DECISIONS-2026-10-30.md. Reports docs/reports/P2-W0/{RM-S1,RM-S2,W0-B1,W0-B2,OC-S1,A1-A3}.md (guard sites for TA in RM-S1, RM-S2). Fixtures docs/tickets/P2-W0/provided/relay-{ok,bad}.txt. Acceptance scripts dev/accept/P2-W0/.
## TRAPS
Worktree /home/user/wt/p2-w0 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. After pyproject entry-point edits (W0-B2, merged) run uv sync once. A route reading project from the body is 422 before 403 for an empty body (RM-S2 learning). Module record from Record.Created alone is hidden (ADR-0016) except to system_view().
