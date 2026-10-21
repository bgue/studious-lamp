# P1-UX2 STATE  r=1 base=b57c20b C=C0 ck=0 gate=n/a wt=/home/user/wt/p1-ux2
## BOARD
S1 p disp f - allowed-actions query + client file/command methods
S2 p disp f - LogScreen, ActionFormScreen, "Log screens" README
T01 t disp f - image_protocol(env) pure fn; provided test
T02 t disp f - file_text helpers; provided test
S3 p todo f - migrate 7 logs, wire actions, code labels; needs S1 S2
S4 p todo f - documents log, preview/, Files tab, deps; needs S1 S2 T01 T02
S5 p todo f - RFI narrative + timeline in details/; needs none
S6 p todo f - demo, tours, section 24; needs S3 S4 S5
## DEC
D1 2026-10-21 ModuleSpec.actions hook (additive), holds(level) = authorizer decision; ADR-0010 addendum by S1 (README D1)
D2 2026-10-21 server returns command+label; key/form table lives in TUI (log_actions.py in S3, own table in S4)
D3 2026-10-21 Haiku only T01/T02; all tl-tui work review: full (orchestrator r1)
D4 2026-10-21 PDF render in child process, timeout + size/pixel/memory caps, cache by sha256 (hostile PDFs crash native lib)
D5 2026-10-21 owner: viewer + thumbnail; pypdfium2 5.14 + textual-image 0.14 (pillow 13); licence check gates; top/bottom, right at 160+
D6 2026-10-21 raw code labels fixed in labels_load/display (S3 only owns both); schema/** never edited by these pieces
D7 2026-10-21 client interface additions all in S1 (allowed_actions, list_record_files, fetch_file, document_command, engineering_command)
D8 2026-10-21 plan check not asked: 8 items, under the ~10 limit
## SEC
(none yet) rows to review at DONE, range b57c20b..head: Sec1 allowed-actions query; Sec2 open/preview path (README)
## OPEN
Q1 ADR-0010 addendum for ModuleSpec.actions is written by S1 as proposed; orchestrator may want ADR review needs orch raised r1
## NEXT
1. Merge wave 1 passes (S1, S2, workflow T01+T02); check board vs git log.
2. Round 2: write wave 2 dispatch S3, S4, S5 (specs ready, status draft: flip to ready, add exact interface lines from merged S1/S2).
3. Before dispatch re-check: S3 and S4 both edit keymap.py and test_snapshots; S4/S5 both touch record_view.py (S4 tabs, S5 Details renderer).
4. Wave 3: S6 after S3 S4 S5. Then orchestrator: whole gate, gate-pg touched dirs, demo, 2 sec reviews (Sec1, Sec2).
5. If S3 hits two strikes: split by area (product logs / ops logs), do not retry whole.
## REFS
Specs docs/tickets/P1-UX2/S1..S6-*.md, T01-image-protocol.md, T02-file-text.md; provided tests docs/tickets/P1-UX2/provided/ (copy byte-identical)
Scope SCOPE.md; plan README.md; prior art docs/reports/P1-UX.md, docs/tickets/P1-UX/S2-record-screen.md
Survey: widgets/{document_register,record_screen}.py; commands access in module commands.py (user|controller|admin) and tl_api/commands.py action_for;
correspondence guards.py/handlers require_state; embedded _controller_gate; tl_api routes/files.py; dev/tools/check_licences.py (installed dists)
## TRAPS
Nothing run (docs only). PyPI reachable via proxy (uv pip install --dry-run resolved the three deps). check_licences reads installed dists: S4 must install first.
keymap.py and snapshots are shared by S3/S4: generated-file conflict at merge is regenerated (Code 131).
