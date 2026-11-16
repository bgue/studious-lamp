# P2-IP STATE  r=4 base=ff727291 C=C2 ck=0 gate=n/a wt=/home/user/wt/ip-r3
Fan-out across P2-QR, P2-INSP, P2-PTW. Plans: `docs/tickets/P2-{QR,INSP,PTW}/README.md` (Plan check answered, F1-F14). Round 4: the T01 views and QR-T04 are merged; the next surface, card and seed tickets and three piece specs are written.
Branch `p2/ip-r3` (from `p2/ip-x4` head 10acf325 = `p2/ip` + `p2/x4` + the three S2 merges + F1/F2) carries every ticket of this batch; X4 is not on the trunk yet (D8). Heads: r3 end ff727291; r4 = the commit that holds this file.
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
QR-T07 t stg f - READY r4: CLI `tl qr` (label, ls, revoke, rotate, resolve, export); disp r4
QR-T06 t stg f - READY r4: API router GET /qr/codes, /export, /resolve/{code}; agents closed; disp r4
PTW-T04 t stg f - READY r4: `tl permit` ten write verbs in cli_permit_write.py; disp r4
PTW-T05 t stg f - READY r4: `tl permit` ls/show/board/export in cli_permit_read.py; disp r4
INSP-T09 t stg f - READY r4: card quality.Inspection copying QR-T04; disp r4
PTW-T09 t stg f - READY r4: card permits.Permit; gas/isolation lines deferred to T02; disp r4
INSP-T04 t stg f - READY r4: `tl insp` (tl_cli/insp*.py); appends cli_groups ref in quality module.py
INSP-T05 t stg f - READY r4: `tl checklist` (tl_cli/checklist*.py); appends cli_groups ref (same tuple as T04)
INSP-T06 t stg f - READY r4: five GET routes tl_api/routes/insp.py; route_order + openapi pins
INSP-T07 t stg f - READY r4: MCP reads + propose_inspection; identity.py two lines; OLD_TOOL_NAMES pin
PTW-T07 t stg f - READY r4: API router, permit routes only; isolation/gas routes = T07b after T02
PTW-T08 t stg f - READY r4: MCP permit reads + propose_permit; list_isolations = T08b after T02
QR-S3 p stg f - SPEC r4 (S3-scan-page.md); builder; waits for X4 on trunk to merge; start after QR-T06 (log filter names its route)
PTW-S3 p stg f - SPEC r4 (S3-isolations-and-gas-tests.md); builder; writes provided test of T02
PTW-S5 p stg f - SPEC r4 (S5-lapse-job.md); builder; copies the job on p2/i4b via git show
INSP-T03 p stg f - SPEC r4 (T03-seed-section.md); a piece, not a ticket (D23); roster: lhartmann quality superuser
INSP-S3 t todo f - readiness check; after S2 (merged); same awp pyproject file as PTW-S4: INSP first
PTW-S4 t todo f - after PTW-S2 and INSP-S3 (same awp file)
QR-T11 t todo f - demo; after T04, T06, T07
QR-T12/INSP-T14,T15/PTW-T15,T16 t todo - demos, tour, docs; after their surfaces
PTW-T02 t todo f - iso views; after PTW-S3 (provided test written by S3)
INSP-T08/PTW-T10 t todo f - client methods; after the API routes
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
## SEC
(none yet; one wave review over d4e92ffc..<p2/ip head> at C4; rows listed in each README plus the S2 spec Goal items; r4 adds: QR-T06 agents closed and resolve 404s equal, QR-S3 whole spec, PTW-S3 hidden-permit text, PTW-S5 job writes the flag only)
## OPEN
Q2 gas limit defaults signed by safety lead needs owner raised PTW-S1
Q3 forms: accept ADR-0031 (capture-only forms engine in core; INSP thin, PTW typed) needs owner raised FORMS-EVAL
Q4 forms: vendor the two MIT SurveyJS files into the web client, fallback server page needs owner raised FORMS-EVAL
Q5 forms: server-side drafts (default no); queue permits offline (default no); cached as-of status (default no) needs owner raised FORMS-EVAL
Q6 forms: late window 72 h `forms.late_accept_hours`; general submissions reviewed by a controller needs owner raised FORMS-EVAL
Q7 delegation: RequestPermit eligible for policy auto-accept? (default no, D10) needs owner raised PTW-S2
Q8 p2/ip-x4 goes to p2/ip only after X4 is on trunk (D8); until then ticket bases are p2/ip-r3 needs orch raised IP-r2
Q9 owner to confirm D15 (approver may issue a permit) needs owner raised PTW-S2
Q10 PTW-S2 stub `routes.py` docstring says 'T05 adds them'; plan and T07 say T07: ticket wins, T07 may fix the docstring needs orch raised IP-r4
Q11 QR-T06 asks `qr.view` per project on the list/export routes and the provider view word on resolve: confirm no extra word is wanted needs owner raised QR-T06
## NEXT
1. Orch: dispatch the six DISPATCH items of the r4 relay (base `p2/ip-r3` head). Workflow A {QRT07, PTWT05, PTWT04} (CLI files), workflow B {INSPT09, PTWT09, QRT06}; at most 2 heavy runs.
2. Next batch (disjoint paths): INSP-T04, INSP-T05 (one module.py tuple: serialise or accept an append merge), INSP-T06, INSP-T07, PTW-T07, PTW-T08 (route_order and openapi pins: one API-route ticket per workflow). Builder slots: PTW-S3, PTW-S5, INSP-T03 (one at a time, one workflow beside).
3. After QR-T06 merges: QR-S3 builder (it edits tl_web app/routers and tl_api main). After PTW-S3 merges: PTW-T02 (provided test), PTW-T03 seed, PTW-T06 CLI iso/gastest, T07b/T08b.
4. WAITS FOR X4 ON TRUNK (D8): no S2 merge into p2/ip (QR, INSP, PTW, F1, F2); QR-S3, INSP-S3, PTW-S4 (awp pyproject); every merge of a ticket branch into p2/ip; the three-S2 gate-pg rerun on freed disk.
5. After X4 lands: merge trunk into p2/ip-x4, then p2/ip-x4 into p2/ip (Q8), re-issue bases of open tickets from p2/ip.
6. Heavy runs at most 2; tl-api test_commands.py alone is 7-9 GB: in no gate. tl-api and tl-mcp test files gated one per call.
## REFS
Specs: docs/tickets/P2-IP/S2-common.md; S2 specs under P2-{QR,INSP,PTW}; S2 reports docs/reports/P2-{QR,INSP,PTW}/S2.md; T01/T04 reports under docs/reports/P2-*.
r4 tickets: P2-QR/{T06-api-read-router,T07-cli-qr}.md; P2-PTW/{T04-cli-permit-writes,T05-cli-permit-reads,T07-api-router,T08-mcp-tools,T09-scan-card}.md; P2-INSP/{T04-cli-insp,T05-cli-checklist,T06-api-routes,T07-mcp-tools,T09-scan-card}.md.
r4 specs: P2-QR/S3-scan-page.md; P2-PTW/S3-isolations-and-gas-tests.md, S5-lapse-job.md; P2-INSP/T03-seed-section.md. Job pattern for S5: `git show p2/i4b:packages/tl-modules/scaffold/src/tl_mod_scaffold/inspections_due.py` (never check out).
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
