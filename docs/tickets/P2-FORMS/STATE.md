# P2-FORMS STATE (process v3 pilot)  base=p2/v3-forms  plan=docs/build-spec/process-v3.md
Earlier rounds (v2 board, decisions D1-D39, SEC, OPEN): `STATE-v2.md`. Merged before the pilot: S1 S2 S2w S3 CR1
S7c W1 T01 T02 T03 T13 T14 I02 I03 B1, and P2-IP PERF1.
## BOARD  unit wave state review commit note
P1  1 disp f+sec - per-row hidden check; tests/perf budget
P0  1 rev  f+sec 8464bfc8 tl report, 17 reports; scaffold.view ruling; reviews running
P2  1 mrg  f     83e7a512 gate-changed (2 heavy slots), commit-check; 1 CR round
F1a 2 todo f     - generator, routes, tl form, demo 1-3 5 7 8; owns shared files
P0b 2 todo l     - report registrations for the other modules (spec from P0)
F1b 3 todo f     - TUI log + runner; clause 11
F1s 3 todo f+sec - form sources quality+permits; clause 6
F2  4 todo f     - MCP, draft resume, walks; clause 4
F3  4 todo f     - web fill page + cards; clause 9
F4  4 todo f+sec - intake signed-in; clause 10
F5  5 todo l     - docs, runbook, tour, highlights
## BASE-RED (on p2/v3-forms, not caused by a unit)
hidden_sql world lacks scaffold rows (P1 fixes) | awp proposable exclusions stale (F1a fixes) | wheel count 27 vs 21 (DEFERRED)
## OPEN
Q9 S6 public route: owner gate (out of the pilot)
Q10 record keys come from one sequence per project, so a hidden record leaves a gap in every list read and report (P0 sec F2; pre-existing, platform-wide): accept as a documented limit, or a rule? needs owner
## DEC
D40 2026-11-17 owner Q7: privileged forms hidden from all but the author (CR1 behaviour kept; no clearance table); F1a walk proves it
## METRICS (for V3-PILOT.md)
start 2026-11-17 wave 1 dispatched; handoffs 8 (3 dispatch, 4 resume, 1 re-review); rulings 4 (P1 lock wait, P2 Q1-Q3, P2 F8 rejected, P0 duplicate gate); late surprises 0
lessons: one heavy lock serialised light runs (fixed in P2: 2 slots, dev/tests unlocked); P0 walk tests slow on the pre-P1 base
