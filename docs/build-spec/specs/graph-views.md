# Graph views: how facts, links and provenance are shown

Status: design v0.1 (proposed). Design only; all build deferred (`DEFERRED.md:50`).
Data model, verification and scoping: `docs/adr/0026-attested-bitemporal-graph.md` (proposed). This spec only says how
the facts are surfaced. Builds on: the log standard (`packages/tl-tui/README.md` "Log screens"), skill `tui-layout`,
web look v2 (`web-look-v2.md`), the record-panel pattern of `drawings-model-panel.md`, ADR-0016.

## 1. The contract the views consume
Two read routes in `tl_api`, called by the web, the TUI (through `ClientInterface`) and later an MCP read tool. No logic in
the TUI; both run as the caller's viewer, so hidden looks exactly like missing.
- `GET /records/{id}/graph?known_on=&as_of=&depth=` returns the record's facts, its neighbours and each fact's provenance.
- `GET /projects/{p}/graph?known_on=&as_of=&module=&category=&party=&cursor=` returns a page of nodes and edges for the
  project view, bounded by a work limit.
Rules every answer follows: **two dates**, `known_on` (what the ledger knew: transaction time) and `as_of` (how it stood:
valid time), both default to today and neither is ever later than today; no totals, no "hidden" counts; a fact whose valid
time is unknown says `date not recorded`, never a guess; times are plain days in plain mode and instants in technical mode.

