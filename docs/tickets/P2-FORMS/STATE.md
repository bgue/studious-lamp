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
F2  4 todo f     - MCP, draft resume, walks; clause 4
F3  4 todo f     - web fill page + cards; clause 9
F4  4 todo f+sec - intake signed-in; clause 10
F5  5 todo l     - docs, runbook, tour, highlights
## BASE-RED (on p2/v3-forms, not caused by a unit)
awp proposable exclusions fixed by F1a | wheel count 27 vs 21 (DEFERRED)
tl-api: 5 tests red on fc02817a too (settings 34 vs 53 keys x3, permits error table, activity select 16 vs 15; F1a)
## WAVE-REVIEW (for the DONE security review)
N1 privileged Submission that is itself a subject: its own answer class not checked on that hop (P0c sec) | F1s bound.record hardening (scope, use_viewer) before F1b/F3 call it
## OPEN
Q9 S6 public route: owner gate (out of the pilot)
## DEC
D40 2026-11-17 owner Q7: privileged forms hidden from all but the author (CR1 behaviour kept; no clearance table); F1a walk proves it
D41 2026-11-17 owner Q10: key gaps from hidden records allowed, documented as a limit (ADR-0016 Known limits); per-project option later (DEFERRED)
D42 2026-11-18 owner: F1s (form sources) accepted on its full + security reviews (APPROVALS line); the web fill page (F3) needs the owner's own sign-off before merge
## METRICS (for V3-PILOT.md)
start 2026-11-17 wave 1 dispatched; handoffs 19 (5 dispatch, 9 resume, 5 reviews+rechecks beyond the first); rulings 7 (+P0 view word, P0 Q10 to owner, P1 alias rename); late surprises 0; wave 1 wall clock ~6 h (gate queueing ~2 h, disk full once)
lessons: one heavy lock serialised light runs (fixed in P2: 2 slots, dev/tests unlocked); P0 walk tests slow on the pre-P1 base
