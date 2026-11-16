# P2-IP STATE  r=6 base=c085b915 C=C2 ck=0 gate=n/a wt=/home/user/wt/ip-r3
Fan-out across P2-QR, P2-INSP, P2-PTW. Plans: `docs/tickets/P2-{QR,INSP,PTW}/README.md` (Plan check answered, F1-F14). Round 6: r5 batch merged (13 items, QR-S3 incl.); the last twelve tickets written; IP DONE checklist in NEXT.
Branch `p2/ip-r3` carries every ticket; builder merges trunk and `p2/ip` (forms) into `p2/ip-int` from `7985e828` (do not touch). Ticket bases = `p2/ip-r3` head at dispatch. Reports land at `docs/reports/P2-IP/<relay id>.md` (D39).
## BOARD
S1 pieces QR, INSP, PTW p mrg f (a34abf02, ed1ff779, 15962582); ADR-0030 accepted; APPROVALS; gas defaults pending safety lead
S2 pieces QR, INSP, PTW p mrg f (eaf68371, 463f8871, aa12b9f2) on p2/ip-x4; sec reviews P after fixes; FORMS-CR1 600591e3; X4-F1/F2 8abcab3d,c9ae6cc9
T00/T01/T02/T03 early tickets QR, INSP, PTW t mrg (QR-T02,T03; INSP-T00,T01; PTW-T00,T01; QR-T01 3088c62f)
QR-T04 f0ecbd20, T06 182dc7ec, T07 04be50cb; INSP-T04 6e48a1b7, T05 f18145ae, T06 8470eea4, T07 6e1fc511, T09 ac3334a0 t mrg f review P
PTW-T04 a92df5ba, T05 0d683b36, T08 705b3f5d, T09 6bdb4bda t mrg f review P
INSP-T03 p mrg f 9ee5c5b4 seed; PTW-S3 p mrg f a25a6297 (sec F1 MD fixed); PTW-S5 p mrg f c3771554 lapse job
PTW-T07 t mrg f 7b5509e3 permit routes; PTW-T02 t mrg f da88dbca iso views; INSP-T08 t mrg f 0b4cea79 client
PTW-T03 p mrg f 2a89c949 permits seed; PTW-T06a t mrg f 8d581e96; PTW-T06b t mrg f ac81ec58; INSP-S3 t mrg f 0d4db34a
PTW-S4 t mrg f 9b275d47 (Lapsed day granularity, Q12 accepted); PTW-T08b t mrg f d1a6d1cf; PTW-T07b t mrg f c8772285
QR-S3 p mrg f 9b513c65 scan page (sec F1/F2 HI fixed: strict-origin form pages; APPROVALS c085b915); PTW-T04-FX t mrg 7985e828
PERF1 p disp f - hidden-record filter fast on Postgres (P2-IP/PERF1-hidden-filter-postgres.md); builder on p2/perf1-hidden-filter
IPF3 t stg f - CLI insp_write/checklist_write run as acting person (F3-cli-insp-viewer.md); batch 1
PTWT09b t stg f - card gas and isolation lines (P2-PTW/T09b-card-gas-isolation-lines.md); batch 1
INSPT10 t stg f - terminal inspections log+record (P2-INSP/T10-terminal.md); batch 1
PTWT10 t stg f - client methods, permit_command, fake (P2-PTW/T10-client-methods.md); batch 2
QRT11 t stg f - demo P2-QR, 8 clauses (P2-QR/T11-demo.md); batch 2
IPF4 t stg f - webhook scenario QR, INSP, PTW events (P2-IP/F4-webhook-scenario.md); batch 2
PTWT11 t stg f - terminal permits register+record; after PTWT10 (P2-PTW/T11-terminal.md); batch 3
INSPT14 t stg f - demo P2-INSP 7 clauses + 7b; after INSPT10 (P2-INSP/T14-demo.md); batch 3
PTWT15 t stg f - demo P2-PTW 8 clauses + 8b; after PTWT11 (P2-PTW/T15-demo.md); batch 4
IPF5 t stg l - tour shots 13-16; after INSPT10, PTWT11 (P2-IP/F5-tour-shots.md); batch 4
INSPT15, PTWT16, QRT12 t stg l - docs; after demos INSPT14, PTWT15, QRT11 (T15-docs, T16-docs, T12-docs); batch 5
Follow-up slice (INSP T02/T11/T12/T13, PTW T12-T14, QR T05/T08-T10, hook declarations): not scheduled; DEFERRED.

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
D34 2026-11-16 r6: PTW-T11 screen offers approve, reject, suspend, resume, revalidate, hand back, close; issue, cancel, request stay CLI (issue needs ticked precautions, gas test, verified isolations: a form, follow-up)
D35 2026-11-16 r6: no CLI/API/MCP read takes a clock; PTW demo clause 2 moves the clock in-process (views `now=`, `lapse.run_once`, card provider); CLI/API/MCP lapse reads stay with test_views_lapse and the walks
D36 2026-11-16 r6: no QR tour shot (tourkit is terminal only); scan page text is shown by the P2-QR demo clauses 2 and 7; F5 shots 13-16 are INSP and PTW screens
D37 2026-11-16 r6: QR demo clause 3 covers four of six miss kinds (malformed, unknown, revoked, hidden); expired and no-word are test_scan_page.py only (no clock, no account lacks qr.view)
D38 2026-11-16 r6: PTW card line `Gas test` always present (`none taken` is information on a safety card); `Isolations n of m verified` counts only isolations the viewer reads
D39 2026-11-16 r6: IP tickets name their report `docs/reports/P2-IP/<relay id>.md` (implementers had deviated to it every time)
D40 2026-11-16 r6: IPF3 CLI viewer fix is one ticket for both files (same one-line change, a spy test each); webhook scenario ticket IPF4 covers QR, INSP, PTW events only, forms events after the integration merge
D32 2026-11-16 every new controller action is decided in test_auth_review.py in its own ticket; MCP tickets name test_mcp_server.py TOOLS and test_module_tool_hooks.py OLD_TOOL_NAMES; route tickets name route_order.txt and openapi.json
## SEC
F1/F2 HI QR-S3 fixed (form pages strict-origin; no-referrer pages host no form); F1 MD PTW-S3 fixed. One wave review over d4e92ffc..<p2/ip head> at C4; rows listed in each README plus the S2 spec Goal items; r4 adds: QR-T06 agents closed and resolve 404s equal, QR-S3 whole spec, PTW-S3 hidden-permit text, PTW-S5 job writes the flag only; r5: iso/gas views, routes, tools read hidden as missing; S4 check reads without viewer, keys only; PTW-S3 F1 MD fixed; residual LO per-account clearance privileged)
## OPEN
Q2 gas limit defaults signed by safety lead needs owner raised PTW-S1
Q3 forms: accept ADR-0031 (capture-only forms engine in core; INSP thin, PTW typed) needs owner raised FORMS-EVAL
Q4 forms: vendor the two MIT SurveyJS files into the web client, fallback server page needs owner raised FORMS-EVAL
Q5 forms: server-side drafts (default no); queue permits offline (default no); cached as-of status (default no) needs owner raised FORMS-EVAL
Q6 forms: late window 72 h `forms.late_accept_hours`; general submissions reviewed by a controller needs owner raised FORMS-EVAL
Q7 delegation: RequestPermit eligible for policy auto-accept? (default no, D10) needs owner raised PTW-S2
Q8 p2/ip-x4 goes to p2/ip only after X4 is on trunk (D8); until then ticket bases are p2/ip-r3 needs orch raised IP-r2
Q9 owner to confirm D15 (approver may issue a permit) needs owner raised PTW-S2
Q13 PTW-S3 DEFERRED: add permits.Permit to SCANNED_STREAM_TYPES (core scan) needs orch raised PTW-S3
Q14 forms events in the webhook scenario and forms catalog pins, after p2/ip-int holds the forms branch needs orch raised IPF4
## NEXT
1. Batch 1 {IPF3, PTWT09b, INSPT10} one wf (no API-route ticket); builder PERF1 beside it. Max 2 heavy runs. Batch 2 {PTWT10, QRT11, IPF4}; batch 3 {PTWT11 after PTWT10, INSPT14 after INSPT10}; batch 4 {PTWT15 after PTWT11, IPF5 after both screens}; batch 5 {INSPT15, PTWT16, QRT12} docs (root AGENTS.md rows append-conflict: orch resolves).
2. Gates: ruff, scoped pyright, named test files, one `just gate` call per tl-api and tl-mcp test file; `packages/tl-api/tests/test_commands.py` in no gate; demos run once, Postgres down is `ge`.
3. IP DONE (C4, orch): (a) `just check` once; (b) whole suite per directory with `just gate` parts, then `just gate-pg` on touched dirs (permits, qr, quality, tl-api, tl-mcp, tests/webhooks, tests/contract); (c) `just demo P2-QR`, `P2-INSP`, `P2-PTW` on SQLite and Postgres, each clause PASS; (d) ONE wave security review over `d4e92ffc..<p2/ip head>` with the Sec rows in SEC, findings fixed by pieces or tickets, re-check on fix commits; (e) PERF1 merged and `gate-pg` on the permit and inspection views; (f) Q13 decided, DEFERRED row of the webhook scenario closed (IPF4 + forms after integration).
4. DONE round (fresh supervisor): reports `docs/reports/P2-{QR,INSP,PTW}.md` (<= 80 lines each, from STATE), learnings, README and AGENTS pointers, STATUS and APPROVALS lines, `88` with REPORT.
5. Orch before any merge into p2/ip: merge trunk into p2/ip-x4 then into p2/ip (Q8, D33); the three-S2 gate-pg rerun; re-issue open ticket bases.
6. Open owner items to carry to DONE: Q2 (gas defaults, safety lead), Q3-Q6 forms, Q7, Q9.
## REFS
Specs: docs/tickets/P2-IP/S2-common.md; S2 specs under P2-{QR,INSP,PTW}; S2 reports docs/reports/P2-{QR,INSP,PTW}/S2.md; T01/T04 reports under docs/reports/P2-*.
r4 tickets: P2-QR/{T06-api-read-router,T07-cli-qr}.md; P2-PTW/{T04-cli-permit-writes,T05-cli-permit-reads,T07-api-router,T08-mcp-tools,T09-scan-card}.md; P2-INSP/{T04-cli-insp,T05-cli-checklist,T06-api-routes,T07-mcp-tools,T09-scan-card}.md.
r4 specs: P2-QR/S3-scan-page.md; P2-PTW/S3-isolations-and-gas-tests.md, S5-lapse-job.md; P2-INSP/T03-seed-section.md. Job pattern for S5: `git show p2/i4b:packages/tl-modules/scaffold/src/tl_mod_scaffold/inspections_due.py` (never check out).
r6 tickets: P2-IP/{F3-cli-insp-viewer,F4-webhook-scenario,F5-tour-shots}.md; P2-PTW/{T09b-card-gas-isolation-lines,T10-client-methods,T11-terminal,T15-demo,T16-docs}.md; P2-INSP/{T10-terminal,T14-demo,T15-docs}.md; P2-QR/{T11-demo,T12-docs}.md.
r5 tickets: P2-PTW/{T02-iso-views,T06a-cli-isolation,T06b-cli-gastest,T07b-api-iso-routes,T08b-mcp-list-isolations,S4-readiness-check}.md; P2-INSP/{T08-client-methods,S3-readiness-check}.md. r5 piece: P2-PTW/T03-seed-section.md. IP-ticket reports: docs/reports/P2-IP/.
Finished patterns to copy: card = packages/tl-modules/awp/src/tl_mod_awp/scan_card.py (+ its test); CLI = tl_cli/punch*.py; API = tl_api/routes/punch.py; MCP = tl_mcp/punch_tools.py; tests = test_cli_punch.py, test_api_punch.py, test_punch_tools.py.
## TRAPS
No read surface takes a clock (D35). tl-web scan routes are bounced by the auth middleware before the guard (QR-S3 learning): agents get 401 on /web/q, 403 on /qr routes. Whole-repo `just check` is orchestrator-only.
Provided rules tests (S2_*) need the X4 hooks: green only on p2/ip-x4 and later. Base failures not ours (pre-existing on the base): forms/permits lacked commands hook pin, 7 agent-grant failures in test_forms_rows (F1 may have fixed: orchestrator confirm).
Baseline pins a new module surface moves: OLD_GROUPS (tl-cli), OLD_TOOL_NAMES (tl-mcp), OLD_COMMANDS and route_order.txt (tl-api). Ticket paths for T06-T08 will touch these only if a new route/tool/group appears: say so in each ticket.
Whole-repo pyright was OOM-killed (247) in all three S2 builds with builders live: touched-path pyright only; `just check` in a ticket runs it whole, so run tickets when at most one other heavy run is live.
uv venv in a new worktree needs `uv sync --offline --all-packages --all-extras` once before pyright resolves anything.
Statement-count tests ignore BEGIN/COMMIT/ROLLBACK. PTW T01 `permit_list` state filter splits Active/Lapsed on valid_until in SQL (no clock read).
set_status writes cur_core_record.status only: tests that need an IWP or inspection state walk the real transitions (QR-T04 report).
`just check` runs past 10 minutes in a worktree (codegen drift): background, no timeout; tickets do not run it.
Ticket id in relay lines has no hyphen (`QRT07`): relay-lint item pattern is `[A-Za-z0-9]+`.
