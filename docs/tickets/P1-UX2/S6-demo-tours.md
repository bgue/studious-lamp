# P1-UX2-S6 — Demo, tours and the tour section

Status: draft (dispatch in wave 3, after S3, S4, S5 are merged)
Tier: sonnet
Kind: piece
Review: full
Labels: dev, tui, docs, tests
Depends on: S3, S4, S5
Branch: `p1/ux2-s6-demo-tours`

## Goal
`just demo P1-UX2` proves the four SCOPE §5 clauses on SQLite and Postgres; the tours are regenerated with the leak
check and gain a section that shows the log standard, the RFI record and the document preview fallback; the
tl-tui README and runbook match what shipped.

## Brief references (pasted, abridged)
> SCOPE §5. `just demo P1-UX2` (SQLite and Postgres): the breadcrumb follows the highlighted row; the actions bar of an
> RFI shows Answer to an answerer and not to a plain reader, and Answer from the bar answers it; the RFI record shows
> narrative, timeline and files; the document log opens a PDF (to a temp file, checked by hash) and shows its
> page-count fallback. Tours regenerated with the tour leak check; a new PHASE-1-TOUR section shows the log standard,
> the RFI record and the document preview fallback.
> Skill rule 12: one pass where two would read the same screens: the leak check runs inside the tour generator that
> already visits the screens, and the demo drives only the four clauses (the P1-UX walk made that demo take about 15
> minutes; do not repeat a full walk here). Builders run what the brief names, once.

## Interfaces
- `dev/demos/P1-UX2.sh` (create; same skeleton as `dev/demos/P1-UX.sh`: `TL_DEMO_BACKENDS`, throw-away Postgres on `TL_PG_URL`, `DEMO FAILED`, a PASS line per clause) and `dev/demos/p1_ux2_demo.py` (create; drives the TUI with the Textual test pilot on a seeded ledger).
- Seed (in the demo, not the fixtures): an RFI awaiting an answer with a long question, an answer round, and two attached files; a document whose current revision has a small real PDF (made with `pypdfium2`, 3 pages) attached through the file service; a controller, an answerer, a plain reader, and `TL_VIEWER_CMD` pointing at a recorder script that writes the path it was given.
- Clause checks: (1) crumb text equals `P123 › RFI Log › <number>: <title>` for the highlighted row and changes when the cursor moves; (2) bar for the answerer contains `Answer`, bar for the reader does not, `a` + typed text + submit moves the RFI to Answered and the status line stays clean; (3) the record screen Details starts with the question, shows the timeline rows in order and the Files tab lists both files; (4) `v` on the document row: the recorder received a path in a private temp directory (mode 0700), its sha256 equals the stored file's, and with images forced off (`TL_IMAGES=off`) the panel reads `PDF document ... 3 pages`.
- `dev/tour/phase1.py`: new section 24 "The log standard, the RFI record and document preview" (shots `24a` RFI log wide at 170 columns, `24b` RFI log stacked at 100, `24c` RFI record Details with timeline, `24d` Files tab, `24e` document log with the page-count fallback, `24f` actions bar for a reader vs an answerer), `docs/reports/PHASE-1-TOUR.md` section 24, and regenerated `docs/reports/tour/phase-1/**` and phase 0 outputs.
- `packages/tl-tui/README.md`: check the "Log screens" and "File preview" sections against the code (fix wording only); `docs/runbooks/tui-dev.md`: demo and tour notes.

## Context (≤ 10 files)
- `dev/demos/P1-UX.sh`, `dev/demos/p1_ux_demo.py`, `dev/tour/phase1.py` (section 23 as the pattern), `dev/tour/tourkit.py`
- `docs/reports/PHASE-1-TOUR.md` (section 23), `packages/tl-tui/README.md`, `docs/runbooks/tui-dev.md`
- `packages/tl-tui/src/tl_tui/preview/viewer.py` (`TL_VIEWER_CMD`), `docs/tickets/P1-UX2/SCOPE.md` §5
may explore: S3/S4/S5 reports in `docs/reports/P1-UX2/`

## Allowed paths
- `dev/demos/P1-UX2.sh`, `dev/demos/p1_ux2_demo.py` (create); `justfile` only if `demo` needs no change (it does not: leave it)
- `dev/tour/phase1.py`, `dev/tour/tourkit.py`, `docs/reports/PHASE-1-TOUR.md`, `docs/reports/tour/**`
- `packages/tl-tui/README.md`, `docs/runbooks/tui-dev.md`, `packages/tl-tui/tests/test_tour_leaks.py`
- `docs/reports/P1-UX2/S6.md` (create)
Consequential pins (rule 12): a tour leak the new screens expose that is a test-list or tour-list gap is fixed in the list
(never by hiding text); a real leak in a screen is NOT fixed here: stop and list it (file, token).

## Acceptance (run these, once, in this order)
```
just check
just demo P1-UX2
just tour-all
just tour-all
git status --short docs/reports/tour
```
Expected: demo 4/4 on SQLite and Postgres; `just tour-all` exit 0, no `LEAK`; the second run changes no file.

## Tests to add
`packages/tl-tui/tests/test_tour_leaks.py` gains the new shots' ids if it lists them. No new suite.

## Report requirements
`docs/reports/P1-UX2/S6.md` ≤ 60 lines: deviations first, the four PASS lines, shot count, run times, learnings.

## Escalation triggers
- A real leak (id, hash, internal key) in S3/S4/S5 output: stop, list.
- The demo exceeds 20 minutes: stop and say which clause is slow.
