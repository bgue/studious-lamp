# P1-UX STATE  r=1 base=4b2cda0 C=C0 ck=- gate=n/a wt=/home/user/wt/p1-ux
Read first: README.md (plan, decisions D1-D6, tickets, order), SCOPE.md (owner request), the three S specs. Branch p1/ux (trunk claude/wizardly-allen-m2v96s @4b2cda0).
r1 surveyed tl-tui and wrote the plan and three piece specs. Nothing dispatched: 12 tickets > ~10, so PLANCHK first.
## BOARD
S1 p stg f - display helper, spec written
S3 p stg f - fixture sets, titles, type_labels; schema 95
S2 p stg f - record screen, details registry, form_metadata(record_id); dep S1 S3
T01 t todo f - documents register
T02 t todo f - tag register
T03 t todo f - correspondence register inbox clocks
T04 t todo f - domain screen, RFI log
T05 t todo l - commercial, evidence; dep T04
T06 t todo f - schedule and cost lists
T07 t todo f - review queue
T08 t todo f - record view, psets tab, context panel, grid
T09 t todo f - integration, accounts, settings, schema screens plain
T10 t todo f - toggle key, help, palette, snapshots
T11 t todo f - walking test and dev/demos/P1-UX.sh; dep T01-T10
T12 t todo l - tour re-shot, PHASE-1-TOUR section; dep T11
## DEC
D1 2026-10-21 record screen from a register is a modal RecordScreen on top; Esc dismisses; README.
D2 2026-10-21 Details per type from the typed views registers already read, in tl_tui/details/<area>.py; no new route.
D3 2026-10-21 type labels = LinkML title on record-type classes + generated type_labels.py; humanize fallback.
D4 2026-10-21 new sets added in place to fixture 3.2.0 (3.3.0 is the P1-I8 demo draft); additive.
D5 2026-10-21 technical mode = in-memory DisplayMode on the app, admin-only toggle, not remembered.
D6 2026-10-21 GET /schema/forms gains optional record_id (bound sets for tags); output otherwise unchanged.
D7 2026-10-21 owner (via orch): scope = SCOPE clauses 1-5; toggle admin-only; fixture sets approved, orch records APPROVALS.
## SEC
(none yet; DONE review scoped to S2 route + record_id and S3 schema)
## OPEN
Q1 plan check: 12 tickets + 3 pieces; trim by merging T07 into T09 and T05 into T04? needs orch raised r1
Q2 Do the `title` lines on module classes and generated type_labels.py fall under the owner's 2026-10-21 approval? needs orch raised r1
Q3 Is the key for the toggle left to T10? Free: Ctrl+K, Ctrl+D, Ctrl+L, Ctrl+Y (all F-keys and Ctrl+A/E/G/N/O/P/Q/R/S/T taken). Proposal Ctrl+D; palette entry "Technical details". needs orch raised r1
## NEXT
1. Orchestrator spawns plan-check on README.md; findings under "## Plan check"; answer or waive each (round 2).
2. Round 2: apply the check, then batch 1 = S1 + S3 in parallel (disjoint paths), dispatch with provided tests named in specs.
3. Batch 2 = S2 after S1 and S3 merge (C1). Round after S2 merges: write T01-T12 from the template with pasted interfaces.
4. Tickets: batch 3 T01 T02 T03; batch 4 T04 T06 T07; batch 5 T05 T08 T09 T10; then T11, T12.
5. Before each DISPATCH grep every function and command a provided test calls (L-P1-I7B-9).
6. Every screen ticket runs its own TUI snapshot tests and regenerates only its snapshots (L-P1-I8-13).
7. DONE round: report, learnings, tl-tui README/AGENTS (display.py, details/), APPROVALS check, 88.
## REFS
Specs: docs/tickets/P1-UX/S1-display-helper.md, S2-record-screen.md, S3-fixture-psets-and-labels.md.
Survey facts (so the next round need not re-read): registers are ModalScreens (document_register, tag_register, correspondence_screen, domain_screen, schedule_screen, review_queue, integration_screen), each holds client/project/actor and rows carry record `id`; record view = widgets/record_view.py (tabs details, psets, links, history, trace, thread); psets_tab.py calls form_metadata(scope, type) with no record id; app.is_admin exists; client getters take (project, number): get_document, get_tag, get_correspondence, get_rfi, get_commercial, get_clock, get_schedule, get_schedule_snapshot; tour = dev/tour/phase0.py phase1.py, output docs/reports/tour/phase-{0,1}, narrative docs/reports/PHASE-1-TOUR.md; p1_i8_demo.py text anchors on the fixture ('version: 3.2.0', '\n\n  safety_data:', one 'range: decimal').
Learnings that apply: L-P1-I8-13 L-P1-I8-15 L-P1-I5-1 L-P1-I5-2 L-P1-I3-7 L-P1-I8-4 L-P1-I7B-9.
## TRAPS
none seen (no suite run in r1).
