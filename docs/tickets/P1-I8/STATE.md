# P1-I8 STATE  r=5 base=79f2bcf C=C4 ck=0 gate=pass wt=/home/user/wt/p1-i8-report
Read first: docs/reports/P1-I8.md (the increment report), FANOUT.md, README.md. Branch p1/i8 @79f2bcf; report branch p1/i8-report (docs only, off 79f2bcf).
r5 wrote the report, learnings L-P1-I8-13..15, README and AGENTS updates (tl-cli, tl-tui, root AGENTS) and a runbook section. No code, no suite.
## BOARD
S1 p mrg f 2023370 classify
S2 p mrg f 0404c94 schemareg module
S4 p mrg f 3d007e5 lake silver, readable-set rule
S5 p mrg f 72559cd plumbing: views, routes, client, fakes
S6 p mrg f c65c7ab legacy framework, reserved prefixes
S9 p mrg f cdfb5ab conformance dashboard, waived apart
S10 p mrg f 3079582 export/import hardening, merge 79f2bcf
T03 t mrg f 07c7bb7 impact report
T08 t mrg l 3fb9c0a lake marts
T05a1 t mrg f 38049fa package report commands
T07a t mrg l 31e272f dms-register loader
T05a2 t mrg f 538cdff publish, adopt, drift
T07b t mrg l c45de16 tag-list loaders
T05a3 t mrg f 89c1e20 waiver CLI
T05a4a t mrg l - crosswalk
T05a4b t mrg f 8a7ee4d export-git, company scope, dup-target refusal
T05a4c t mrg f 30d276d import-git
T04a t mrg f - workbench screen, Ctrl+O
T04b t mrg f d136c1a review screen
T09a t mrg l d002b41 demo clauses 1-4
T09b t mrg l 95a1b1e demo 7/7 2a
T10 - orch - phase report; orchestrator
## DEC
D1-D23 see FANOUT.md and the report (packages, roles, pins, gates, waivers, load runs, bronze, security list, not built, S9, crosswalk, export/import, workbench, demo split).
D24 2026-10-20 Q3 (orch): webhooks deliver catalog events by subscription; the exit chain subscribes to the derived-publish events, no rule.
D25 2026-10-20 T05a4b F1 scope (orch): export-git company scope only, refuses a duplicate target.
D26 2026-10-20 T09b five questions (orch): after compensate the plan shows the 3 existing; lake built for the lowest reader; reorder; status-count delta; XER steps from P1-I4 demo.
## SEC
First review (9928c45): F1 HI, F2 HI, F3-F6 MD fixed, recheck P at c5733e5; F7 LO accepted; F8 LO fixed; F9 LO closed by design.
Final review (c5733e5..2cf4f3b): F1 MD export temp followed a link; F2 LO export paging; F3 LO import TOCTOU; F4 accepted. S10 fixed@3079582, merged 79f2bcf.
Residual LO: TagTarget ignores run class (tags carry no class) = follow-up.
## OPEN
none. Gate cells marked <<fill>> in the report (part 4, gate-pg, demo on merged tree): the orchestrator fills them from the reruns on 79f2bcf.
## NEXT
1. Orchestrator: merge p1/i8-report into p1/i8, fill the <<fill>> cells, then merge p1/i8 to trunk.
2. Orchestrator: STATUS.md line, APPROVALS, phase report (T10), risk register (roles, line list class, promote).
3. Follow-ups are listed in docs/reports/P1-I8.md; A1-A3 tools come after the Phase 1 exit.
## REFS
Report: docs/reports/P1-I8.md. Ticket reports: docs/reports/P1-I8/. Tools and references: docs/tickets/P1-I8/refs/.
## TRAPS
One heavy pytest at a time, own --basetemp, never /tmp/pytest-of-root, never pkill. Run packages one per process (OOM). Split the DONE gate per part in the background (L-P1-I8-14). test_int_inbound_worker flakes under load (112).
