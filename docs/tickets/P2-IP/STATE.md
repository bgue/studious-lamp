# P2-IP STATE  r=2 base=8878427d C=C1 ck=0 gate=n/a wt=/home/user/wt/design-ip
Fan-out across P2-QR, P2-INSP, P2-PTW. Plans: `docs/tickets/P2-{QR,INSP,PTW}/README.md` (Plan check answered, F1-F14). Round 2: S2 specs against the X4 hooks.
Integration branch `p2/ip` (head 8878427d at round start); this branch `p2/design-ip` carries the documents. X4 (hooks) is on `p2/x4` (44b67625), not on trunk.
## BOARD
QR-S1 p mrg f a34abf02 review P; ADR-0030 accepted; APPROVALS
INSP-S1 p mrg f ed1ff779 review P; F1 MD `at` accepted; APPROVALS
PTW-S1 p mrg f 15962582 review P; APPROVALS (gas defaults pending safety lead)
QR-T02 t mrg l 26266171 review P after amend 1 + report fix
QR-T03 t mrg f 09182bee review P; 2 LO
INSP-T00 t mrg f bf8bb301 review P after amend 1
PTW-T00 t mrg f 40d0e103 review P first pass (pre-linted)
FORMS-CR1 p mrg f 600591e3 forms rows merged (SUBJECT_LINKS holds 10 rows)
QR-S2 p stg f - spec S2-code-service.md; base p2/ip+p2/x4; order 1 of 3
INSP-S2 p stg f - spec S2-commands-and-engine.md; base p2/ip+p2/x4; order 2 of 3
PTW-S2 p stg f - spec S2-permit-lifecycle.md; base p2/ip+p2/x4; order 3 of 3
QR-T01 t stg f - views; re-issue after QR-S2 (stub + provided test come from S2)
INSP-T01 t stg f - views; re-issue after INSP-S2
PTW-T01 t stg f - views and board; re-issue after PTW-S2
QR-T04 t todo f - awp IWP card; needs only T03 (merged), base p2/ip; ticket not yet written
QR-S3 p todo f - after QR-S2; scan page
PTW-S3 p todo f - after PTW-S2; isolations, gas tests (no confidentiality edit: S2 owns the three rows)
PTW-S5 p todo f - after PTW-S2; lapse job
INSP-S3 t todo f - after INSP-S2; readiness check
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
Q8 base branch p2/ip-x4: orchestrator merges p2/x4 into p2/ip (fix the pin, just gen, compat-update) needs orch raised IP-r2
## NEXT
1. Orch: make p2/ip-x4 (D7); dispatch QR-S2 (builder, wt /home/user/wt/qr/s2). INSP-S2 and PTW-S2 may build at once (2 heavy max) but their row commits wait for the earlier S2 to merge (D9).
2. Alongside the S2 builder: one workflow slot. Nothing is ready on p2/ip alone except QR-T04, which round 3 writes; re-issue each T01 as its S2 merges.
3. After each S2 merges: re-issue its T01 (paste the stub), then workflow {T01, T03/T04 ...} per the README waves.
4. After QR-S2 merges: QR-S3 spec (scan page; walk; L-P2-WEB1-2). After PTW-S2: PTW-S3 and PTW-S5 specs.
5. INSP-S3 spec only after INSP-S2 (readiness; shares the awp pyproject with PTW-S4).
6. No S2 merges before X4 reaches the trunk (D8).
## REFS
Specs: docs/tickets/P2-IP/S2-common.md; P2-QR/S2-code-service.md; P2-INSP/S2-commands-and-engine.md; P2-PTW/S2-permit-lifecycle.md.
Provided: docs/tickets/P2-IP/provided/{S2_ip_rules,S2_test_qr_rules,S2_test_insp_rules,S2_test_ptw_rules}.py -> tests/services/{ip_rules,test_qr_s2_rules,test_insp_s2_rules,test_ptw_s2_rules}.py
(checked on a scratch merge of p2/ip and p2/x4: ruff format, ruff check, pyright, 0 findings). S2 builders write the T01 provided tests under each increment's provided/.
Staged: docs/tickets/P2-{QR,INSP,PTW}/T01-read-views.md. X4 reads: `git show p2/x4:tests/ext_demo/src/tl_mod_ext_demo/module.py`, `tl_core/modules.py`, `tests/services/test_module_conformance.py`.
## TRAPS
r2 provided tests need the X4 hooks: red on p2/ip, green only on the merged base. r1 tickets' tests are merged and green on p2/ip.
p2/ip + p2/x4 trial merge: conflict in tests/settings/test_phase2_keys.py; quality/module.py auto-merges (INSP S2 edits it again: keep PUNCH_COMMANDS).
Baseline pins a new module's surfaces move: OLD_GROUPS (tl-cli test_module_cli_groups), OLD_TOOL_NAMES (tl-mcp test_module_tool_hooks), OLD_COMMANDS and route_order.txt (tl-api test_module_hooks_api).
Statement-count tests ignore BEGIN/COMMIT/ROLLBACK. Gates per file or small group; tl-api test_commands.py alone is 7-9 GB; max 2 heavy runs; runs over 10 minutes go to background.
Join budget: SUBJECT_LINKS grows from 10 to 15 rows (QR 1, INSP 1, PTW 3); the join-budget test in test_forms_rows.py must stay green on both adapters.
proposable_exclusions.toml on p2/ip has 11 more lines than on p2/x4: the merge must keep both.
