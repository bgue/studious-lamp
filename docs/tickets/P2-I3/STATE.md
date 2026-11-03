# P2-I3 STATE  r=7 base=1b93a13 C=2 ck=0 gate=n/a wt=/home/user/wt/p2-i3
## BOARD
S1 p mrg f 485f3b4 schema merged; APPROVALS logged
S2 p mrg f af76b84 package + pins; e543b97 adds tl-mod-legacy dep + uv.lock; C1 done
T01a t mrg l 8aa58ed samples (50 items, 9 locations, 15 PO lines), 26 checks
S3 p mrg f 658c452 receipts, movements, actions, commands, tl_api glue; b21676a; 2s accepted by orch
T01b t mrg l 6b3e9c7 loaders mat-*; merge 3da7b71 (p2/i3 head at r4 start), ck0
S4 p mrg f f114592 mto target + documents extension points; orch ratified esc (D22, D24); APPROVALS logged
T03 t mrg l 6004b0e readiness (subject only); defaults kept (Q7)
T04a t mrg f bad05ef 9 GET routes; 10 agent pins; MaterialItemView rename; APPROVALS logged; C2 reached
T04b t mrg f b1cbd75 client methods + materials_command + fake (e64703a); ck0
T05a t mrg f 60b4c77 reports.py (6 reports, CSV) + report route (261067d); ck0
T05b t mrg f 7c559df CLI reads (9 verbs + report); merge cdbd388; sign fallback, loc header accepted (D35)
T05c t stg f - CLI write verbs (receipt receive, move, reserve, mto assign); r8: needs mat.py quoted
T05d t stg f - CLI reads of S5: mto show (detail), item projects; r8
T06a t mrg f d0971d6 materials_text.py; 2s accepted; merge 0503ef0 (47d76c3 + fix, D35)
T06f t disp f - StockScreen + MovementLogScreen (unregistered); T06f-stock-screens.md; p2/i3-t06f-stock-screens
T06g t stg f - materials_text For (movement, lot reservations) + receive sign (D35); r8, after T06f mrg (same screens)
S5 p mrg f 08ee349 view keys + 2 GET routes; merge 46e96e7; APPROVALS 9d13710
T06b t disp f - receipt_text.py + ReceiptLogScreen; T06b-receipt-log.md; p2/i3-t06b-receipt-log
T06c t stg f - item_text.py + ItemLibraryScreen (+ Projects table); r8
T06d t disp f - mto_text.py + MtoLinesScreen (+ Reservations, Open receipts); T06d-mto-lines.md; p2/i3-t06d-mto-lines
T06h t stg f - location_text.py + LocationScreen (split from T06c, D36); r8
T06e t stg f - receipt_entry_text.py + ReceiptEntryScreen; after T06b mrg
T07 t mrg f 3f8599c nine MCP reads + propose_reservation; MATERIALS_MCP_ACTIONS (a38d5a3); APPROVALS 01ba7bc
T08 t stg l - sim MaterialsDesk + actor; deps mrg; ticket r8 (needs sim files read)
T11 p todo f - tests + mutants of S1-S4; at C3 (Sonnet). T09 demo (needs P2-I1 merged); T10 docs lite
## DEC
D1 2026-11-01 owner policy: tests at T11 (C3), pieces leave dev/accept/P2-I3/<id>.py + smoke, no pytest, no security review, tour at C4
D2 2026-11-01 UOM: S1 adds code list StockUom (EA SET BOX ROLL L m kg lb m3) to co.acme.materials@1.0.0; UnitOfMeasure has no EA (Q1 answered by orch)
D3 2026-11-01 code lists fixed in S1: ItemCategory 15, LocationKind 5, ConditionCode 4, MovementReason 7; samples paste the same lists
D4 2026-11-01 T01 split T01a samples / T01b loaders; ticket total 16, no PLANCHK
D8 2026-11-01 S2: stored `available` (projector writes on_hand-reserved); quantities Decimal in code (no SQL arithmetic)
D10 2026-11-01 RecordPoLine auto-adopts the ProjectItem; one root per project; ReviseLocation cannot re-parent
D13 2026-11-01 S2 review accepted: hand-written load targets; tl-mod-legacy dep; underscore target names materials_item_master/_location/_po_line
D14 2026-11-01 F4 glue (MATERIALS_COMMANDS, error rows, API_COMMANDS_OF pin) landed inside S3; now on p2/i3
D15 2026-11-01 four MTO error classes already in materials errors.py (S4 adds no ServiceError)
D17 2026-11-01 T01b mapping text kept as constants in loaders/materials.py (no mappings/ dir)
D19 2026-11-01 merge notes: openapi lives at docs/reference/openapi.json (regenerate after S4 and T04a, `python -m tl_api.openapi`); S3 RULES reads S4's MtoRule rows by shape
D20 2026-11-02 r4 orch accepted S3 2s (subjects not rewritten; rules.py waived; receipt line item must equal PO line item = rule) and T01b esc (include_confidential to bronze ok: materials sources carry no class; raw system count in dev script ok)
D21 2026-11-02 r4 S3 F3 LO (receipts missing_mtr filtered after LIMIT) was already fixed in SQL at 658c452 (S3 report 2a): nothing left for T04a. F3-info (mto_lines short_only scans all lines before limit) is a one-line report note in T04a; views.py untouched (D8 forbids SQL arithmetic)
D22 2026-11-02 r4 orch APPROVES the documents change under P2-Q10 (interface change; APPROVALS line at merge): S4 spec decision 5 = (a) optional reverse hook on PublishTarget used by publish.py compensation, (b) check_mapping accepts any publish_targets() name, mapping fields from the target, (c) schemas.py target_kind str. Generic, no materials import in documents. Replaces D16/Q4
D23 2026-11-02 r4 T04a guard is `document.read` (as routes/cost.py), not a new action: `materials.view` is the read role and AGENT_ACTIONS lives in tl_core.auth. Five-reader walk over classified materials records goes to T11 (D1); T04a only raises MIN_ROUTES and proves plumbing (no viewer passed)
D24 2026-11-02 r4 batch S4 + T03 + T04a: T03 and S4 both add a pyproject table (readiness_checks / publish_targets): keep both at merge; S4 and T04a both regenerate docs/reference/openapi.json: regenerate at merge. T05 waits for S4 (reports and mto verbs); T07 and T04b follow T04a
D25 2026-11-02 r5 screen text lives in Textual-free tl_tui/<x>_text.py modules (materials_text, receipt_text, receipt_entry_text, item_text, location_text, mto_text); no details/materials.py; contracts in text-contracts.md; web twins T12-T14 import them
D26 2026-11-02 r5 views carry ids, not keys, for movement For, lot reservations For, received_by, per-line reservations, per-project item quantities: those columns/sections deferred in the text contracts (Q6)
D27 2026-11-02 r5 T07 exports MATERIALS_MCP_ACTIONS; server.py call and identity.py MCP_ACTIONS lines are registry glue (supervisor, after P2-I1 merges); T07 acceptance uses a local authorizer hook
D28 2026-11-02 r5 T05 split T05a reports+route / T05b read verbs / T05c write verbs; ticket total 18 (was 15 in spec, 16 at D4), same slot, no PLANCHK
D29 2026-11-02 r5 S4 open questions accepted: republished take-off key -2 (voided keys stay taken), takes_provenance False; T11 pins both. T03 subject form accepted unrewritten
D30 2026-11-02 r6 T05a answers: movement_log By = actor; heat_trace MTR = last mtr-slot file; deviations 2-4 (leading | quoted, 422 on bad heat/date, missing receipt = no MTR) accepted
D31 2026-11-02 r6 Q6 YES (orch): S5 builder piece (public-interface change fails 01-tiers 6 item 6). New fields default so T06a/T07/fakes stay valid; new views_detail.py (MtoLineDetailView, ItemProjectView, OpenReceiptView); routes mto-line?key= and item-projects?code=; T06b-e carry the columns, T06g the movement/lot For; T05d the CLI. Ticket total 22 (was 18), same slots, no PLANCHK
D32 2026-11-02 r6 T04b/T07 ask to declare tl-mod-materials in tl-tui and tl-mcp pyproject: registry glue with uv.lock at M4 merge (NEXT 4), not a ticket
D33 2026-11-02 r6 T07 propose_reservation scans mto_lines to MAX_VIEW_ROWS; accepted until a ticket swaps in mto_line_detail (S5). T04b ticket gate path is tests/api/test_client_roundtrip.py
D34 2026-11-02 r6 T05c, T06b-g, T08 not staged as files: tickets quote interfaces verbatim from the tree, so they are written at r7 after T06a/T05b/S5 merge (weekly capacity)
D35 2026-11-03 r7 rulings on the r6 reports: T06a KIND_WORDS keyed by ledger kinds (receive = Receipt) kept; Lot cell heat else lot key kept; empty notes `No stock on hand`/`No movements` kept; receive rows (direction None) get a sign by kind as `tl mat movements` does (receive, return +; issue, scrap -; else unsigned), built in T06g; T05b loc header `locations: <n>` and movement sign fallback kept; `movements --kind` unknown returns zero rows (T11 pins)
D36 2026-11-03 r7 every text module ticket ends with its read-only LogScreen in widgets/ (unregistered), acceptance pushes it on TlApp over a copy of .accept/p2-i3.db and saves SVGs to .accept/shots/<id>-<w>.svg (owner screenshots before C4); T06c split: T06c items, T06h locations (5-file limit); stock and movement screens are T06f; ticket total 23. Contract: text-contracts.md "Screens"
D37 2026-11-03 r7 S5 question: ItemProjectView.title stays the project id until a project record carries a title; the item panel Projects table column is `Project` (the id); D26 deferrals lifted in text-contracts.md (movement and lot For, received_by, Projects table, MTO Reservations and Open receipts)
D38 2026-11-03 r7 T06a left the superseded 47d76c3 in history (merge 0503ef0 carries both); no rewrite. Batch r7: T06f + T06b + T06d (screens first, disjoint widgets, one workflow); T06c/T06h/T06g/T06e/T05c/T05d/T08 staged for r8-r9 in that order
## SEC
(none; Sec rows S1-S4, T03, T04a, T07 recorded in spec §9, review only if the owner asks)
## OPEN
Q3 RejectReceipt user vs superuser: spec default user (owner decisions 15); no action needed owner raised spec §11
Q5 S3 report asks: reserve check is literal `reserved + qty <= line qty` (issued not added) while coverage counts both; `by_module` loosens nothing; Adopt on an ItemMaster is a project word at company scope, so a plain user is never offered it (row may belong on ProjectItem). Defaults kept; T11 pins them; veto needs orch raised S3
Q7 T03 defaults kept: no planned_start means blocked; a fully received PO line still promises its item; T11 pins both; veto needs orch raised T03
## NEXT
1. Orch: one ticket-batch-v2 workflow of T06f, T06b, T06d (all review full; disjoint widgets and text files; branches from the r7 state commit). Merge order free. Collect the SVGs in .accept/shots/ for the owner (T06f-stock-*, T06f-movements-*, T06b-receipts-*, T06d-mto-*).
2. r8 after those mrg: write and dispatch T06c (items), T06h (locations), T06g (For + receive sign; edits materials_text.py only, after T06f so the screens exist to screenshot); then T06e after T06b; T05c and T05d (quote tl_cli/mat.py, mat_read.py); T08 (read sim files). Each quotes interfaces from the tree.
3. r9 or r10: T11 tests piece (C3). Tests must RUN: `just gate <touched test dirs>`. Scope: spec §9 tests list, mutant guards in the S2/S3/S4/S5 reports, five-reader walks over T04a/T05a/T07/S5, T06 text modules (packages/tl-tui/tests/test_{materials,receipt,mto,item,location}_text.py), CLI tests packages/tl-cli/tests/test_cli_mat_*.py, pins D29/Q5/Q7/D35.
4. T07 may swap its mto_lines scan for mto_line_detail via a small ticket (D33).
5. Registry glue by supervisor, last, after P2-I1 merges: add_typer for tl mat, MCP_ACTIONS from MATERIALS_MCP_ACTIONS, register_materials_tools in server.py, nav entries and keys for the six screens (Stock, Movements, Receipts, Items, Locations, MTO lines), pinned lists, tl-mod-materials in tl-tui and tl-mcp pyproject (D32); regenerate, uv lock.
6. C4: demo P2-I3 sqlite+pg incl. the M3 clause, tour once (screens registered by then). T09 demo (needs P2-I1 merged), T10 docs lite.
7. Seed ledger .accept/p2-i3.db is built by dev/accept/P2-I3/S3.py --keep (untracked, gitignored, ~2m15s; the worktree has none now: every T06 acceptance starts with it); rebuild after a schema change.
## REFS
Spec docs/build-spec/specs/m4-materials.md §9 (table), §10 (demo). Reports: docs/reports/P2-I3/{S1,S2,S3,S4,S5,T01a,T01b,T03,T04a,T04b,T05a,T05b,T06a,T07}.md.
S5 guards for T11: views.py:756 (received_by filter, equivalent to the t.id check: test the hidden receipt raises), views_detail.py:177 (hidden-project filter), :42 (open-receipt states, used at :130). Screens: widgets/tag_register.py is the precedent; LogTable has no right-align hook.
Mutation guards for T11: S2 limits.py:27, handlers/locations.py:172 and :244, targets.py:342, projectors/stock.py:216 and :211; S3 handlers/receipts.py:850 (MTR), handlers/movements.py:389 (negative balance), :449 (reserve over line qty), :385 (consumable cost code), commands.py:104 (word of AdjustStock); S4 guards listed in its spec.
S3 facts: receipt commands take stream_id (+expected_version for Accept); `Movement` has from_location/to_location codes; Accept needs state Inspected; `RULES` rows read by shape (record_type|type, condition, label, command|command_name, word); `Rule` lives in actions.py; ids for MTOLine samples are 27 chars (fixtures only).
Seed ledger facts: project:P123, receipt P123-RCPT-0001 (heat H-7781, MTR attached), lots @1 @2, MTO ISO-1234@A/MTO 3 lines for awp.CWP P123-CWP-PIP-0001, actors user:materials-super, user:plain.
Tickets this round: docs/tickets/P2-I3/{T06f-stock-screens,T06b-receipt-log,T06d-mto-lines}.md; screen contracts text-contracts.md (r7: D26 lifted, Screens section). Reports S5, T05b, T06a merged. Reports T04b, T07, T05a, S4, T03, T04a in docs/reports/P2-I3/. Every item: setup uv sync --all-packages, NODE_OPTIONS=--max-old-space-size=6144 just check, acceptance script, no pytest except T11; subject P2-I3-<id>: ...
Security sweep per D1/spec §9 only if the owner asks; T04a/T07/T05a walks over classified records are T11's.
## TRAPS
T06a second attempt added a commit instead of amending (fine). A text module that imports a widget leaks textual: acceptance checks sys.modules in a fresh subprocess. LogScreen.keep_columns keeps a `State` column by default: logs without one override it. `.accept/` is empty in a new worktree: S3.py --keep first.
New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144 (both in every acceptance). Worktree /home/user/wt/p2-i3 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background it. Do not rm -r dev/accept (tracked W0 scripts). P2-I1 and P2-WEB1 run beside: registries (tl_api/{auth,app,commands}.py, pyproject.toml, uv.lock, docs/reference/openapi.json) regenerate on merge, M4 merges last. A load target name cannot hold a dot. SQLite returns NUMERIC as float: read Decimal(str(x)). A reused worktree keeps its old base: check `git rev-list --left-right --count p2/i3...HEAD` before starting (p2/i3-s4-mto is behind by S3, T01b). A new dir under packages/tl-modules/ without a pyproject.toml breaks every uv run. A SQLite open_uow takes BEGIN IMMEDIATE on entry (barrier before the with). `bronze` needs include_confidential and a LakeConfig for internal runs. A new entry point is invisible until `uv sync --all-packages`. A base merge can add an undecided agent action: run test_auth_review after each. Two view models with one class name in different modules rename each other in openapi: use distinct names. views.MAX_VIEW_ROWS is pyright-private: import limits.MAX_VIEW_ROWS.
