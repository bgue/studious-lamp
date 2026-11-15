# P2-IP STATE  r=1b base=9e4efdde C=C0 ck=0 gate=n/a wt=/home/user/wt/design-ip
Fan-out across P2-QR, P2-INSP, P2-PTW. Plans: `docs/tickets/P2-{QR,INSP,PTW}/README.md` (Plan check answered, F1-F14).
Integration branch `p2/ip` created at this commit's parent chain head (not pushed).
## BOARD
QR-S1 p mrg f a34abf02 review P; ADR-0030 accepted; APPROVALS
INSP-S1 p mrg f ed1ff779 review P; F1 MD `at` accepted; APPROVALS
PTW-S1 p mrg f 15962582 review P; APPROVALS (gas defaults pending safety lead)
QR-T02 t mrg l 26266171 review P after amend 1 + report fix
QR-T03 t mrg f 09182bee review P; 2 LO
INSP-T00 t mrg f bf8bb301 review P after amend 1
PTW-T00 t mrg f 40d0e103 review P first pass (pre-linted)
QR-S2 p todo f - after S1 and X4-free (no hooks); writes T01 provided test
INSP-S2 p todo f - after INSP-S1, INSP-T00
PTW-S2 p todo f - after PTW-S1, PTW-T00
## DEC
D1 2026-11-15 QR URL is <base>/web/q/<code> (cookie Path=/web); ADR-0030, spec, QR S1
D2 2026-11-15 S2 pieces carry no hook fields; hooks later after X4 C2 in p2/ip; errors hook DEFERRED
D3 2026-11-15 max 2 heavy runs; QR-S1 with INSP-S1, PTW-S1 after one ends
D4 2026-11-15 first signed S1 merges first; later ones merge p2/ip, just gen, re-pin
D5 2026-11-15 QR T03 helper is tests/contract/scan_card_harness.py (importable); test file provided
D6 2026-11-15 LabelSize enum keeps tag, card, sheet; labels.py renders tag only
## SEC
(none yet; one wave review over d4e92ffc..<p2/ip head> at C4)
D-FORMS 2026-11-15 owner asked forms eval; verdict (a) capture-only engine; in-flight INSP/PTW/QR unchanged; forms path ~6p/24t after INSP C2, PTW C2, X4 C2; module-designs/forms-eval.md, ADR-0031 Proposed
## OPEN
Q1 closed 2026-11-15: ADR-0030 accepted (orch under P2-Q10) + APPROVALS at QR-S1 merge
Q2 gas limit defaults signed by safety lead needs owner raised PTW-S1
Q3 forms: accept ADR-0031 (capture-only forms engine in core; INSP thin, PTW typed) needs owner raised FORMS-EVAL
Q4 forms: vendor the two MIT SurveyJS files (survey-core, survey-js-ui) into the web client, fallback server page needs owner raised FORMS-EVAL
Q5 forms: server-side drafts (default no); queue anything for permits offline (default no); cached as-of status offline (default no) needs owner raised FORMS-EVAL
Q6 forms: late window 72 h `forms.late_accept_hours` (< idempotency retention); general submissions reviewed by a controller, not the submitter needs owner raised FORMS-EVAL
## NEXT
1. Orchestrator: dispatch QR-S1 and INSP-S1 (workflow items, builders), PTW-S1 when one ends.
2. After QR-S1 merges: workflow {QR-T02, QR-T03}.
3. After INSP-S1 merges: INSP-T00; after PTW-S1 merges: PTW-T00 (one workflow of up to 3 tickets).
4. Next round: S2 specs for QR, INSP, PTW (no hook fields; deps and stub registrars; label_fields; _HOPS test).
5. Follow-up slices wait (see each README table).
## REFS
Provided tests: docs/tickets/P2-QR/provided/{T02_test_labels,T03_test_scan_card_contract}.py,
docs/tickets/P2-INSP/provided/T00_test_insp_rules.py, docs/tickets/P2-PTW/provided/T00_test_rules.py.
Tickets: docs/tickets/P2-QR/T02-label-renderer.md, T03-card-contract-harness.md; P2-INSP/T00-insp-rules.md; P2-PTW/T00-ptw-rules.md.
## TRAPS
Provided tests were written before S1 exists and were not run; first run is the ticket gate. Report any test that
fails on its own logic (not on a missing S1 name) back as 2s to the supervisor.
