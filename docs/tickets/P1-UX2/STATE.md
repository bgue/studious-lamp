# P1-UX2 STATE  r=final base=b57c20b C=C4 ck=0 gate=n/a wt=/home/user/wt/p1-ux2
Read first: docs/reports/P1-UX2.md (final report), SCOPE.md. Branch p1/ux2 plus p1/ux2-s6-demo-tours (S6 awaits merge). Built; the whole-suite run is the last open step.
## BOARD
S1 p mrg f d9b3a26 allowed-actions query + client file/command methods
S2 p mrg f c73ff96 LogScreen, ActionFormScreen, "Log screens" README
T01 t mrg f 6093bb8 image_protocol(env)
T02 t mrg f c69cb4d file_text helpers
S4 p mrg f 199b74a documents log, preview/, Files tab, deps (rich-pixels, D9)
S5 p mrg f 7ea83f0 RFI narrative + timeline
S3 p mrg f 3b4d76a every log on LogScreen, actions wired, code labels (D10)
S6 p done f - demo 4/4 on SQLite and Postgres; tour-all x2 clean; section 24 (branch p1/ux2-s6-demo-tours)
## DEC
D1 2026-10-21 ModuleSpec.actions hook (additive), holds(level) = authorizer decision; ADR-0010 addendum by S1
D2 2026-10-21 server returns command+label; key/form table lives in TUI (log_actions.py in S3, own table in S4)
D3 2026-10-21 Haiku only T01/T02; all tl-tui work review: full
D4 2026-10-21 PDF render in child process, timeout + size/pixel/memory caps, cache by sha256
D5 2026-10-21 owner: viewer + thumbnail; pypdfium2 5.14 + rich-pixels 3.0.1 (pillow 13); licence check gates; top/bottom, right at 160+
D6 2026-10-21 raw code labels fixed in labels_load/display (S3 only owns both); schema/** never edited
D7 2026-10-21 client interface additions all in S1
D8 2026-10-21 plan check not asked: 8 items, under the ~10 limit
D9 2026-10-22 textual-image is LGPL-3.0-or-later (S4 stopped): owner approved rich-pixels 3.0.1 (MIT); one allow-list entry in check_licences.py
D10 2026-10-22 S3 paths widened: list_code_lists(scope) read into labels_load so plain logs show words, technical keeps codes
D11 2026-10-22 owner process: no security reviews for this increment; testing deferred to one whole-suite run at the end
## SEC
Not run (owner, D11). Open rows: Sec1 allowed-actions query; Sec2 open/preview path.
## OPEN
Q1 whole-suite `just gate` and `just gate-pg` on the merged branch: <<fill>> in docs/reports/P1-UX2.md
Q2 follow-up 1 of the report: LogScreen table caches (a one-line product fix), owner or orchestrator to decide
## NEXT
1. Merge p1/ux2-s6-demo-tours into p1/ux2.
2. Run the whole suite once (`just gate`, then `just gate-pg` on adapters and ledger paths); fill the two rows in the report.
3. Merge p1/ux2 to trunk; update docs/memory/STATUS.
## REFS
Specs docs/tickets/P1-UX2/S1..S6-*.md, T01, T02; reports docs/reports/P1-UX2/*.md and P1-UX2.md; tour section 24 of docs/reports/PHASE-1-TOUR.md
## TRAPS
Four container restarts: resume a lost run from its last commit (L-P1-UX2-2). A Textual DataTable can keep header-wide columns until reload (report follow-up 1); tourkit.fit_tables hides it in the tour only.
