# P2-FORMS STATE (process v3 pilot)  base=p2/v3-forms  plan=docs/build-spec/process-v3.md
Earlier rounds (v2 board, decisions D1-D39, SEC, OPEN): `STATE-v2.md`. Merged before the pilot: S1 S2 S2w S3 CR1
S7c W1 T01 T02 T03 T13 T14 I02 I03 B1, and P2-IP PERF1.
## BOARD  unit wave state review commit note
P1  1 mrg  f+sec fc02817a per-row check 86.7 s -> 0.28 s; budget gate; pg differential P
P0  1 mrg  f+sec ad9ca63c tl report, 17 reports; 3 fix rounds (stale_links leak, empty --out)
P2  1 mrg  f     83e7a512 gate-changed (2 heavy slots), commit-check; 1 CR round
F1a 2 mrg  f     ef38bed7 5 LO notes: walk has no full-viewer reader; F2 must open an MCP read action
P0b 2 mrg  f     98084507 8 more reports; 2 review rounds; left out requisitions, activities, QR (later unit)
P0c 2 mrg  f+s   3c1cd344 last 3 reports; both reviews P; N1 to wave review
F1b 3 mrg  f     d9c89b3d log, record, runner screens; clause 11 PASS; 3 LO
F1s 3 mrg  f+s   016c02ae sources quality+permits; clause 6 PASS; 1 hardening round
F2  4 mrg  f     41f19967 MCP tools (5 mcp.* actions, forms.read kept closed), resume; clause 4 + MCP leg of 7; 3 LO
F3  4 mrg  f+s   687193ed web fill page, cards; clause 9; both P, LO fixes 62ed003b; owner signed off
F4  4 mrg  f+s   f5c5d146 intake signed-in; clause 10; both P; 3 LO fixed bc9550fe; phone shown to reviewer ok (ADR-0032 d7)
FX  4 mrg  l     6530ebb7 forms, permits, qr rows in tl_api.errors; review F1 (sent id echo) fixed 54c18051
FN1 5 mrg  f+s   054b34bb wave sec F1 (N1): Submission never a subject (forms, intake, permits, quality, constraints)
F5  5 mrg  l     b50ce7a4 runbook, README, tour 2 shots 20-22,24, highlights 19-20; 2 gaps DEFERRED
## BASE-RED (on p2/v3-forms, not caused by a unit)
awp proposable exclusions fixed by F1a | wheel count 27 vs 21 (DEFERRED)
activities report `activity_id` column broke test_no_internal_id_is_a_column (P0c); renamed `activity` c4da8d5a
tl-api: 4 tests red on fc02817a too (settings 34 vs 53 keys x3, activity select 16 vs 15); permits error table fixed by FX
FG  5 disp f+s   d466c221 DONE gate fixes (walk import, role seams, webhook scenario, SchemaView OOM) + D44
## WAVE-REVIEW done 2026-11-18: F1 MD (N1) fixed by FN1; F2 LO moot; F3 LO fixed; bound.record, reports, seams P
N1 privileged Submission that is itself a subject: its own answer class not checked on that hop (P0c sec) | F1s bound.record hardening (scope, use_viewer) before F1b/F3 call it
## OPEN
S1 MD base: intake code_hash in IntakeCode.Issued readable on /events, record history, webhooks (F4 sec F1); must be redacted before S6 opens (schema+core, APPROVALS); DEFERRED S6 row
Q9 S6 public route: owner gate (out of the pilot)
## DEC
D40 2026-11-17 owner Q7: privileged forms hidden from all but the author (CR1 behaviour kept; no clearance table); F1a walk proves it
D41 2026-11-17 owner Q10: key gaps from hidden records allowed, documented as a limit (ADR-0016 Known limits); per-project option later (DEFERRED)
D43 2026-11-18 owner signed off the web fill page (F3); merged 687193ed; APPROVALS line
D44 2026-11-19 owner: Submission.DraftSaved/DraftDiscarded are never delivered by webhook (found by V3-FG: after submit, late dispatch sent draft events to every reader); APPROVALS line
D42 2026-11-18 owner: F1s (form sources) accepted on its full + security reviews (APPROVALS line); the web fill page (F3) needs the owner's own sign-off before merge
## METRICS (for V3-PILOT.md)
merged demo 2026-11-18 @6530ebb7: sq PASS 1-11 (c7 175 s, c8 106 s, c9 47 s, c10 81 s) | pg @a894b1d0 PASS 1-11, list reads median <= 0.137 s | start 2026-11-17 wave 1 dispatched; handoffs 19 (5 dispatch, 9 resume, 5 reviews+rechecks beyond the first); rulings 7 (+P0 view word, P0 Q10 to owner, P1 alias rename); late surprises 0; wave 1 wall clock ~6 h (gate queueing ~2 h, disk full once)
lessons: one heavy lock serialised light runs (fixed in P2: 2 slots, dev/tests unlocked); P0 walk tests slow on the pre-P1 base
