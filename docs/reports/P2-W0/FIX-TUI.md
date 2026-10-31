# P2-W0-FIX: TUI group (tl-tui tests, 134 failing ids in 40 files)

Branch `p2/w0-fix-tui` from `p2/w0` b865595. All 134 now pass. No test skipped, xfailed or weakened.
Tests renamed (their claim changed): `test_a_tag_that_is_offered_nothing_has_only_add_property_and_the_open_key`,
`test_an_item_with_no_body_or_history_has_a_dash_for_the_message_and_no_timeline`.

## By cause (counts add to 134)
| Cause | n | What was done |
|---|---:|---|
| A. Pure text and Details rows read the old one-line forms (`id  state  kind  class x`, `question:`, `Type/Number/Subject/State` rows, `-`, columns State before Subject) | 49 | (a) tests now read the page: heading `number · subject`, state line, summary, named sections, tables, `—`; columns Number, Subject, State first |
| B. Screens: the panel is a scrolling widget, so text below the first lines is not on the drawn screen; links and files sit in their own widgets | 45 | (a) new helpers `panel_of` and `static_of` in `tests/helpers.py` read the whole panel (`#log-panel-text`, `#doc-links`, `#fp-lines`); expectations follow the sections; header holds number, title, state |
| C. File panel: the chosen file is a reversed row of a Name/Type/Size/Pages table, not `> name` | 7 | (a) `shown()` reads `.content`; table lines expected |
| D. Keys row: `Up/Down move`, the log's own `KEY_CELLS`, `Esc close`, `F1 more keys` | 12 | (a) `test_log_migration` checks the structure and that all own keys fit at 120; `Host` in `test_log_screen` declares `KEY_CELLS` |
| E. `[+] Add property` is in every record log's actions bar (before `[Enter] Open record`) | 5 | (a) bars updated; see Q1 |
| F. Snapshots | 14 | regenerated, diffs read (below) |
| G. `_typed("nan")` and a fake that no longer answers an unknown record | 2 | one (b), one test fix |

Other test repairs: `fakes_rfi_record.py` gives the first RFI its own clocks in its view (the timeline reads `view.clocks` since P2-PERF; the fake only listed them); `test_rfi_record` no longer assumes a clock outcome sorts after the event rows (the walk's events carry the wall-clock day); `test_standard_code_labels` world has two disciplines (a constant column is hidden) and the document register is opened at 150 columns (at 170 the panel takes half the width and Discipline drops); `test_domain_plain` checks the Kind column on the Commercial register (the RFI log hides it).

## (b) code changes
- `widgets/add_property_form.py:412` `_typed` kept `"nan"`/`"inf"` as floats (they read back equal but are not JSON numbers); now `math.isfinite(...)`; `import math` at :21.
- `evidence_text.py:30` void record with no state showed `-`; now `EMPTY` (`— VOID`).
- `integration_text.py:67,202,209,245,293,332,349` `-` for empty time, error, About, Parameters and Error lines; now `EMPTY`. Pins in `test_integration_text`/`test_integration_plain` changed to `—`.
- `schema_text.py:65` `Class` cell of the versions table showed `-`; now `EMPTY`. Pins in `test_schema_text` changed.

## Regenerated snapshots (each diff read as drawn text)
- `test_log_screen/…_80x24`, `…_170x30`: keys row only (`Up/Down move  / filter  o open only  Esc close  F1 more keys`).
- `test_snapshots/test_record_view_history`, `test_snapshots_links/test_links_tab`, `…_links_tab_narrow`, `…_trace_tab`: footer gains `+ add property (Properties tab)`; nothing else.
- `test_snapshots/test_record_view_details`, `…_record_view_narrow`, `test_snapshots_links/test_link_picker`, `…_record_view_header_badges`, `…_reference_tray`, `…_workflow_menu`: Details tab loses the Title row (it is the header), gains `Summary` and `Record` section headings; footer as above.
- `test_snapshots/test_psets_tab_conformant`, `…_nonconformant`: `[+] Add property` line on the Properties tab; footer as above.

## Gate (`just gate`, groups of 13 to 14 files, one at a time) and check
- 13 files (add_property … evidence_text): `part 1: exit 0, 102 passed in 51.59s` `gate: PASS`
- 13 files (file_panel … rfi_record): `part 1: exit 0, 163 passed in 110.49s` `gate: PASS`
- 14 files (rfi_text … tag_text): `part 1: exit 0, 123 passed in 74.13s` `gate: PASS`
- regression run of 9 passing files that use the changed modules (plain_walk, schema_text, review, palette …): `109 passed in 539.56s` `gate: PASS`
- `just check`: ruff, format, pyright 0 errors, codegen drift, licences: all clean.

## Open questions (c), nothing changed
1. `log_actions.py:332-382` `add_property_actions` hides `[+] Add property` only for agents and voided records, so a reader whom the service will refuse sees it (`test_log_actions` reader bar). Skill: the bar names only offered actions.
2. Panels in technical mode show the label where the old text showed the code (RFI Discipline, tag Area) and drop two raw items: the property path in the tag `Lacks` table, and the endpoint version in the error-queue panel (`integration_text.IDENTITY_LABELS` holds `Endpoint`). Tests now expect the new form.
3. `-` still stands for empty in `schedule_text.py` (62-140), `schema_text.py` header and Defines lines, `schema_review_text.py`, `derive_text.py`, `correspondence_text.py:103`; passing tests pin them, so not touched.
4. RFI panel `overdue 12 days` and `26 days open` use the wall clock (`rfi_text.days_open`, `overdue_note`); the log cell uses the report (`overdue 1d`). They can disagree; no test pins the panel numbers.
5. `Orphaned links` panel with none says `None: every activity …` (schedule); read as a sentence, left.
