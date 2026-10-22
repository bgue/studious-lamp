# P1-UX2 report: the log standard, actions, the RFI record and document preview

Status: built; waiting for the one whole-suite run (owner decision, below). Plan `docs/tickets/P1-UX2/README.md`, scope `SCOPE.md`, board and decisions `STATE.md`, piece reports in `docs/reports/P1-UX2/`.

## Objective (owner, 2026-10-21)
"Our logs should tell us where we are (RFI Log), what record we're on (RFI-0328: Conflict in piling/utilities at AZ203), and what actions to take. Our RFI record should have not only its metadata but the usual narrative information of question and answer, status updates, and list of attached files. Our document log should provide a click to preview or a file preview of the first page of the file if it's a PDF." TUI only; no change to commands, events or stored data.

## What shipped (SCOPE sections)
| # | Clause | Result |
|---|---|---|
| 1 | One log standard | `LogScreen` (S2): breadcrumb `P123 › RFI log › <number>: <title>`, list in plain words, panel below the list (right of it from 160 columns), actions bar, keys row, status line. Every log moved to it (S3, S4): documents, tags, correspondence register, triage inbox, clocks, RFI log, Commercial register, evidence trail, schedules, review queue, integration registry, schema workbench. Written down in the tl-tui README ("Log screens") |
| 2 | Actions from the server | `allowed_actions(record)` (S1): the module that owns the record answers from its state machine and the role rules; hidden = missing (ADR-0016); additive API route, embedded and remote clients; ADR-0010 addendum. The bar shows only what the viewer may do; a command's refusal lands in the status line. Answer opens a small form (`ActionFormScreen`) and sends the existing command |
| 3 | The RFI record | Question, proposed solution and answer first (long text wraps, nothing cut); a status timeline, oldest first, with date, person and note (S5); a Files tab (key `6`) when the record has files |
| 4 | Document preview | `v` or Enter on the file line opens the current revision in the system viewer from a private temp copy checked by size and sha256; the panel shows page 1 as a picture where the terminal can, else `PDF document  789 B  3 pages` (S4). Rendering: pypdfium2 in a resource-limited child process, cached by content hash (D4) |
| 5 | Demo and tour | `just demo P1-UX2` passes 4/4 on SQLite and Postgres (about 9.5 minutes for both); `just tour-all` twice: no `LEAK`, second run changes no file; 27 + 81 shots; new PHASE-1-TOUR section 24 |

## Decisions worth knowing (STATE D1-D10)
- D1 `ModuleSpec.actions` hook, additive; D2 the server returns command and label, the key and form table lives in the TUI; D3 Haiku only for T01/T02, all tl-tui work `review: full`; D4 PDFs render in a child process with time, size, pixel and memory caps; D6 raw code labels fixed in `labels_load`/`display`, `schema/**` untouched; D7 all client additions in S1; D8 no plan check (8 items).
- D5/D9 owner chose a viewer plus a thumbnail. `textual-image` was approved as "permissive" and is LGPL-3.0-or-later: S4 stopped (licence check), and the owner approved **rich-pixels 3.0.1 (MIT)** instead; one named allow-list entry in `check_licences.py` (its wheel declares no licence, only an MIT LICENSE file). pypdfium2 5.14 (BSD-3/Apache-2.0) and Pillow 13 pass.
- D10 (S3, Allowed paths widened): plain logs showed codes (`STR`, `ISO`, `PIP`, `47`). `list_code_lists(scope)` now reads the standards' code lists (embedded and remote, no new route) and `labels_load` keys each by column and list name; plain reads "Structural", "Isometric", "Piping", technical keeps the codes.
- Two keys moved because the bar needs their letters: evidence trail `e` -> `t` (`e` escalates an RFI); response clocks "add the closed ones" `c` -> `m` (`c` is Close). README, F5 help and tour text say so.

## Process decisions by the owner for this increment
- No security reviews. The two rows left open in STATE SEC (Sec1 allowed-actions query; Sec2 open/preview path) were not reviewed; the mutation checks in S1 and S4 cover the access words, the `%PDF-` check, the size cap, the kill on timeout, the 0700 folder and "no shell".
- Testing deferred: each piece ran `just check` and only the tests it touched or added; the whole suite runs once, at the end.

## Gates
| Gate | Result |
|---|---|
| `just check` at each piece | clean (S1-S5) |
| S1 (before the policy): core, three modules, API, tl-tui | 5635 passed; `gate-pg` 2428 passed |
| S4/S5 tl-tui package | 1525 and 1486 passed; `gate-pg` embedded real services 7 and 10 passed |
| `just demo P1-UX2` (S6) | `P1-UX2 demo OK on: sqlite postgres` |
| `just tour-all` x2 (S6) | exit 0, no `LEAK`, second run no change |
| Whole suite `just gate` on the merged branch | <<fill>> |
| `just gate-pg` on touched adapter and ledger paths | <<fill>> |

## Deviations
- Four container restarts ended running agents and workflow runs (three before S6, one during it); each piece resumed from its last commit. In S6 the orchestrator committed the builder's work in progress (`dc73cdd`); the demo had passed SQLite and was seeding Postgres. Learning L-P1-UX2-2.
- S3 widened its paths for D10; S1 put `document_command` and `engineering_command` in `tl_api/client/records.py`; S4 changed the three dev scripts for the renamed table ids.
- S6 added `fit_tables` to `dev/tour/tourkit.py`: the first `just tour-all` failed once ("timed out waiting for the document register") and a later run changed `19c`, both by the cause in follow-up 1. Shots now measure and redraw tables before they are read; no committed shot changed.
- The tour has a seventh shot (`24g`, the RFI log for a controller) beyond the six in the spec; 24f shows a plain user, because an agent cannot open the TUI.

## Follow-ups
1. A Textual table keeps frames drawn before it measures its cells, so a log can show every column as wide as its header (`Path`, `acme`) until a reload; seen in the headless tour about every other run, not seen live. A product fix is one line in `LogScreen._fill` (clear the table's caches after adding rows); S6 may not touch screens, so only the tour was hardened.
2. Not looked at on a real image terminal (kitty, iTerm2, WezTerm): the thumbnail has no snapshot and the tour runs with `TL_IMAGES=off`.
3. `MergeTags` and `RecordResponse` have no UI entry (they need a picker); `list_clocks` has no `item=` argument (S5 filters in Python).
4. T02 left two readings open: an unknown content type with a known extension reads `File`; `1048575` bytes reads `1024.0 KB`. T01: `TL_IMAGES=""` counts as set.
5. Security reviews Sec1 and Sec2 are open until the owner asks for them.

## Showcase
`docs/reports/PHASE-1-TOUR.md` section 24, "The log standard, the RFI record and document preview", shots `24a`-`24g`. Run `just demo P1-UX2` for the four clauses live.
