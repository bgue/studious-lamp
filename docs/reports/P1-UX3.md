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

# Round 2: summary line, relevant fields, tables, short logs, one-line keys, colour

**Deviation first:** again no test was run (owner's instruction); `just check` is clean. Two changes outside the TUI code: `dev/tour/tourkit.py` no longer sets `NO_COLOR` for the whole run (it made every screenshot grey; now only the `tl` command line runs with it), and `dev/tour/phase1.py` has the document-register needles in words. Every shot of both tours was regenerated, so colour shows in all of them. The highlight tour is byte-identical on two runs; no `LEAK` line in any tour.

## What changed, screen by screen (before, after)

| Screen | Before | After |
|---|---|---|
| Every log panel | identity and state only | a dim summary line under the state, 3 or 4 facts joined with ` · `, wrapped between facts at 56 cells (`layout.Page.summary`) |
| RFI panel and Details | Kind row; clocks and timeline as run-on lines; no links | summary (discipline, needed by, to, days open); `Answer required, round 1/2`; clocks, timeline, files as tables; `Links (n)`; red `overdue 3 days` on the state line |
| Letter panel and Details | `Domain: Letter` and `Medium: Letter`; Received, Sent, Triaged on for every letter; From `—` | summary (direction, with, reply due); Medium only when it differs from the domain; outgoing: Issued, Sent, drafter as From; incoming: Received, Triaged on, no To |
| Clock panel | State, Due, Item repeated in Key facts | state `Running`, summary (due, days left, owner); Item, State, Due, Days left are Details-only rows |
| Document panel and Details | `A(IFR)`, run-on revisions and links | `A, Issued for review` (scheme file labels); `Rev State Purpose Date Files` table; files `Name Type Size Pages`; links `Record Type Pin Status`, stale in red with `!`; Originator only when set |
| Commercial, tag, schedule, review queue, integration, schema workbench, evidence trail panels | own text lines | layout pages with summary, Key facts and tables (tag: Lacks table, Number parts; schedule: snapshot, Contents, Checks, look-ahead and orphans as tables; schema: People, Status, tab section; enrichers: Properties table) |
| Tag register | Number, Class, Status, Number check, Conformance, Title | Number, Title, Class, Status, Number check, Conformance; the state of a tag is its conformance |
| Correspondence register | Dir, Domain (`Request for information`), `[kind]` suffix, 200 columns for no scroll | `In/out` (In, Out, Int), `Category` (RFI, Letter, Transmittal, Notice; `Untriaged` when no domain yet), shown at 170 columns without scrolling |
| All logs | the list scrolled sideways when columns varied | `plan_columns`: constant columns hidden, `With` (and the document `Type`) shorten to 12 cells, then the least needed columns go (`*_DROP` lists), the subject keeps 26 cells; wide split 3:2 as before |
| File panel | `> name  kind  size` and `v or Enter: open in viewer` | header `Name Type Size Pages`, selected row reversed when there are several, no hint |
| Keys row | one long line, cut off | `Up/Down move`, the log's own keys, `Esc close`, `F1 more keys` (fits 80 and 100 columns by construction, `log_text.keys_row`); F1 in a log opens the key map with the log's keys on top |
| State colour | none | green done, amber waiting or running, red overdue, late or refused on the state line, the state cells of every log, the record header and table cells (ANSI colours of the terminal theme, word always written) |

## Stale pins for the next test run

Not run, not edited: in `packages/tl-tui/tests/` the pins of `test_tag_text`, `test_tag_plain`, `test_schedule_text`, `test_schedule_plain`, `test_schedule_more_plain`, `test_schedule_screen_pages`, `test_integration_text`, `test_integration_screen`, `test_integration_plain`, `test_review_plain`, `test_schema_text`, `test_schema_screen`, `test_schema_plain`, `test_schema_enter`, `test_evidence_text`, `test_domain_screen`, `test_domain_plain`, `test_rfi_text`, `test_rfi_record`, `test_commercial_text`, `test_commercial_plain`, `test_correspondence_text`, `test_correspondence_plain`, `test_correspondence_screen`, `test_document_text`, `test_document_register`, `test_document_plain`, `test_document_flow`, `test_file_panel`, `test_log_screen` and `test_log_migration` (`#log-keys` is no longer `KEY_HINTS`; `KEY_HINTS` stays as the full key text), `test_log_text` (`table_width` is 3/5 minus 1, `flex_width` unchanged), `test_record_view` and `test_record_plain` (the header is a styled `Text`), `test_details_registry`, `test_record_files_tab`, `test_plain_walk`, the snapshots under `__snapshots__`, and the demos `dev/demos/p1_i2_demo.py`, `p1_i5_demo.py`, `p1_i6_demo.py`. New tests wanted: `layout.render` with tables, `wrap_facts`, `state_style`; `log_text.plan_columns` and `keys_row`; `document_text.status_labels`; `details.link_rows` and `file_rows`; `clock_names`.

## Not done

- `Email` as a category: the register line carries no medium, so an item with no domain reads `Untriaged`. Adding the medium to `RegisterLineView` changes the API schema (`docs/reference/openapi.json`) and was left alone.
- A panel does not adapt to its width: a table wider than the panel (the revisions table at 160 columns) wraps its last columns; a summary breaks only between facts.
- The Details tabs of schedules, schema packages and the other registry rows keep their generic rows; only the panels moved to the shared sections. Evidence facts still show stored codes (`early_warning`).
- Keys rows of non-log screens (forms, admin, the review screens) are unchanged.
