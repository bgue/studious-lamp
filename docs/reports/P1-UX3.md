# P1-UX3: the `tui-layout` rules applied to the everyday screens

**Deviation first:** the owner said to run no tests, so none was run (no pytest, no gate). `just check` is clean; both full tours and the new highlight tour were regenerated instead. Snapshot and text pins below are stale on purpose.

## What changed

One shared renderer, `tl_tui/layout.py` (a `Page` of an identity line, a state line and named `Section`s; `Label  value` lines aligned per section; `—` for empty; long text cut at a word with `… (Enter for all)`). Every panel and every Details tab renders through it. A record type builds its rows once (`DetailRow` now has a `section`) and the Details tab and the log panel both use them: `details/technical.py` (RFI), `details/correspondence.py` (letter, clock), `details/commercial.py`, `document_text.py` + `details/documents.py`.

Logs (`LogScreen`, so every log): a column whose value is the same in every shown row (two or more rows) is hidden and returns when a second value appears; the number, the state and the subject never hide. Only the subject column shortens, with `…`, to the width left by the others. Empty cells read `—`.

| Screen | Before | After |
|---|---|---|
| RFI log | Number, State, Kind, Disc, Raised, Needed, Answered, Days, Timing, Impact, Subject | Number, Subject, State, then Kind (only if it varies), Discipline, Raised, Needed by, Answered, Days, Timing, Impact; constant ones hidden |
| RFI panel | one run-on line, `subject:`, `question:` lines | identity and state lines; Question, Proposed solution, Answer, Key facts, Response clocks, Timeline (4 rows), Files (3 rows) |
| RFI Details | rows mixed: subject, question, answer, review, timeline, metadata, ids | sections as above (full lists), Record dates last; ids, keys and the full timeline times only in technical mode |
| Correspondence register, inbox | State, Dir ... Subject last | Number, Subject, State, Dir, Domain, Date, With, Due |
| Clocks | Clock/Item, State ... Label last | Item (Clock), Label, State, Due, Left, Days, Type |
| Letter panel | 6 run-on lines | identity, state, Message, Suggestion (inbox), Key facts, People, Dates, Response clocks, Timeline, Files |
| Letter Details | flat rows with Type, Number, State repeated | Message, Key facts, People, Dates, clocks, timeline, files; delivery, received-via and clock keys are technical |
| Clock panel and Details | two lines, then flat rows | identity and state, Key facts, Problem |
| Document log | Number, State, Current, Type, Discipline, Title | Number, Title, State, Current, Type, Discipline |
| Document panel | `state ... \| type ...` run-on lines | identity, state, Key facts, Revisions (n), Files (n) with the preview line, Links (n, k stale) with `No links` |
| Document Details | flat rows, no revisions or links | Description, Key facts, Revisions, Files, Links, Record, technical |
| Commercial register and panel | State ... Subject last; run-on lines | Number, Subject, State first; sections Basis, Key facts, Cost and schedule, Assessment, clocks, files |
| Generic record Details | Type, Title, Status ... flat | Description, Summary, Record, technical |

Small word changes: an unlabeled lower-case code reads as a word (`Internal`); money reads `12500.00 USD`; clocks read `Running · due 2026-10-26 · 14 calendar days left`.

## Highlight tour

`dev/tour/highlights.py`, `just tour highlights` (the recipe now picks the script by name), eight SVGs in `docs/reports/tour/highlights/` and `docs/reports/HIGHLIGHTS-TOUR.md`. The world loads both standards files and raises RFIs with the code `STR`, so Discipline reads `Structural`. `TL_TOUR_TEXT=<dir>` (tourkit) also writes each shot as plain text. The `structural` free text in `phase1.py` RFIs became `STR` for the same reason. Two runs of the highlight tour are byte-identical; no `LEAK` line in any of the three tours.

## Stale pins for the next test run

Not touched, not run: `packages/tl-tui/tests/` `test_rfi_text`, `test_commercial_text`, `test_commercial_plain`, `test_correspondence_text`, `test_correspondence_plain`, `test_correspondence_screen`, `test_document_text`, `test_document_register`, `test_document_plain`, `test_document_flow`, `test_domain_screen`, `test_domain_plain`, `test_rfi_record`, `test_record_view`, `test_details_registry`, `test_record_files_tab`, `test_log_screen` (columns, 80/170 snapshots), `test_snapshots*` and `__snapshots__`, `test_plain_walk`, `test_standard_code_labels`, `fakes_correspondence`; demos `dev/demos/p1_i2_demo.py`, `p1_i5_demo.py`, `p1_i6_demo.py` read panel text. Expect new columns order, `—` for `-`, section headings, `Internal`. A new test is wanted for `log_text.visible_columns`, `fit_cell`, `flex_width` and `layout.render`.

## Not done

- Panels of the other logs (tags, schedules, review queue, integration, schema workbench, evidence trail) keep their own text; they get the column rule only. The tag register still has Title fourth.
- RFI and letter Details do not list Links (the Links tab and the header count do).
- One row shows every column (a single row has nothing to compare). At 170 columns an RFI log whose columns all vary still overflows the list's three fifths and scrolls sideways; the 3:2 split is unchanged.
- The correspondence highlight is shot at 200 columns for that reason.
- `State` colour (green, amber, red) from the skill is not applied; headings are bold grey and labels dim.