## 2. Record graph mode ("Show in graph")
Opens from a record. TUI: a record-screen tab `Graph` (key `8`; `7` is Locations) and a log-panel toggle `G`. Web: a view
in the web increment, button `Graph` beside the record tabs. Same sections, in the `tl_tui.layout` `Page` order
(narrative, key facts, people, dates, timeline, record, technical):
| Section | Lines |
|---|---|
| Identity and state | `P123-NCR-0042 · Weld repair on line 47-12`, `Open · since 2026-10-13`; the as-of line `Showing: as it stood 2026-10-01, as known 2026-10-03` |
| Facts | One `Prop` per fact: label, value, `valid 2026-09-28 to —`, `recorded 2026-10-02 by kchan`. A corrected fact shows the new value with `corrected 2026-10-05, was 4 in`; a retracted one is shown only for dates before the retraction |
| Neighbours | Table: Relation, Record, State, Since. Groups: links, constraints on this record, targets of a constraint raised here, intents that name this record as an end state ("toward this") |
| Provenance | Press Enter on a fact: the event (type, time, who, why), the chain of causes (proposal, then accepted by), and the check result in words: `Verified`, `Verified, not yet sealed`, `Cannot be checked from here`, `Does not match the ledger` (technical mode adds hash and `seq`; `layout.find_technical` walks it) |
**As-of control.** Two fields in the crumb row: `As it stood [today]` and `As it was known [today]`, `[` `]` step a day,
`=` resets, `d` opens a date form (`ActionFormScreen`; ISO day, or `-7d`). Changing either re-reads the panel. The
neighbours follow the dates; a record that did not yet exist reads `Did not exist on that date` (same text as the evidence
trail's 422). The control never offers a date before the project began.

## 3. Project graph view
A log screen (`LogScreen` subclass, `GraphLog`): one row per node, columns Number, Subject, State, Module, Party, Open
constraints, and `1`/`2`/`3` switch the view: **Nodes**, **Edges** (From, Relation, To, Since), **Constraints**.
- Filters: `/` text; `m` module, `c` category, `p` party (internal viewers only; a party viewer has none, its scope is fixed),
  each a small form; chosen filters show in the crumb.
- **Time slider.** Web: a range input with day ticks over the project's life plus the two date fields; dragging debounces
  200 ms and re-reads. TUI: `[`/`]` step a day, `{`/`}` a week, `Home` the project start; no slider widget. Both set
  `as_of`; `known_on` is a separate field, so "what we knew" is never confused with "what was true".
- **Saved questions** (a `?` menu; data in `schema/fixtures/graph/questions.yaml`, not code): each is a named filter plus
  a walk, run through the same route.
  - "What blocked WP-123 on 1 October and who cleared it": constraints on WP-123 open on that day, the person and event that
    cleared each, and the date it cleared.
  - "Every constraint still open on the pipe rack": constraints whose target is in the rack's tag or area subtree and that
    are open today, oldest first, with the owner.
  - Others to add by data: "intents toward this end state", "links added by an agent not yet verified".
  A question can be pinned to a log's key row and shared inside the project (a stored saved view, ledgered as a record).
- Panel: the selected row's record graph mode, **following the selected row** like the drawings and model panel: a
  `GraphPane` with `selected_key`, a 200 ms wait, a worker read, an answer for a row no longer selected is dropped
  (`drawings-model-panel.md` section 3). It sits beside or under the record panel by the same width rules (right from 200
  columns in the TUI; third column from 1600 CSS px in the web, a drawer from 1280, stacked below).
- Web only: a node-link picture (an optional drawing of the neighbours, small cap of 200 nodes, text list always present).
  The terminal shows the Neighbours table, never an ASCII drawing.

## 4. TUI or web
| Piece | TUI | Web |
|---|---|---|
| Record `Graph` tab, neighbours, provenance, as-of fields | Yes (increment 1) | Yes, as page partials (`templates/page.html`) |
| Project `GraphLog` with filters and day stepping | Yes | Yes (list, panel, actions as today) |
| Range slider, node-link picture, share a saved view | No | Yes |
| Saved questions menu | Yes, a form with the list | Yes, a select above the list |
Both render the same `Page` (`tl_tui.layout`); the web macro turns it to HTML. Empty states are one text each, identical for
"nothing here" and "everything hidden": `No facts for this record on that date.`

## 5. Confidentiality (ADR-0016, ADR-0026 section 5)
Record first: hidden or missing is `record_not_found`. Neighbours and facts are filtered in one batch per page by the viewer
(`hidden_sql`, and `Viewer.party` once P3-I8 T01 lands); an edge to a hidden node is dropped, not stubbed. Provenance lists
only events the viewer may read and never shows a `seq` or hash of anything else. A party viewer's graph is its scope plus one
`belongs_to` hop; the saved questions that name a party filter are not offered. Tests: the walking test classifies both routes
and runs the seven readers (user, controller, agent, admin, system, external, guest); a twin test compares whole responses for
a record with no facts and one whose every fact is hidden. Known limit, as in the locator spec: response time grows with hidden rows.

## 6. Effort (S = Sonnet builder piece, H = Haiku ticket of one file area, one gate)
Prerequisite (not here): ADR-0026 accepted; `cur_facts` projector and `tl:valid_time` tags on about 47 classes (1 S + 2 H, ADR-0026 plan check F4, F5).
| Piece | Size |
|---|---|
| `GraphReader` core service: as-known and as-stood folds, two-date filter, viewer batch filter | 1 S |
| Provenance and verification read (event, causes, check result words) | 1 S |
| Routes, paging and work bound, errors, walking and twin tests, `ClientInterface.graph` | 1 S |
| Saved-question loader and the two first questions as data and tests | 1 H |
| TUI `Graph` tab, as-of fields and date form | 1 S + 1 H (tests) |
| TUI `GraphLog`, filters, day stepping, `GraphPane` follow hook | 1 S + 1 H |
| Web partials: graph panel, neighbours, provenance, as-of form, out-of-band swap | 1 S + 1 H (CSS, tests) |
| Web range slider and node-link picture | 1 S + 1 H |
| Docs, runbook, demo script | 2 H |
Total: 7 S and 6 H, after the Phase 3 chain and projection work, in Phase 4. The TUI side (2 S, 3 H) can land first.
## Open questions for the owner
1. Are saved questions per project, per user or both? 2. Is the node-link picture wanted in v1 or is the table enough?
3. May an external party see the provenance list of its own facts (who recorded them, by name) or only the party name?
## Plan check (2026-11-07)
Findings F8–F11 of the ADR-0026 plan check apply here and are accepted (answers in the ADR). In short: verdict words come
from a server-side check, and "Cannot be checked from here" is for replicas only. Counts are of visible rows. Every hop
filters. Sharing a saved view is deferred. Effort is 2 S + about 10 H. v1 is the tab, `GraphLog`, the modal and the web
drawer. The slider, picture and following pane come after the web increment. Project start does not use `Home`.
