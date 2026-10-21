# P1-UX STATE  r=final base=2bcedda C=C4 ck=0 gate=n/a wt=/home/user/wt/p1-ux
Read first: docs/reports/P1-UX.md (final report), SCOPE.md. Branch p1/ux @ed025b8 plus the final-round docs commits. Final round: report, learnings, tl-tui README/AGENTS written; no code.
## BOARD
T00 t mrg f 369b72f display helper
S3 p mrg f 6a0c7ae example sets (D12), TYPE_LABELS
S2 p mrg f 16d2e11 RecordScreen, open_record, details registry
T01 t mrg f 4250f0d documents register Enter + plain
T02 t mrg f e4ee157 tag register Enter + plain
T03 t mrg f a09aad7 correspondence register/inbox/clocks
T04 t mrg f 739b084 domain_screen wiring, Enter, RFI Details
T05 t mrg l 806c519 commercial/evidence/RFI text; D30
T06 t mrg f 55a8205 schedule screen Enter + plain
T06b t mrg f ec9af6d compare, activity, look-ahead plain (D37)
T07 t mrg f a3eab29 review queue Enter via target
T08 t mrg f 85ed991 record header, History, context panel (D36)
T08b t mrg f 0f697ef links_tab, thread_tab plain
T08c t mrg f 2a7c34a grid type column + headers (D38)
T09a t mrg f c34c7e5 integration registry plain, no Enter
T09b t mrg f 893dd7d accounts, about:config plain
T09c t mrg f 4007e29 schema workbench and review plain
T09d t mrg f c52873d Enter on schema package rows
T09e t mrg l 34fc72d settings layer words
T10 t mrg f 4793a7c Ctrl+D toggle, help/palette scroll
T11 t mrg f aca2ec5 plain walk test, plain + admin
T11b t mrg f 7b0ce59 carries: Ver, settings kinds, palette refusal, remote hidden
T13 t mrg f e303567 feed pane, header, ref tray plain
S4 p mrg f 8a74f75 demo 4/4, both tours, leak check in tour (D45)
T11c,T12,T12b - abn - - replaced by S4 (D45)
S5 p disp f - final polish (D46); p1/ux-s5-final-polish (wt /home/user/wt/s5)
## DEC
D1 2026-10-21 record screen from a register = modal RecordScreen; Esc dismisses; README.
D2 2026-10-21 Details per type from typed views in tl_tui/details/<area>.py; no new route.
D3 2026-10-21 type labels = LinkML title on record-type classes + generated type_labels.py; humanize fallback.
D4 2026-10-21 new sets in place in fixture 3.2.0 (3.3.0 is the P1-I8 demo draft); additive.
D5 2026-10-21 technical mode = in-memory DisplayMode on the app, admin-only, not remembered.
D6 2026-10-21 GET /schema/forms gains optional record_id; output otherwise unchanged.
D7 2026-10-21 toggle key Ctrl+D, palette "Technical details" (Q3 answered).
D8 2026-10-21 titles + type_labels.py covered by owner approval; orch records APPROVALS (Q2 answered).
D9 2026-10-21 S1 -> ticket T00 (F10): ids/branch renamed T00-display-helper / p1/ux-t00-display-helper.
D10 2026-10-21 DisplayMode lives on the app as `display_mode` (App.display is a Textual CSS prop); mode_of reads it.
D11 2026-10-21 calendar leak pattern is `code@version` (CALENDAR_REF_PATTERN) with a lookbehind so package refs do not double-hit.
D12 2026-10-21 S3: adoption mandatory for sets dropped from project scopes; missing values at most warning.
D13 2026-10-21 admin tools plain by default: token ids, setting seq numbers, svc: actors, joined name@version, Digest lines technical-only; setting keys, workbench Version column, Property/Lint/Diff tabs stay.
D14 2026-10-21 toggle refresh: widgets define `refresh_for_display_mode()`; T10 calls it on all widgets of all stacked screens (errors swallowed). Every screen ticket adds it when its text depends on the mode.
D15 2026-10-21 T09b split: schema part T09c; Enter on package rows is T09d. Accounts, tokens, settings are not records: no Enter.
D16 2026-10-21 History/By column shows the name (actor_label), not the raw actor id.
D17 2026-10-21 help and palette scroll; pinned snapshot asserts became presence checks.
D18 2026-10-21 priority Ctrl+D steps aside in Input/TextArea.
D19 2026-10-21 palette toggle entry is ungated; the refusal lives in DisplayMode.toggle. Plain layer names: Company, Project P123, User.
D20 2026-10-21 record header `v{version}` hidden in plain, shown in technical (record_view.py). In T08.
D21 2026-10-21 clock rows: plain leads with item number under `Item`, technical with clock key under `Clock`.
D22 2026-10-21 registers open records on DataTable.RowSelected, never a priority Enter binding (steals Enter from the filter Input).
D23 2026-10-21 FakeClient.add_stored_record(record_id, key, type, title) registers a record under a module fake's view id so a register row opens it.
D24 2026-10-21 T05 text-only; T04 owns all domain_screen wiring (domain_screen imports commercial_text, evidence_text, rfi_text).
D25 2026-10-21 carry-overs: (a) (c) -> T11; (b) -> T09e (done); (d) (e) -> T08.
D26 2026-10-21 commercial `Status` column dropped in both modes; COMMERCIAL_COLUMNS is 11 wide.
D27 2026-10-21 cell functions default `technical=True` (raw); lines functions default plain. Callers pass labels and mode explicitly. Every later text ticket keeps raw as the default for functions another ticket still calls.
D28 2026-10-21 T03 answers: register Domain has no technical form; clock_line keeps stored state raw; `as Letter` in triage status accepted.
D29 2026-10-21 snapshot plain name `Snapshot N`, technical `CODE#N`; cost lists have no screen.
D30 2026-10-21 T05 accepted: the pin `Cost impact: yes` (plain fact key) stands; plain default reaches domain_screen until T04 wires the mode; missing `Record` row in technical_rows was a ticket error (Key/Version/Scope/Schema hash are the rows). T05 reviewer-lite escalated.
D31 2026-10-21 agent actors read `{name} ⚙` in plain, `agent:{name} ⚙` in technical; services by label (`a service` if unknown). In T13 T08b.
D32 2026-10-21 LESSON: every tl-tui ticket is `review: full` (reviewer-lite excludes tui). T05 and T09e merged as lite; T12 (drives the TUI) changed to full; README table updated.
D33 2026-10-21 T08 split for the 400-line/5-file rule: T08 record_view.py + context_panel.py; T08b links_tab thread_tab thread_text; T08c grid.py. T08 regenerates the snapshots that show the context panel heading and header (most of test_snapshots and test_snapshots_links).
D34 2026-10-21 integration registry rows are projection rows, not records: T09a has no Enter; T07 (review queue, Enter via target.id) goes first and adds the `technical` switch to integration_text.py; T09a follows.
D35 2026-10-21 grid `Ver` column kept (default columns are in every snapshot); T11 walk decides (Q6). main_area.py and link_picker.py print no ids: no ticket.
D36 2026-10-21 History needles in tests are the plain words (T08); the technical form is kept in one assertion per area.
D37 2026-10-21 look-ahead header, phases, percent and relationship types read as plain words; technical keeps the codes (T06b).
D38 2026-10-21 grid: approved needle stands; the column chooser shows the property label, not the key (T08c, Blocked cleared by orch).
D39 2026-10-21 (orch) Q6: grid `Ver` only in technical mode; Q7: layer kind words capitalised in plain (`Company ●`). Both in T11b.
D40 2026-10-21 r7: T11 split (T11 walk, T11b carries, T11c demo) and T12 split (T12 regen, T12b new section 23): the 400-line/5-file rule. New section numbered 23 in the Phase 1 tour; tour world sets the three data sets inside it so sections 1-22 change only by plain language.
D41 2026-10-21 derived-documents schema column reads as plain label (T11).
D42 2026-10-21 grid Ver technical-only on all grids; settings kinds in plain words (T11b).
D43 2026-10-21 admin walk rules: plain clean on and after toggle; MUST_CHANGE screens differ under Ctrl+D; round trip restores plain; UNCHANGED_OK is f1 only (T11).
D44 2026-10-21 extension grids, chooser name and settings list rows follow plain mode (T11b).
D45 2026-10-21 S4 replaces T11c, T12, T12b: one builder does demo and both tours; the tour checks its own screens for technical text.
D46 2026-10-21 S5 final polish: Properties tab labels and unit placeholder, workbench drafter, SERVICE_PATTERN hyphen, tour key_hits with a test, review-queue row in the demo.
PROC 2026-10-21 skill rule 12 (owner request) on trunk 5a05125: consequential pins, size by coherence, one pass, orchestrator fixes trivia, builders run only what is named.
## SEC
9 reviews, range 4b2cda0..aca2ec5: record screen P, property sets P.
F1 LO fixed@09461d6 record_id max_length=64 (GET /schema/forms)
F2 LO fixed@09461d6 document_data confidentiality_note says it does not restrict
F3 LO accepted reload-after-reclassification, ADR-0016 section 6
S4 review F1 F2 (demo review-queue row, tour key_hits) -> S5
## OPEN
Q8 owner: move the full web client earlier than Phase 5 I6 for mainstream AEC users? (raised 2026-10-21) needs owner raised orch
## NEXT
1. Orchestrator: merge S5 (D46), then DONE gate: just check, just gate (parts as separate background runs, L-P1-I8-14), gate-pg touched dirs, just demo P1-UX.
2. Fill the <<fill>> cells in docs/reports/P1-UX.md (check, gate, gate-pg, S5 line); S5 narrative and screenshots come from its report.
3. Merge p1/ux to trunk; STATUS.md line; APPROVALS already has the 2026-10-21 line.
4. Phase 2 owner questions stay in docs/build-spec/phase2-owner-questions.md.
## REFS
Report docs/reports/P1-UX.md; specs docs/tickets/P1-UX/*.md; reports docs/reports/P1-UX/; tour section 23 in docs/reports/PHASE-1-TOUR.md; tl-tui README/AGENTS "Plain and technical display".
## TRAPS
Trunk time-bomb: tests reading the wall clock; a fixed-date fake world needs a pinned today. A gate with a nonexistent test path exits 4 and reads red. `just check` takes over 2 min; run in background. Demo takes about 15 min. Full tl-tui suite about 10 min.
