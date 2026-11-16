# P2-IP STATE  r=3 base=10acf325 C=C2 ck=0 gate=n/a wt=/home/user/wt/ip-r3
Fan-out across P2-QR, P2-INSP, P2-PTW. Plans: `docs/tickets/P2-{QR,INSP,PTW}/README.md` (Plan check answered, F1-F14). Round 3: T01 tickets re-issued on the merged S2 interfaces; QR-T04 written.
Branch `p2/ip-r3` (from `p2/ip-x4` head 10acf325 = `p2/ip` + `p2/x4` + the three S2 merges + F1/F2) carries this round; every ticket in the batch branches from it. X4 is not on the trunk yet (D8).
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
QR-T01 t stg f - READY: re-issued r3 (views stub pasted, expiry rule, gate path)
INSP-T01 t stg f - READY: re-issued r3 (stub + rules pasted, DDL pasted)
PTW-T01 t stg f - READY: re-issued r3 (stub + effective_state pasted)
QR-T04 t stg f - READY: awp IWP card; needs only S1+T03 (merged); test written by the ticket
QR-T06 t todo f - after QR-T01 merges; API router in the module package
QR-T07 t todo f - after QR-T01 (T02 merged); CLI group `tl qr`
INSP-T09 t todo f - card quality.Inspection; after INSP-T01 (pattern of QR-T04)
PTW-T09 t todo f - card permits.Permit; after PTW-T01 (pattern of QR-T04)
INSP-T03 t todo f - seed section; 294-line roster-driven quality.py + golden pins: needs a spec round, not a ticket yet
QR-S3 p todo f - after QR-S2 on trunk; scan page
PTW-S3 p todo f - isolations, gas tests (no confidentiality edit: S2 owns the three rows)
PTW-S5 p todo f - lapse job
INSP-S3 t todo f - readiness check
PTW-S4 t todo f - after PTW-S2 and INSP-S3 (same awp file)
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
## SEC
(none yet; one wave review over d4e92ffc..<p2/ip head> at C4; rows listed in each README plus the S2 spec Goal items)
## OPEN
Q2 gas limit defaults signed by safety lead needs owner raised PTW-S1
Q3 forms: accept ADR-0031 (capture-only forms engine in core; INSP thin, PTW typed) needs owner raised FORMS-EVAL
Q4 forms: vendor the two MIT SurveyJS files into the web client, fallback server page needs owner raised FORMS-EVAL
Q5 forms: server-side drafts (default no); queue permits offline (default no); cached as-of status (default no) needs owner raised FORMS-EVAL
Q6 forms: late window 72 h `forms.late_accept_hours`; general submissions reviewed by a controller needs owner raised FORMS-EVAL
Q7 delegation: RequestPermit eligible for policy auto-accept? (default no, D10) needs owner raised PTW-S2
Q8 p2/ip-x4 goes to p2/ip only after X4 is on trunk (D8); until then ticket bases are p2/ip-r3 needs orch raised IP-r2
Q9 owner to confirm D15 (approver may issue a permit) needs owner raised PTW-S2
## NEXT
1. Orch: dispatch QR-T01, INSP-T01, PTW-T01 (base p2/ip-r3; one workflow of 3 is fine, disjoint paths). QR-T04 next slot (own workflow of 1, or after one T01 ends).
2. After each T01 merges: stage its dependants (QR-T06/T07; INSP-T04..T07; PTW-T04/T05/T07/T08) with the merged signatures; INSP-T09 and PTW-T09 copy QR-T04 (card ticket).
3. Specs needed before the next builder slot: PTW-S3 (isolations, gas), PTW-S5 (lapse job), QR-S3 (scan page; L-P2-WEB1-2), INSP-T03 seed spec.
4. WAITS FOR X4 ON TRUNK (D8): no S2 merge into p2/ip (QR, INSP, PTW, F1, F2); QR-S3 (web scan page), INSP-S3 and PTW-S4 (awp pyproject, shared) , every merge of a ticket branch into p2/ip; the three-S2 gate-pg rerun on freed disk (PTW report: ENOSPC at /).
5. After X4 lands: merge trunk into p2/ip-x4, then p2/ip-x4 into p2/ip (Q8), re-issue bases of open tickets from p2/ip.
6. Heavy runs at most 2; tl-api test_commands.py alone is 7-9 GB.
## REFS
Specs: docs/tickets/P2-IP/S2-common.md; P2-QR/S2-code-service.md; P2-INSP/S2-commands-and-engine.md; P2-PTW/S2-permit-lifecycle.md. S2 reports: docs/reports/P2-{QR,INSP,PTW}/S2.md.
Provided T01 tests (copy byte-identical): docs/tickets/P2-QR/provided/T01_test_views.py -> qr/tests/test_views.py; P2-INSP/provided/T01_test_insp_views.py -> quality/tests/test_insp_views.py; P2-PTW/provided/T01_test_views.py -> permits/tests/test_views.py.
Staged tickets: docs/tickets/P2-{QR,INSP,PTW}/T01-read-views.md (ready), docs/tickets/P2-QR/T04-awp-iwp-card.md (ready).
## TRAPS
Provided rules tests (S2_*) need the X4 hooks: green only on p2/ip-x4 and later. Base failures not ours (pre-existing on the base): forms/permits lacked commands hook pin, 7 agent-grant failures in test_forms_rows (F1 may have fixed: orchestrator confirm).
Baseline pins a new module surface moves: OLD_GROUPS (tl-cli), OLD_TOOL_NAMES (tl-mcp), OLD_COMMANDS and route_order.txt (tl-api). Ticket paths for T06-T08 will touch these only if a new route/tool/group appears: say so in each ticket.
Whole-repo pyright was OOM-killed (247) in all three S2 builds with builders live: touched-path pyright only; `just check` in a ticket runs it whole, so run tickets when at most one other heavy run is live.
uv venv in a new worktree needs `uv sync --offline --all-packages --all-extras` once before pyright resolves anything.
Statement-count tests ignore BEGIN/COMMIT/ROLLBACK. PTW T01 `permit_list` state filter splits Active/Lapsed on valid_until in SQL (no clock read).
