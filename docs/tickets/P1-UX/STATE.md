# P1-UX STATE  r=4 base=2bcedda C=C2 ck=0 gate=n/a wt=/home/user/wt/p1-ux
Read first: README.md (plan, tickets, waves), SCOPE.md, specs T01 T02 T03 T09e, S2 report docs/reports/P1-UX/S2.md (getter table). Branch p1/ux @d87534c+st (trunk claude/wizardly-allen-m2v96s @2bcedda merged in).
r4: T00 S3 S2 T09b T09c T10 merged (C1, C2 done); wave 3 = T01 T02 T03 written and dispatched; T09e (T09b leftovers) staged; tests-support FakeClient.add_stored_record added by supervisor (tests/fakes.py, 32 lines + 1 test).
## BOARD
T00 t mrg f 369b72f display helper; LO F1 F2 done in T10
S3 p mrg f 6a0c7ae example sets (D12), TYPE_LABELS; units numbers only
S2 p mrg f 16d2e11 RecordScreen, open_record, details registry, form_metadata(record_id)
T09b t mrg f 893dd7d accounts, about:config plain (D16 D19)
T09c t mrg f 4007e29 schema workbench and review plain
T10 t mrg f 4793a7c Ctrl+D toggle, help/palette scroll (D17 D18)
T01 t disp f - documents register Enter + plain; gate: tests listed in ticket
T02 t disp f - tag register Enter + plain + details/tags.py
T03 t disp f - correspondence register/inbox/clocks + details/correspondence.py
T09e t stg l - settings layer words (b); dispatch wave 4
T05 t todo l - commercial/evidence TEXT ONLY, kwargs optional; before T04
T06 t todo f - schedule and cost lists; independent; wave 4
T09d t todo f - Enter on schema package rows; unblocked (S2 T09c merged); wave 5
T04 t todo f - domain screen wires T05 text; RFI details; after T05
T07 t todo f - review queue Enter via row target RecordRef; wave 5 with T09a
T09a t todo f - integration registry Enter; wave 5
T08 t todo f - context panel, grid, links tab, thread tab; + D20 (d) + (e)
T13 t todo f - main screen: feed, header, main area, ref tray, link picker
T11 t todo f - walking test from keymap.py, P1-UX.sh; + carry-overs (a) (c)
T12 t todo l - tour re-shot, PHASE-1-TOUR
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
D10 2026-10-21 DisplayMode lives on the app as `display_mode` (App.display is a Textual CSS prop); mode_of reads it. T00 fx@1d9669f. README unchanged, here.
D11 2026-10-21 calendar leak pattern is `code@version` (CALENDAR_REF_PATTERN) with a lookbehind so package refs do not double-hit. T00 report.
D12 2026-10-21 S3: adoption mandatory for sets dropped from project scopes; missing values at most warning. Builder fixing on S3 branch, then full review. S2 waits for S3.
D13 2026-10-21 admin tools plain by default: token ids, setting seq numbers, svc: actors, joined name@version, Digest lines technical-only; setting keys, workbench Version column and Property/Lint/Diff tabs stay. In T09b T09c.
D14 2026-10-21 toggle refresh: widgets define `refresh_for_display_mode()`; T10 calls it on all widgets of all stacked screens (errors swallowed). Every later screen ticket adds it when its text depends on the mode (in S2 too).
D15 2026-10-21 T09b split: schema part is T09c; Enter on package rows (PackageSummary.id is a record id) is T09d after S2. Accounts, tokens, settings are not records: no Enter.
D16 2026-10-21 History/By column shows the name (actor_label), not the raw actor id. T09b.
D17 2026-10-21 help and palette scroll; pinned snapshot asserts became presence checks. T10.
D18 2026-10-21 priority Ctrl+D steps aside in Input/TextArea (Textual binds ctrl+d = delete right there). T10.
D19 2026-10-21 palette toggle entry is ungated; the refusal lives in DisplayMode.toggle. Plain layer names: Company, Project P123, User (settings_text.layer_label). T09b T10.
D20 2026-10-21 record header `v{version}` hidden in plain mode, shown in technical (record_view.py:186). Placed in T08.
D21 2026-10-21 clock rows: plain leads with item number under `Item`, technical with clock key under `Clock`; calendar ref technical only. In T03.
D22 2026-10-21 registers open records on DataTable.RowSelected (never a priority Enter binding: it steals Enter from the filter Input). Tag register has no actor: getattr(app, "actor", "user:dev"). In T01 T02 T03.
D23 2026-10-21 FakeClient.add_stored_record(record_id, key, type, title) registers a record under a module fake's view id so a register row opens it (supervisor, tests/fakes.py).
D24 2026-10-21 T05 is text-only (optional labels/technical kwargs; dropped State/Status column via the constants); T04 owns all domain_screen wiring: domain_screen imports commercial_text, evidence_text, rfi_text, so T04 and T05 never share a wave.
D25 2026-10-21 carry-overs: (a) (c) -> T11; (b) -> T09e; (d) (e) -> T08. See NEXT.
## SEC
(none yet; DONE review: Sec S2 (routes/reference.py record_id, record_screen hidden=missing), S3; range 4b2cda0..<head>; one reviewer per item)
## OPEN
Q4 CLOSED r3 by grep: enrichment rows are `EnrichmentValue` dumps with `target` RecordRef dict {id,key,record_type,version,seq} (contract.py:780, integration_text.py:141,211); no client change. T07/T09a use row["target"]["id"].
## NEXT
1. Orchestrator dispatches T01 T02 T03 (one workflow, gate lists in the tickets), merges after gate + review.
2. r5: verify board; write T05 (text only), T06 from the tree after T01-T03 merge; dispatch T05 T06 T09e (3 slots). T04 after T05 merges.
3. r6: T04, T09d, then T07+T09a, T08+T13. T08 carries D20 (record_view.py:186 v{version} plain-hidden) and (e) History tab scanned by find_technical.
4. T11 carries (a) a plain user is refused via the palette entry (T10 rev F1 LO), (c) remote-client hidden=missing on the record screen (S2 rev F1 LO). T11 and T12 set document_data/rfi_data/correspondence_data values.
5. DONE round: report, learnings (mode_of takes the app; DataTable Enter/RowSelected; wrong gate paths cost a gate), tl-tui README/AGENTS (display.py, details/, record_screen), APPROVALS check, 88.
6. Before each DISPATCH: `ls` every test path in the gate list (a wrong path cost one red gate); grep each function a ticket cites.
7. Screen tickets regenerate only their own snapshots (L-P1-I8-13); registers T01-T03 have no snapshot test. Every screen ticket adds refresh_for_display_mode (D14).
8. Open nits not placed: record screen does not reload the register after an edit (F5 reloads); revisit in T11 if the walk shows it.
## REFS
Specs: docs/tickets/P1-UX/{T00,S2,S3,T01,T02,T03,T09b,T09c,T09e,T10}-*.md. Stub this round: tests/fakes.py add_stored_record (+test_fakes.py). Tickets list tests by name; gate paths verified by ls at r4.
Survey facts: registers are ModalScreens (document_register, tag_register, correspondence_screen, domain_screen, schedule_screen, review_queue, integration_screen), each holds client/project/actor, rows carry record `id`; record view = widgets/record_view.py (tabs details, psets, links, history, trace, thread); psets_tab.py:84 prints `Effective schema #…` (S2 owns); form_metadata: client.py:142, tl_api/client/links.py:148 (remote via __getattr__ remote.py:240); app.is_admin exists; client getters take (project, number): get_document, get_tag, get_correspondence, get_rfi, get_commercial, get_clock, get_schedule, get_schedule_snapshot; tour = dev/tour/phase0.py phase1.py tourkit.py, output docs/reports/tour/phase-{0,1}, narrative docs/reports/PHASE-1-TOUR.md; p1_i8_demo.py anchors on the fixture ('version: 3.2.0', '\n\n  safety_data:', one 'range: decimal'). Only the palette renders the keymap in a snapshot (test_snapshots_links::test_command_palette). Textual Input binds ctrl+d (delete right): T10 escalates if the app binding does not fire from grid/record focus.
Learnings that apply: L-P1-I8-13 L-P1-I8-15 L-P1-I5-1 L-P1-I5-2 L-P1-I3-7 L-P1-I8-4 L-P1-I7B-9.
## TRAPS
Trunk time-bomb: domain_screen evidence test read the wall clock (fixed 2e8285c); expect other date-reading tests. A gate with a nonexistent test path exits 4 and reads red (S2 r3). `just check` takes over 2 min here; run in background.
