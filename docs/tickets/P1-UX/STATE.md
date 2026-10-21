# P1-UX STATE  r=3 base=2e8285c C=C0 ck=0 gate=n/a wt=/home/user/wt/p1-ux
Read first: README.md (plan, D1-D9, tickets + S2 S3, waves), SCOPE.md, specs T00 S2 S3 T09b T09c T10. Branch p1/ux @9f5d34c+r3 commits (trunk claude/wizardly-allen-m2v96s @2e8285c merged in).
r3: T00 merged @369b72f; S3 not merged (builder fixing D12 on its branch, then full review); wave 2 = T09b T09c T10 written and dispatched; S2 held for S3 (needs generated type_labels.py, absent on p1/ux).
## BOARD
T00 t mrg f 369b72f display helper (fx@1d9669f D10 D11); LO F1 F2 ride T10
S3 p gr f 32c1681 gr was trunk time-bomb only (fx 2e8285c); D12 fix building, then review; schema 95
S2 p todo f - updated r3 (display_mode, refresh hook); dispatch after S3 mrg
T09b t disp f - accounts, about:config plain; no Enter (rows not records)
T09c t disp f - schema workbench and review plain (split from T09b: too big)
T10 t disp f - Ctrl+D, keymap, palette, refresh hook, find_technical dedupe
T09d t todo f - Enter on schema package rows; after S2 + T09c
T01 t todo f - documents register; wave 3
T02 t todo f - tag register; wave 3
T03 t todo f - correspondence register inbox clocks; wave 3
T04 t todo f - domain screen, RFI log; wave 4
T05 t todo l - commercial, evidence, drop State/Status dup; wave 4
T06 t todo f - schedule and cost lists; wave 4
T07 t todo f - review queue Enter via row target RecordRef; wave 5 with T09a
T09a t todo f - integration registry Enter; wave 5 with T07
T08 t todo f - context panel, grid, links tab, thread tab; wave 5
T13 t todo f - main screen: feed, header, main area, ref tray, link picker; wave 5
T11 t todo f - walking test from keymap.py, P1-UX.sh; wave 6
T12 t todo l - tour re-shot, PHASE-1-TOUR; wave 7
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
## SEC
(none yet; DONE review: Sec S2 (routes/reference.py record_id, record_screen hidden=missing), S3; range 4b2cda0..<head>; one reviewer per item)
## OPEN
Q4 CLOSED r3 by grep: enrichment rows are `EnrichmentValue` dumps with `target` RecordRef dict {id,key,record_type,version,seq} (contract.py:780, integration_text.py:141,211); no client change. T07/T09a use row["target"]["id"].
## NEXT
1. Orchestrator merges T09b T09c T10 after gate + review; merges S3 after its D12 fix and full review (S3 95 line to owner), then S2 can dispatch (C1 = T00+S3).
2. r4: verify board; dispatch S2 (builder) alone or with T09d-prep; write T01 T02 T03 only after S2 report (getter table: read it first).
3. T09d from tree after S2 + T09c merged (open_record call in schema_screen.py Enter).
4. Wave 4 T04 T05 T06; wave 5 T07+T09a, T08+T13; wave 6 T11; wave 7 T12; DONE round: report, learnings, tl-tui README/AGENTS (display.py, details/), APPROVALS check, 88.
5. Before each DISPATCH grep every function and command a provided test calls (L-P1-I7B-9).
6. Every screen ticket runs its own TUI snapshot tests, regenerates only its snapshots (L-P1-I8-13); T10 owns palette snapshot.
7. T11 screen list generated from keymap.py; T11 and T12 set document_data/rfi_data/correspondence_data values (P1-UX.sh; dev/tour/tourkit.py, phase1.py update_psets).
8. Tickets written one wave ahead from the tree, interfaces verbatim. Screen tickets must add refresh_for_display_mode (D14); T11 walk sets display_mode directly.
## REFS
Specs: docs/tickets/P1-UX/{T00,S2,S3,T09b,T09c,T10}-*.md. No provided tests or stubs this wave (tickets list tests by name). Existing tests marked "Provided; do not edit" (schema text/screens) are updated by T09c on purpose.
Survey facts: registers are ModalScreens (document_register, tag_register, correspondence_screen, domain_screen, schedule_screen, review_queue, integration_screen), each holds client/project/actor, rows carry record `id`; record view = widgets/record_view.py (tabs details, psets, links, history, trace, thread); psets_tab.py:84 prints `Effective schema #…` (S2 owns); form_metadata: client.py:142, tl_api/client/links.py:148 (remote via __getattr__ remote.py:240); app.is_admin exists; client getters take (project, number): get_document, get_tag, get_correspondence, get_rfi, get_commercial, get_clock, get_schedule, get_schedule_snapshot; tour = dev/tour/phase0.py phase1.py tourkit.py, output docs/reports/tour/phase-{0,1}, narrative docs/reports/PHASE-1-TOUR.md; p1_i8_demo.py anchors on the fixture ('version: 3.2.0', '\n\n  safety_data:', one 'range: decimal'). Only the palette renders the keymap in a snapshot (test_snapshots_links::test_command_palette). Textual Input binds ctrl+d (delete right): T10 escalates if the app binding does not fire from grid/record focus.
Learnings that apply: L-P1-I8-13 L-P1-I8-15 L-P1-I5-1 L-P1-I5-2 L-P1-I3-7 L-P1-I8-4 L-P1-I7B-9.
## TRAPS
Trunk time-bomb: domain_screen evidence test read the wall clock (fixed 2e8285c); expect other date-reading tests. `just check` takes over 2 min here; run in background.
