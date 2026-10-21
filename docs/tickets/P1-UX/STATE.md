# P1-UX STATE  r=6 base=1dc96af C=C2 ck=0 gate=n/a wt=/home/user/wt/p1-ux
Read first: README.md (plan, tickets, waves), SCOPE.md, specs of the items you dispatch, reports T05 T06 (docs/reports/P1-UX/), S2 report (getter table). Branch p1/ux (trunk claude/wizardly-allen-m2v96s @2bcedda merged in).
r6: T05 T06 T09e merged (806c519). Wrote T04 T08 T13 (dispatched, 3 slots) and staged T08b T08c T06b T07 T09a T09d (tickets committed 1dc96af). All `review: full`. No code, stubs or held tests by the supervisor.
## BOARD
T00 t mrg f 369b72f display helper
S3 p mrg f 6a0c7ae example sets (D12), TYPE_LABELS
S2 p mrg f 16d2e11 RecordScreen, open_record, details registry
T09b t mrg f 893dd7d accounts, about:config plain
T09c t mrg f 4007e29 schema workbench and review plain
T10 t mrg f 4793a7c Ctrl+D toggle, help/palette scroll
T01 t mrg f 4250f0d documents register Enter + plain
T02 t mrg f e4ee157 tag register Enter + plain
T03 t mrg f a09aad7 correspondence register/inbox/clocks
T06 t mrg f 55a8205 schedule screen Enter + plain (cd96edc)
T09e t mrg l 34fc72d settings layer words (3f7f39a)
T05 t mrg l 806c519 commercial/evidence/RFI text (5915ad6); D30
T04 t disp f - domain_screen wiring, Enter, RFI Details, evidence via-label F1; p1/ux-t04-domain-screen
T08 t disp f - record_view header v + History, context panel; p1/ux-t08-record-view-context
T13 t disp f - feed pane, header, ref tray; p1/ux-t13-main-screen-plain
T08b t stg f - links_tab, thread_tab, thread_text; after T08 merges (snapshots)
T08c t stg f - grid type column, property headers
T06b t stg f - compare, activity, look-ahead, orphan lines (Q5)
T07 t stg f - review queue Enter via target + plain; integration_text technical switch
T09a t stg f - integration registry plain, no Enter; after T07 merges
T09d t stg f - Enter on schema package rows + details/schemareg.py
T11 t todo f - walking test from keymap.py, P1-UX.sh; carry-overs (a) (c), Q6 Q7
T12 t todo f - tour re-shot, PHASE-1-TOUR (tier fixed D32)
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
## SEC
(none yet; DONE review: Sec S2 (routes/reference.py record_id, record_screen hidden=missing), S3; range 4b2cda0..<head>; one reviewer per item)
## OPEN
Q5 CLOSED r6: placed as T06b.
Q6 grid `Ver` column and any other record version shown in plain: T11 walk decides. needs self raised T08c
Q7 settings list/origin rows show lowercase kinds `company ●` (T09e report): T11 walk decides. needs self raised T09e
## NEXT
1. Orchestrator dispatches T04 T08 T13 (disjoint). Merge order T04, T08, T13. test_reference_tray.raw changes in both T08 (heading) and T13 (type label): second merge conflicts on the .raw only; regenerate (131), do not send back.
2. r7: verify board; dispatch T07, T08b, T06b (T08b needs T08 merged; all disjoint: review_queue/integration_text, links/thread, schedule_text/compare/activity). Re-read each ticket's "Interfaces" against the tree at dispatch (T08 changes record_view.py).
3. r8: T09a (after T07), T08c, T09d. r9: T11. r10: T12.
4. T11 carries (a) a plain user is refused via the palette entry (T10 rev F1 LO), (c) remote-client hidden=missing on the record screen (S2 rev F1 LO), Q6, Q7. T11 and T12 set document_data/rfi_data/correspondence_data values. T11 walks the screens generated from keymap.py with find_technical(text, labels) as a plain user.
5. DONE round: report, learnings (mode_of takes the app; DataTable Enter/RowSelected; wrong gate paths cost a gate; kwargs default raw when the screen is another ticket's; tl-tui never lite D32; Context must list files the Interfaces pin; a snapshot .raw changed by two tickets conflicts: order merges, regenerate), tl-tui README/AGENTS (display.py, details/, record_screen), APPROVALS check, 88.
6. Before each DISPATCH: `ls` every test path in the gate list (done r6 for all nine; new files marked); grep each function a ticket cites.
7. Screen tickets regenerate only the snapshots they name (L-P1-I8-13). Every screen ticket adds refresh_for_display_mode (D14).
8. Open nits not placed: record screen does not reload the register after an edit (F5 reloads); revisit in T11 if the walk shows it. `schedule_detail_lines(technical=)` unused (T06 report): T11 or DONE nit.
## REFS
Specs: docs/tickets/P1-UX/{T00..T13 incl. T06b T08b T08c T09d}-*.md; no stubs or provided tests (tickets list tests by name; new test files marked "(new)" in each Acceptance). Reports in docs/reports/P1-UX/.
Survey facts: registers are ModalScreens (document_register, tag_register, correspondence_screen, domain_screen, schedule_screen, review_queue, integration_screen), each holds client/project/actor; record view = widgets/record_view.py (tabs details, psets, links, history, trace, thread); app.is_admin exists; tour = dev/tour/phase0.py phase1.py tourkit.py, output docs/reports/tour/phase-{0,1}, narrative docs/reports/PHASE-1-TOUR.md; p1_i8_demo.py anchors on the fixture ('version: 3.2.0', '\n\n  safety_data:', one 'range: decimal'). Snapshots: tests/__snapshots__/<module>/<test>.raw, one file per test; the context panel shows in most; header badges test is in test_snapshots_links.
Text pattern (copy for new work): `fn(x, labels=None, *, technical=...)`; widget reads `mode_of(self.app).technical`, loads `load_labels(client, scope, types)` on mount, defines refresh_for_display_mode.
Learnings that apply: L-P1-I8-13 L-P1-I8-15 L-P1-I5-1 L-P1-I5-2 L-P1-I3-7 L-P1-I8-4 L-P1-I7B-9.
## TRAPS
Trunk time-bomb: tests reading the wall clock (domain_screen fixed 2e8285c); expect others. A gate with a nonexistent test path exits 4 and reads red. `just check` takes over 2 min here; run in background. Haiku implementers name their own model in the trailer; the orchestrator's trailer rule wins at merge.
