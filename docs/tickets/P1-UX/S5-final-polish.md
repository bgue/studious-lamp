# P1-UX-S5: final plain-language polish (piece)

kind: piece · review: full · branch p1/ux-s5-final-polish · depends on S4 merged (p1/ux @8a74f75)
Work under skill rule 12 (consequential pins allowed and listed; run only what is named here).

## Goal (from the S4 report follow-ups and the S4 review, D46)
1. **Properties tab shows labels, not codes.** A code-list value shows its label (`Structural`, not `structural`;
   the currency's label or its standard code where the list has no label, e.g. `USD` stays). A unit placeholder
   such as `{currency}` is resolved to the record's currency value or the property's currency field; a raw
   `{…}` never reaches a plain screen. Technical mode keeps the stored codes.
2. **People by name.** The schema workbench (and any screen the walk now flags) shows `demo`, not `user:demo`,
   in plain mode, through `display.actor_label`; technical keeps the prefix.
3. **SERVICE_PATTERN** in display.py matches service ids with hyphens (`svc:inbound-acme-nde.results`), with a test.
4. **The tour check is as strict as the walk.** `tourkit.check_plain` also runs T11's `key_hits` over the
   record-type and property keys (move the key-list builder to a place both can import, e.g. tl_tui.display or a
   test-support module the tour may import), and gets an automated test: a plain shot carrying `core.Record`, a
   package ref and a ULID each print `LEAK` and make the run exit 1; a clean shot passes (S4 review F2).
5. **Review queue row in the demo** (S4 review F1): seed one enrichment proposal in the P1-UX demo ledger so
   clause 1 also opens the record screen from the review queue.
6. Re-run `just tour-all` twice (no `LEAK`, second run changes nothing) so screenshots that show the Properties
   tab or the workbench drafter are current; update narrative text that quotes them.

## Allowed paths
packages/tl-tui/src/tl_tui/** (display.py, psets_tab.py and the text modules the fixes need), packages/tl-tui/tests/**,
dev/tour/**, dev/demos/P1-UX.sh, dev/demos/p1_ux_demo.py, docs/reports/PHASE-*-TOUR.md, docs/reports/tour/**,
docs/reports/P1-UX/S5.md.

## Run
`just check`; `just gate packages/tl-tui/tests` once at the end; the tour test; `just tour-all` twice;
`just demo P1-UX` once.

## Acceptance
All of the above green; demo ends `P1-UX demo OK on: sqlite postgres`; report docs/reports/P1-UX/S5.md ≤ 60 lines
(fixes, consequential pins, screenshots changed, anything left).
