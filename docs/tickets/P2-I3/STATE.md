# P2-I3 STATE  r=11 base=8142349 C=2 ck=0 gate=n/a wt=/home/user/wt/p2-i3
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
T05c t mrg f 453af44 CLI writes; merge 7dc889d; adjust --direction; rev pass; receipt lookup before gate viewer-filtered accepted
T05d t mrg f e444c09 mto show + item-projects; merge 8e6f89c; `T05d:` subject kept
T06a t mrg f d0971d6 materials_text.py; 2s accepted; merge 0503ef0 (47d76c3 + fix, D35)
T06f t mrg f 33af41d StockScreen + MovementLogScreen; merge fedd934; rev pass; D41
T06g t mrg f 1f7ef4a For columns + receive signs; merge c464f6a; subject T06g: kept (D45)
S5 p mrg f 08ee349 view keys + 2 GET routes; merge 46e96e7; APPROVALS 9d13710
T06b t mrg f 922a711 receipt_text + ReceiptLogScreen; MTR line (D39); merge dbcb4f9
T06c t mrg f c3610f1 item_text + ItemLibraryScreen; merge edb6055; crumb fix in T06e (D45)
T06d t mrg f 641051a mto_text.py + MtoLinesScreen; merge 2046d54; rev pass; D41
T06h t mrg f 4a91f61 location_text + LocationScreen; merge 423b515; D45
T06e t mrg f cc81803 receipt entry + Company crumb; merge 7a7f4c1; Delete key; no MTR upload (D42)
T07 t mrg f 3f8599c nine MCP reads + propose_reservation; MATERIALS_MCP_ACTIONS (a38d5a3); APPROVALS 01ba7bc
T12 t stg f - sim MaterialsDesk + actor; T12-sim-desk.md; disjoint from T06j (tl-sim); merge before T11 (D49)
S6 p mrg f 05b1f13 client attach_record_file; merge a2a6502; embedded.py import conflict resolved by orch
T06i t mrg f 63eb4ef cursor, KEYS style, amber Note; merge addf25a
T08 t disp f - demo; r2 esc@b822444 decided D48; r3 running (wf, same branch); T08a mrg 79f87ec (tl load --company)
T11 p stg f - tests + 6 mutants; gate RUNS tests; T11-tests.md; after S6, T06i, T08 (C3)
T06j t stg f - MTR upload in ReceiptEntryScreen; T06j-mtr-upload.md; extends T06e.py
T13 t stg f - registry glue (was NEXT 5); T13-registry-glue.md; after T06j (D50)
T10 t todo l - docs lite, after T11
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
D39 2026-11-03 r8 T06b esc (fake Files row for the MTR note) decided (c): plain amber line `MTR required to accept` before the Files table, no fake row; section note `No files`. Recorded in T06b Decision and text-contracts.md Receipts bullet
D40 2026-11-03 r8 glue 9bc864b: tl_cli.main mounts `mat` (tl mat reads were unreachable); tl_tui commands.py + app.py get keyless palette entries Stock, Movements, MTO lines (action_stock/_movements/_mto_lines via one helper). Keys, nav panel, keymap rows, receipts/items/locations entries stay with NEXT 5 (P2-I1 and P2-WEB1 edit the same registries; screenshots come from the acceptance scripts, which push the screens on TlApp)
D41 2026-11-03 r8 rulings: T06f (movement `k` filters the rows read, `h` on a row without heat is a no-op, empty Labels() on both screens, commit subject form) and T06d (Document/Revision parsed from the line key, filter text in the summary, failed detail text, labels ignored) accepted. Proposed learning: LogScreen._draw_actions always offers `[Enter] Open record` (can_open=True) on a read-only log; leave until the record screens (web twins)
D42 2026-11-03 r9 ClientInterface has no file upload (no register/complete upload; ApiClient has it, EmbeddedClient only reads files), so T06e saves CreateReceipt and does not attach the MTR; its status line says to attach on the receipt (tl file put, slot mtr). Needs a small builder piece S6 (client upload method on ClientInterface, EmbeddedClient, ApiClient, fake) before T09; raised as Q8
D43 2026-11-03 r9 preview `tl mat receipt ls --project P123` exit 2 = unknown verb: the T05b verb is `list`, and every other tl group says `ls`. Glue in mat.py adds `ls` aliases for receipt and mto (list stays); T05d acceptance checks both
D44 2026-11-03 r9 glue: palette entries Receipts, Items (company level when no project), Locations (app.py _push_materials, commands.py); mat_write.py and mat_detail.py stubs (register no-op) called from mat.py so T05c and T05d own disjoint files
D45 2026-11-03 r9 rulings on r8 reports: T06g subject `T06g:` kept, no rewrite (blocked question answered: accept); T06h missing-parent reading (names the direct parent, stops) and literal `1 lots` kept; T06c Category shows humanized code (labels=None) kept, `used in 0 projects` on a failed read kept; T06c breadcrumb becomes `Company` (T06e one-liner); T06b amber styling stays plain (Q9)
D46 2026-11-03 r10 Q8 YES: builder piece S6 (client attach_record_file); a follow-up ticket T06j wires the MTR upload into the entry screen after S6 merges. Q9 YES: T06i adds layout.Note (amber) used by the receipt MTR line. Demo ticket takes id T08 (orch); the old sim ticket is T12, unscheduled; diff over 400 accepted for T08 (shell + driver)
D47 2026-11-03 r10 LO rulings: T06e cursor jump and KEYS style go to T06i (KEYS becomes `Del remove line`, sibling style; docs glue first set to `[Del] Remove line` as asked, T06i updates text-contracts); T06e refusal-path check goes to T11 part C; T05c viewer-filtered receipt lookup before the gate accepted. Glue: T06e ticket and text-contracts no longer say Ctrl+D
D48 2026-11-04 r11 T08 r2 esc rulings (orch): F1 HI DefineItem really accepted (a), clause 10 = 51; F2 MD clause 11 asserts from/to/by; F3/F4 LO; retry notes in T08-demo.md. p2/i1 merged into p2/i3 (Q10 awp path); T08a added --company to tl load run verbs
D49 2026-11-04 r11 T12 may run beside T06j (tl-sim vs tl-tui, no shared file), not beside anything touching dev/demos; it must merge before T11 (T11 gate includes tl-sim). Mirrors WorkfacePlanner
D50 2026-11-04 r11 registry glue is Haiku ticket T13 (full), not supervisor work: serial after T06j (both edit tl-tui; T13 edits app.py/keymap). Ticket total 26
## SEC
(none; Sec rows S1-S4, T03, T04a, T07 recorded in spec §9, review only if the owner asks)
## OPEN
Q3 RejectReceipt user vs superuser: spec default user (owner decisions 15); no action needed owner raised spec §11
Q5 S3 report asks: reserve check is literal `reserved + qty <= line qty` (issued not added) while coverage counts both; `by_module` loosens nothing; Adopt on an ItemMaster is a project word at company scope, so a plain user is never offered it (row may belong on ProjectItem). Defaults kept; T11 pins them; veto needs orch raised S3
Q7 T03 defaults kept: no planned_start means blocked; a fully received PO line still promises its item; T11 pins both; veto needs orch raised T03
Q10 closed r11: p2/i1 merged, T12 scheduled (D49)
## NEXT
1. Orch: T08 r3 result (wf running). Then batch A: T06j + T12 (disjoint: tl-tui | tl-sim; review full each), no T08 overlap needed. Then T13 alone (serial after T06j merge; uv.lock, registries).
2. T11 (piece, spec ready) after T08, T12, T13 merged: tests RUN, `just gate <dirs>` + `just gate-pg packages/tl-modules/materials`, 1 sentinel + 5 mutants; adds test_materials_coordinator.py. Then C3.
3. T10 docs lite after T11 (write at the round that stages it; load throughline-docs).
4. T07 may swap its mto_lines scan for mto_line_detail via a small ticket (D33).
5. C4: `just demo P2-I3` sqlite+pg (T08), tour once (screens registered by T13). Increment report, README/AGENTS.md updates in the DONE round.
6. Seed ledger .accept/p2-i3.db is built by dev/accept/P2-I3/S3.py --keep (untracked, gitignored, ~2m15s; a new worktree has none: every acceptance starts with it); rebuild after a schema change.
## REFS
Spec docs/build-spec/specs/m4-materials.md §9 (table), §10 (demo). Reports: docs/reports/P2-I3/{S1,S2,S3,S4,S5,T01a,T01b,T03,T04a,T04b,T05a,T05b,T06a,T07}.md.
S5 guards for T11: views.py:756 (received_by filter, equivalent to the t.id check: test the hidden receipt raises), views_detail.py:177 (hidden-project filter), :42 (open-receipt states, used at :130). Screens: widgets/tag_register.py is the precedent; LogTable has no right-align hook.
Mutation guards for T11: S2 limits.py:27, handlers/locations.py:172 and :244, targets.py:342, projectors/stock.py:216 and :211; S3 handlers/receipts.py:850 (MTR), handlers/movements.py:389 (negative balance), :449 (reserve over line qty), :385 (consumable cost code), commands.py:104 (word of AdjustStock); S4 guards listed in its spec.
S3 facts: receipt commands take stream_id (+expected_version for Accept); `Movement` has from_location/to_location codes; Accept needs state Inspected; `RULES` rows read by shape (record_type|type, condition, label, command|command_name, word); `Rule` lives in actions.py; ids for MTOLine samples are 27 chars (fixtures only).
Seed ledger facts: project:P123, receipt P123-RCPT-0001 (heat H-7781, MTR attached), lots @1 @2, MTO ISO-1234@A/MTO 3 lines for awp.CWP P123-CWP-PIP-0001, actors user:materials-super, user:plain.
Tickets: docs/tickets/P2-I3/{T06j-mtr-upload,T12-sim-desk,T13-registry-glue,T11-tests,T08-demo}.md. Reports S6, T06i, T08a merged. S6 facts: CreateReceipt result.stream_id is the receipt record id; after Accept only certificate/photo attach; embedded client needs TL_ENV=dev or object_store. Reports T06e, T05c, T05d merged (docs/reports/P2-I3/); screen contracts text-contracts.md (D26 lifted, Screens section). T06e learnings: TlApp binds ctrl+d with priority (check app.py bindings before picking a key); SVG export writes `&#160;` for spaces (grep `Remove&#160;line`). T05c: a controller check needs an account with an explicit module grant (dev ledger gives user: actors only the user word); ForbiddenError text `<Command> needs the <word> access word for <module> on <scope>`. T05d: seed locations are L2 etc., keys have no random suffix: read them from the copy. Every item: setup uv sync --all-packages, NODE_OPTIONS=--max-old-space-size=6144 just check, acceptance script, no pytest except T11; subject P2-I3-<id>: ...
Security sweep per D1/spec §9 only if the owner asks; T04a/T07/T05a walks over classified records are T11's.
## TRAPS
Layout: Section.note shows only when a section has no items; a plain str item carries no colour. Seed P123: no leaf with stock (L2 holds stock, child TC1), 2 receive movements without direction, no reservations (For columns need a client that adds some). Receipt accept needs expected_version = common.version_of(uow, id).
T06a second attempt added a commit instead of amending (fine). A text module that imports a widget leaks textual: acceptance checks sys.modules in a fresh subprocess. LogScreen.keep_columns keeps a `State` column by default: logs without one override it. `.accept/` is empty in a new worktree: S3.py --keep first.
New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144 (both in every acceptance). Worktree /home/user/wt/p2-i3 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background it. Do not rm -r dev/accept (tracked W0 scripts). P2-I1 and P2-WEB1 run beside: registries (tl_api/{auth,app,commands}.py, pyproject.toml, uv.lock, docs/reference/openapi.json) regenerate on merge, M4 merges last. A load target name cannot hold a dot. SQLite returns NUMERIC as float: read Decimal(str(x)). A reused worktree keeps its old base: check `git rev-list --left-right --count p2/i3...HEAD` before starting (p2/i3-s4-mto is behind by S3, T01b). A new dir under packages/tl-modules/ without a pyproject.toml breaks every uv run. A SQLite open_uow takes BEGIN IMMEDIATE on entry (barrier before the with). `bronze` needs include_confidential and a LakeConfig for internal runs. A new entry point is invisible until `uv sync --all-packages`. A base merge can add an undecided agent action: run test_auth_review after each. Two view models with one class name in different modules rename each other in openapi: use distinct names. views.MAX_VIEW_ROWS is pyright-private: import limits.MAX_VIEW_ROWS.

Commit subjects in tickets are `P2-I3-<id>: ...` (r7 runs used `T06x:`; history is not rewritten). Salient T06d fact: seed MTO line keys carry a random 4-hex suffix, read them from the ledger; S5 need_by is always None so Need by is always dropped.
