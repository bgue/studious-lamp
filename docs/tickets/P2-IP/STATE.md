# P2-IP STATE  r=5 base=9ee5c5b4 C=C2 ck=0 gate=n/a wt=/home/user/wt/ip-r3
Fan-out across P2-QR, P2-INSP, P2-PTW. Plans: `docs/tickets/P2-{QR,INSP,PTW}/README.md` (Plan check answered, F1-F14). Round 5: r4 batch merged (27 items); iso views, CLI, route, tool, client and readiness tickets and a seed piece written.
Branch `p2/ip-r3` (from `p2/ip-x4` = `p2/ip` + `p2/x4` + three S2 merges + F1/F2) carries every ticket; X4 is not on trunk (D8). Heads: r4 cce88e5b; r5 = the commit that holds this file; ticket bases = `p2/ip-r3` head at dispatch.
## BOARD
QR-S1 p mrg f a34abf02 review P; ADR-0030 accepted; APPROVALS
INSP-S1 p mrg f ed1ff779 review P; F1 MD `at` accepted; APPROVALS
PTW-S1 p mrg f 15962582 review P; APPROVALS (gas defaults pending safety lead)
QR-T02 t mrg l 26266171 review P after amend 1 + report fix
QR-T03 t mrg f 09182bee review P; 2 LO
INSP-T00 t mrg f bf8bb301 review P after amend 1
PTW-T00 t mrg f 40d0e103 review P first pass (pre-linted)
FORMS-CR1 p mrg f 600591e3 forms rows merged
QR-S2 p mrg f eaf68371 on p2/ip-x4; security review P after fixes; LO beyond two hops recorded
INSP-S2 p mrg f 463f8871 on p2/ip-x4; review P
PTW-S2 p mrg f aa12b9f2 on p2/ip-x4; security+safety review P after F1-F6
X4-F1/F2 p mrg f 8abcab3d,c9ae6cc9 grant fallout; forms commands hook
QR-T01 t mrg f 3088c62f review P after report fix (amend 1)
INSP-T01 t mrg f 3482fbdb review P
PTW-T01 t mrg f ff727291 review P; Lapsed via rules.effective_state; agreement test
QR-T04 t mrg f f0ecbd20 review P; IWP card; 30 tests; window line shows the one planned date set
QR-T07 t mrg f 04be50cb review P round 3; --project required on revoke/rotate (D26)
QR-T06 t mrg f 182dc7ec review P; qr.read on no agent list; 27 controller actions decided
PTW-T04 t mrg f a92df5ba review P
PTW-T05 t mrg f 0d683b36 review P
PTW-T09 t mrg f 6bdb4bda review P; gas/isolation card lines still deferred
INSP-T09 t mrg f ac3334a0 review P
INSP-T04 t mrg f 6e48a1b7 review P
INSP-T05 t mrg f f18145ae review P; cli_groups union
INSP-T06 t mrg f 8470eea4 review P; five GET routes
INSP-T07 t mrg f 6e1fc511 review P; test_mcp_server TOOLS pin unioned
PTW-T08 t mrg f 705b3f5d review P; permit reads + propose_permit
INSP-T03 p mrg f 9ee5c5b4 seed; 2343 records/9793 events; review P (F1-F3 fixed)
PTW-S3 p mrg f a25a6297 review P; sec F1 MD fixed; DEFERRED Q13; APPROVALS
PTW-S5 p mrg f c3771554 lapse job; NULL valid_until never selected; APPROVALS
PTW-T07 t stg f - RE-DISPATCH r5: wf died at gate, no commit; /home/user/wt/ip4/ptwt07 may hold partial files (reuse or reset); batch A
PTW-T02 t stg f - READY r5: iso_views.py; provided T02_test_iso_views.py (ruff clean); batch A
INSP-T08 t stg f - READY r5: inspection/checklist client methods, fake; quality_command widened; batch A
PTW-T03 p stg f - SPEC r5 (T03-seed-section.md): builder piece; permits section of demo; batch B alone
PTW-T06a t stg f - STAGED r5: `tl isolation` all verbs; after T02; batch C
PTW-T06b t stg f - STAGED r5: `tl gastest` + permit export --gas-tests; after T02; batch C
PTW-T08b t stg f - STAGED r5: list_isolations, list_gas_tests tools; after T02; batch C
PTW-T07b t stg f - STAGED r5: iso and gas-test routes; after T07 AND T02 merge; batch D alone
QR-S3 p stg f - SPEC r4 (S3-scan-page.md); QR-T06 merged so ready; X4 on trunk (D33): ready; builder after PTW-T03
INSP-S3 t stg f - STAGED r5 (S3-readiness-check.md); ready (D33); merges before PTW-S4
PTW-S4 t stg f - STAGED r5 (S4-readiness-check.md); waits INSP-S3 merge (awp pyproject)
QR-T11 t todo f - demo; clauses 2,3,6 need the scan page: write after QR-S3 merges
PTW-T10 t todo f - client methods; after T07 and T07b
INSP-T10 t todo f - terminal screens; after INSP-T08 merges
INSP-T14/T15, PTW-T11/T15/T16, QR-T12 t todo - demos, screens, docs; after their surfaces
## DEC
D1 2026-11-15 QR URL is <base>/web/q/<code> (cookie Path=/web); ADR-0030, spec, QR S1
D2 2026-11-16 supersedes D2 of r1: S2 pieces DO declare hooks (X4 complete); rules in P2-IP/S2-common.md; errors hook still deferred (core error classes)
D3 2026-11-15 max 2 heavy runs; with S2 the steady state is one S2 builder + one ticket workflow
D4 2026-11-15 first signed S1 merges first; later ones merge p2/ip, just gen, re-pin
D5 2026-11-15 QR T03 helper is tests/contract/scan_card_harness.py (importable); test file provided
D6 2026-11-15 LabelSize enum keeps tag, card, sheet; labels.py renders tag only
D7 2026-11-16 base of every S2 is p2/ip merged with p2/x4 (`p2/ip-x4`, orchestrator); trial merge conflicts only in tests/settings/test_phase2_keys.py (pin) plus regenerated files
D8 2026-11-16 S2 branches merge into p2/ip only after X4 is on trunk and p2/ip has merged the trunk ("waits for X4 on trunk"); build, gate, review may start now
D9 2026-11-16 confidentiality.py serialised (plan-check F8): one S2 per wave edits it; order QR, INSP, PTW; QR S2 also turns the two SUBJECT_LINKS pins in test_forms_rows.py into [:6] and [6:9]; PTW S2 adds all three PTW rows
D10 2026-11-16 marks: QR Issue/Rotate excluded:access, Revoke excluded:reserved (row meta); INSP PlanInspection eligible, ten others reserved (delegation_marks.toml); PTW all ten reserved in row meta, RequestPermit keeps agent row propose_permit (owner may flip)
D11 2026-11-16 new module packages (qr, permits) add fastapi, mcp, typer only; never tl-api, tl-mcp, tl-cli (those depend on the module: cycle); uv lock --offline
D12 2026-11-16 the secret code leaves only through tl_mod_qr.service.issue/rotate (CLI, web form); the generic command handler drops it
D13 2026-11-16 S2 builders write the provided test of their T01 (F8); S2 stubs the three surface hooks so T04-T08 tickets edit disjoint files
D14 2026-11-16 supervisor wrote 70 lines of held tests (docs/tickets/P2-IP/provided/, ruff+pyright clean on merged base): over the ~50 cap for three pieces; no other code
D15 2026-11-16 owner: a requester may not issue a permit, an approver may (S2 refuses requester approve+issue; owner confirm pending, Q9); gas defaults await safety lead (Q2)
D16 2026-11-16 QR T01 clock: views carry no `now`; expired = expires_on[:10] < utcnow date (rule of resolve.py:61), the one clock read; INSP and PTW views take no clock or `now` param
D17 2026-11-16 IWP card (QR-T04): banner by state, READY k/n from stored evaluation, open_path None (no web IWP record page), drawings-stale line deferred (no source)
D18 2026-11-16 provided T01 tests checked lint-clean in place (ruff format+check, pyright 0) at r3; tickets say so
D-FORMS 2026-11-15 owner asked forms eval; verdict (a) capture-only engine; forms path after INSP C2, PTW C2, X4 C2 (module-designs/forms-eval.md, ADR-0031)
D19 2026-11-16 r4: supervisor wrote 0 lines of code and no provided test; each ticket lists tests for the implementer and gates ruff + scoped pyright + named test files (no `just check`: OOM; orchestrator runs it at DONE)
D20 2026-11-16 r4: QR resolve over the API stays `GET /qr/resolve/{code}` (plan); guard action `qr.read` is on no agent list so agents get the closed 403; S3's access-log filter also redacts that path
D21 2026-11-16 r4: card banners decided in the tickets (INSP: hold point stop, Done-accept 'to verify' caution, Verified-accept go; PTW: Lapsed and Suspended stop, any unknown state NOT VALID stop); permit gas and isolation lines wait for PTW-T02 like D17
D22 2026-11-16 r4: PTW-T07/T08 cut to permit reads (T01 only); INSP-T04..T07 each append one ref to its own tuple in quality module.py; append conflicts and union pins (OLD_GROUPS, OLD_TOOL_NAMES, route_order, openapi) are resolved by the orchestrator, rule 12
D23 2026-11-16 r4: INSP-T03 is a builder piece (seed ~150 lines, goldens in four files); `lhartmann` gets quality superuser so the verifier differs from the recorder `hsato`
D24 2026-11-16 r4: PTW-S5 job id carries the minute of `now`; source `job:permits.lapse` is already reserved by the `job:` prefix; no core edit; no CLI or scheduler yet
D25 2026-11-16 r4: PTW-S3 failing gas test suspends an Active or Lapsed gas-test permit without the suspend word; all six S3 commands `excluded:reserved`
D26 2026-11-16 r5: QR-T07 revoke/rotate keep required --project; default label text = label_fields title (rulings applied)
D27 2026-11-16 r5: Q10 ruled T07 adds the routes; Q11 ruled yes (qr.view per project on list/export; provider view word on resolve)
D28 2026-11-16 r5: PTW-T06 split: T06a `tl isolation`, T06b `tl gastest` + permit export --gas-tests (disjoint files)
D29 2026-11-16 r5: PTW-T03 is a builder piece like INSP-T03 (D23); no roster change (ipetrov approves/issues, cbrooks/pnair request, lhartmann second verifier)
D30 2026-11-16 r5: INSP-S3 and PTW-S4 are full-review tickets (in a workflow) with a pyproject entry-point edit; uv sync once after it
D31 2026-11-16 r5: PTW-S4 decides Lapsed at day granularity (valid_until before start of `today` UTC) via rules.effective_state; Q12
D33 2026-11-16 r5: X4 is on trunk (92969fca): D8 waits lifted for building; merging trunk into p2/ip-x4 then p2/ip (Q8) is the orchestrator's step before any merge into p2/ip
D32 2026-11-16 every new controller action is decided in test_auth_review.py in its own ticket; MCP tickets name test_mcp_server.py TOOLS and test_module_tool_hooks.py OLD_TOOL_NAMES; route tickets name route_order.txt and openapi.json
## SEC
(none yet; one wave review over d4e92ffc..<p2/ip head> at C4; rows listed in each README plus the S2 spec Goal items; r4 adds: QR-T06 agents closed and resolve 404s equal, QR-S3 whole spec, PTW-S3 hidden-permit text, PTW-S5 job writes the flag only; r5: iso/gas views, routes, tools read hidden as missing; S4 check reads without viewer, keys only; PTW-S3 F1 MD fixed; residual LO per-account clearance privileged)
## OPEN
Q2 gas limit defaults signed by safety lead needs owner raised PTW-S1
Q3 forms: accept ADR-0031 (capture-only forms engine in core; INSP thin, PTW typed) needs owner raised FORMS-EVAL
Q4 forms: vendor the two MIT SurveyJS files into the web client, fallback server page needs owner raised FORMS-EVAL
Q5 forms: server-side drafts (default no); queue permits offline (default no); cached as-of status (default no) needs owner raised FORMS-EVAL
Q6 forms: late window 72 h `forms.late_accept_hours`; general submissions reviewed by a controller needs owner raised FORMS-EVAL
Q7 delegation: RequestPermit eligible for policy auto-accept? (default no, D10) needs owner raised PTW-S2
Q8 p2/ip-x4 goes to p2/ip only after X4 is on trunk (D8); until then ticket bases are p2/ip-r3 needs orch raised IP-r2
Q9 owner to confirm D15 (approver may issue a permit) needs owner raised PTW-S2
Q12 PTW-S4 Lapsed at day granularity (contract gives a date): default per D31 needs owner raised PTW-S4
Q13 PTW-S3 DEFERRED: add permits.Permit to SCANNED_STREAM_TYPES (core scan) needs orch raised PTW-S3
## NEXT
1. Orch: batch A {PTWT07 (the one API-route ticket), PTWT02, INSPT08} one wf. Builder beside it: PTWT03 piece (r5), then QR-S3 piece. Max 2 heavy runs.
2. Batch B after A: {INSPS3, PTWT06a, PTWT06b} (T06a/b need T02 merged; INSP-S3 needs X4: ready). Batch C: {PTWT08b, PTWS4 after INSP-S3 merges}. Batch D: {PTWT07b} alone (API route; needs T07 and T02 merged).
3. After INSP-T08 merges: INSP-T10 terminal (r6). After T07, T07b merge: PTW-T10 client (r6). QR-T11 after QR-S3 merges.
4. Orch before any merge into p2/ip: merge trunk into p2/ip-x4, then p2/ip-x4 into p2/ip (Q8, D33), re-issue open bases; the three-S2 gate-pg rerun. QR-S3, INSP-S3, PTW-S4 may now build; PTW-S4 after INSP-S3 (awp pyproject).
5. Heavy runs at most 2; tl-api test_commands.py in no gate; tl-api and tl-mcp test files gated one per call.
6. Owed (r6): PTW card gas/isolation lines after T02 (small ticket: permits/scan_card.py + test).
## REFS
Specs: docs/tickets/P2-IP/S2-common.md; S2 specs under P2-{QR,INSP,PTW}; S2 reports docs/reports/P2-{QR,INSP,PTW}/S2.md; T01/T04 reports under docs/reports/P2-*.
r4 tickets: P2-QR/{T06-api-read-router,T07-cli-qr}.md; P2-PTW/{T04-cli-permit-writes,T05-cli-permit-reads,T07-api-router,T08-mcp-tools,T09-scan-card}.md; P2-INSP/{T04-cli-insp,T05-cli-checklist,T06-api-routes,T07-mcp-tools,T09-scan-card}.md.
r4 specs: P2-QR/S3-scan-page.md; P2-PTW/S3-isolations-and-gas-tests.md, S5-lapse-job.md; P2-INSP/T03-seed-section.md. Job pattern for S5: `git show p2/i4b:packages/tl-modules/scaffold/src/tl_mod_scaffold/inspections_due.py` (never check out).
r5 tickets: P2-PTW/{T02-iso-views,T06a-cli-isolation,T06b-cli-gastest,T07b-api-iso-routes,T08b-mcp-list-isolations,S4-readiness-check}.md; P2-INSP/{T08-client-methods,S3-readiness-check}.md. r5 piece: P2-PTW/T03-seed-section.md. IP-ticket reports: docs/reports/P2-IP/.
Finished patterns to copy: card = packages/tl-modules/awp/src/tl_mod_awp/scan_card.py (+ its test); CLI = tl_cli/punch*.py; API = tl_api/routes/punch.py; MCP = tl_mcp/punch_tools.py; tests = test_cli_punch.py, test_api_punch.py, test_punch_tools.py.
## TRAPS
Provided rules tests (S2_*) need the X4 hooks: green only on p2/ip-x4 and later. Base failures not ours (pre-existing on the base): forms/permits lacked commands hook pin, 7 agent-grant failures in test_forms_rows (F1 may have fixed: orchestrator confirm).
Baseline pins a new module surface moves: OLD_GROUPS (tl-cli), OLD_TOOL_NAMES (tl-mcp), OLD_COMMANDS and route_order.txt (tl-api). Ticket paths for T06-T08 will touch these only if a new route/tool/group appears: say so in each ticket.
Whole-repo pyright was OOM-killed (247) in all three S2 builds with builders live: touched-path pyright only; `just check` in a ticket runs it whole, so run tickets when at most one other heavy run is live.
uv venv in a new worktree needs `uv sync --offline --all-packages --all-extras` once before pyright resolves anything.
Statement-count tests ignore BEGIN/COMMIT/ROLLBACK. PTW T01 `permit_list` state filter splits Active/Lapsed on valid_until in SQL (no clock read).
set_status writes cur_core_record.status only: tests that need an IWP or inspection state walk the real transitions (QR-T04 report).
`just check` runs past 10 minutes in a worktree (codegen drift): background, no timeout; tickets do not run it.
Ticket id in relay lines has no hyphen (`QRT07`): relay-lint item pattern is `[A-Za-z0-9]+`.
