# P1-UX STATE  r=2 base=b841c39 C=C0 ck=0 gate=n/a wt=/home/user/wt/p1-ux
Read first: README.md (plan, decisions D1-D9, 15 tickets + S2 S3, waves, Plan check), SCOPE.md, T00 / S2 / S3 specs. Branch p1/ux (trunk claude/wizardly-allen-m2v96s; its @d5e5455 adds only an APPROVALS line, not merged).
r2 applied plan check F1-F12 (all accepted), renamed S1 to ticket T00, dispatched wave 1 (T00 + S3).
## BOARD
T00 t disp f - display helper (was S1), branch p1/ux-t00-display-helper
S3 p disp f - fixture sets, titles, type_labels, tl-tui pins; schema 95
S2 p todo f - record screen; dep T00 S3 (wave 2)
T09b t todo f - accounts, settings, schema screens; dep T00 (wave 2)
T10 t todo f - Ctrl+D toggle, help, palette; dep T00 (wave 2)
T01 t todo f - documents register; wave 3
T02 t todo f - tag register; wave 3
T03 t todo f - correspondence register inbox clocks; wave 3
T04 t todo f - domain screen, RFI log; wave 4
T05 t todo l - commercial, evidence, drop State/Status dup; wave 4
T06 t todo f - schedule and cost lists; wave 4
T07 t todo f - review queue, target RecordRef; wave 5 with T09a
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
## SEC
(none yet; DONE review: Sec S2 (routes/reference.py record_id, record_screen hidden=missing), S3; range 4b2cda0..<head>; one reviewer per item)
## OPEN
Q4 wave 5: do review-queue values already carry a `target` RecordRef, or does T07/T09a need a client change? grep before writing T07/T09a; if client contract, escalate. needs builder raised r2
## NEXT
1. Orchestrator merges T00 and S3 (C1) after gates; S3 95 line (fixture, module/core titles) to owner.
2. r3: verify board vs git log; write S2 update if T00/S3 reports changed it; dispatch wave 2 = S2 (builder) + T09b + T10 (write T09b, T10 from the template with interfaces pasted from the tree).
3. Wave 3 T01 T02 T03 after S2 merges (C2); read S2 report for the getter table (get_document... key mapping) first.
4. Wave 4 T04 T05 T06; wave 5 T07+T09a, T08+T13 (two workflows); wave 6 T11; wave 7 T12; DONE round: report, learnings, tl-tui README/AGENTS (display.py, details/), APPROVALS check, 88.
5. Before each DISPATCH grep every function and command a provided test calls (L-P1-I7B-9).
6. Every screen ticket runs its own TUI snapshot tests, regenerates only its snapshots (L-P1-I8-13).
7. T11 screen list is generated from keymap.py; T11 and T12 set document_data/rfi_data/correspondence_data values (P1-UX.sh; dev/tour/tourkit.py, phase1.py update_psets).
8. Tickets are written one wave ahead from the tree, so pasted interfaces are verbatim.
## REFS
Specs: docs/tickets/P1-UX/T00-display-helper.md, S2-record-screen.md, S3-fixture-psets-and-labels.md. No provided tests or stubs for wave 1 (T00 lists its tests by name; S3 lists its).
Survey facts: registers are ModalScreens (document_register, tag_register, correspondence_screen, domain_screen, schedule_screen, review_queue, integration_screen), each holds client/project/actor and rows carry record `id`; record view = widgets/record_view.py (tabs details, psets, links, history, trace, thread); psets_tab.py:84 prints `Effective schema #…` (S2 owns); form_metadata: client.py:142 (interface), tl_api/client/links.py:148 (remote, RemoteClient via __getattr__ remote.py:240); app.is_admin exists; client getters take (project, number): get_document, get_tag, get_correspondence, get_rfi, get_commercial, get_clock, get_schedule, get_schedule_snapshot; tour = dev/tour/phase0.py phase1.py tourkit.py, output docs/reports/tour/phase-{0,1}, narrative docs/reports/PHASE-1-TOUR.md; p1_i8_demo.py anchors on the fixture ('version: 3.2.0', '\n\n  safety_data:', one 'range: decimal').
Learnings that apply: L-P1-I8-13 L-P1-I8-15 L-P1-I5-1 L-P1-I5-2 L-P1-I3-7 L-P1-I8-4 L-P1-I7B-9.
## TRAPS
none seen (no suite run). `just check` takes over 2 min here; r2 ran it in the background, clean.
