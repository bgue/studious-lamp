# Increment plan — P1-UX usability: one record screen, plain language, property sets

Status: in-progress (round 5: T01-T03 merged; wave 4 = T05, T06, T09e dispatched)
Supervisor session: 2026-10-21 (rounds 1-4)
Brief sections: §6.3 (psets), §9 M2/M10, §10 (TUI), ADR-0010, ADR-0016
Branch: `p1/ux`
Input: `SCOPE.md` (owner request 2026-10-21). Owner decision 2026-10-21: scope is SCOPE clauses 1-5; the
example property sets for documents, RFIs and correspondence are approved (orchestrator records APPROVALS);
the technical-details toggle is for admins only.

## Objective
Make the Phase 1 TUI usable by a mainstream AEC user without changing any stored data, command, event, API, MCP
or CLI output. Enter on any list row opens one record screen (Details, Properties, Links, History, Thread).
Every screen speaks plain language by default: type, code-list, domain and property labels with units; no ids,
hashes, schema versions or internal keys. An admin can switch the technical details on and off with one key.
Documents, RFIs and correspondence get example property sets in the fixture company standard.

## Findings from the survey (what the plan rests on)
- `RecordView` (widgets/record_view.py) lives in the main area and is opened by `OpenRecord(scope, key)`.
  The register screens (documents, tags, correspondence, domains, schedule, review queue, integration) are
  `ModalScreen`s with their own `DataTable`; none opens a record. Their view rows all carry the record `id`;
  `ClientInterface.get_record_by_id` exists and is viewer-filtered (hidden = `None`).
- Details today shows only envelope fields (key, type, status, `Schema #a91f…3c`). A module record's own
  fields (ADR-0010 side table) are shown only in each register's bottom panel, as raw codes.
- `PsetsTab` is the Properties tab under the name "Psets". It calls `client.form_metadata(scope, type)` without the
  record id, so class-bound sets (tags, ADR-0010 decision 5) are missing. `psets.form_metadata` already accepts
  `record_id`; the API route `GET /schema/forms` and the client do not pass it.
- Psets reach module types through `applies_to` (the fixture's `provenance` already lists
  `engineering.Tag, documents.Document`). Record types: `documents.Document`, `correspondence.Correspondence`,
  `correspondence.TechnicalItem` (RFI), `correspondence.CommercialItem`, `correspondence.ResponseClock`,
  `schedule.Schedule`, `schedule.ScheduleSnapshot`, `engineering.Tag`.
- Class names have no `title` in the module LinkML today, so no schema label exists for "Control valve" style
  type names. `FieldMeta.label`/`unit` and pset labels exist.
- Key map: all F1-F12 and Ctrl+A/E/G/N/O/P/Q/R/S/T are taken. `app.is_admin` exists (F10 uses it).
- Fixture `co.acme.engineering@3.2.0.yaml` is the only version; the P1-I8 demo derives its 3.3.0 draft from it by
  two text anchors (`version: 3.2.0\n`, `\n\n  safety_data:`, and one `        range: decimal\n`). The
  new sets must keep those anchors unique (or the piece updates `dev/demos/p1_i8_demo.py`).

## Decisions taken in this plan (reversible; the plan check may overrule)
| # | Decision |
|---|---|
| D1 | Record screen from a register is a `RecordScreen` (modal) pushed on top of the register; Esc dismisses it, so the register is back on the same row. No change to how the main-area record view opens. |
| D2 | Details for module types is built per type from the typed views the registers already read (no new API route). A package `tl_tui/details/` holds one module per area; a registry picks by record type; a generic envelope fallback covers the rest. Each screen ticket adds its own file, so tickets stay disjoint. |
| D3 | Type labels: LinkML `title` on every record-type class (schema, owner gate) plus a generated `type_labels.py` from `just gen`. Fallback when a type has none: split CamelCase into words. |
| D4 | Fixture sets are added **in place** to 3.2.0, additive, not a new version (3.3.0 is used by the P1-I8 demo). |
| D5 | Technical mode is in-memory state on the app (`DisplayMode`), off at start, admin-only toggle, not remembered. A "remember" setting is not built. |
| D6 | `GET /schema/forms` gains an optional `record_id`; the answer only differs for a visible record. The API/MCP/CLI output otherwise stays as is. |
| D7 | Toggle key is `Ctrl+D` (palette entry "Technical details"); T10 binds it (owner/orchestrator answer to Q3, 2026-10-21). |
| D8 | `title` on module classes and generated `type_labels.py` are additive display metadata covered by the owner approval of 2026-10-21 (answer to Q2; orchestrator records APPROVALS). |
| D9 | S1 became Haiku ticket T00 (plan check F10): same spec, id and branch renamed `T00-display-helper`, `p1/ux-t00-display-helper`. |

## Demo `just demo P1-UX` (SQLite and Postgres) — clauses
1. From each register (documents, tags, correspondence register/inbox/clocks, RFI log, commercial, schedule/cost
   lists, review queue) Enter opens the record screen; its Properties tab lists the sets for that type with labels.
2. As a plain user a test walks the screens and greps the rendered text: no ULID, hash, schema version, internal
   key, clock or calendar id; the toggle key answers with a one-line refusal.
3. As an admin the toggle shows those details and hides them again.
4. A restricted record opened from a stale list row by a plain user reads exactly like a missing one.
5. The tours regenerate with no diff on a second run (`just tour-all`); PHASE-1-TOUR.md has the new section.

## Builder pieces (in order)
| # | Piece | Why builder | Reviewer | Status |
|---|---|---|---|---|
| S3 | Schema: example sets in the fixture, `title` on record-type classes, generated `type_labels.py` (also fixes the tl-tui pins and snapshots that render 3.2.0) | `schema/**` and the generator; human gate | full | dispatched r2 |
| S2 | Record screen for module types: `RecordScreen`, `open_record`, Details registry (documents the only bespoke renderer), `form_metadata(record_id)` through client, `tl_api` client, embedded, fakes and the API route, Properties tab with plain rule words | Client contract and a route that can carry record text (ADR-0016 walking test) | full | spec written; dep T00 S3 |

Specs: `T00-display-helper.md` (a ticket since r2), `S2-record-screen.md`, `S3-fixture-psets-and-labels.md`.

## Tickets (all `tier haiku`; T00 written, the rest written one batch ahead from the tree after S2 merges)
| ID | Title | Depends | Review | Allowed area |
|---|---|---|---|---|
| T00 | Display helper: labels, plain-language rules, `DisplayMode`, `find_technical(text, labels=None)` (was S1) | none | full | tl_tui/display.py, text.py (units), test_display.py |
| T01 | Documents register: Enter, plain text (document Details exist since S2) | T00 S2 S3 | full | document_register.py, document_text.py |
| T02 | Tag register: Enter, plain text, tag Details | T00 S2 S3 | full | tag_register.py, tag_text.py, details/tags.py |
| T03 | Correspondence register, inbox, clocks: Enter, plain text, item and clock Details | T00 S2 S3 | full | correspondence_screen.py, correspondence_text.py, details/correspondence.py |
| T04 | Domain screen and RFI log: Enter on all three modes, plain RFI text, RFI Details; wires T05's text into domain_screen (r4: domain_screen imports commercial_text, evidence_text, rfi_text) | T00 S2 S3 T05 | full | domain_screen.py, details/technical.py |
| T05 | Commercial, RFI and evidence text: plain words (optional labels/technical kwargs, `Status` column dropped D26), RFI clock pin fix, commercial Details; no screen change | T00 S2 T03 | lite | commercial_text.py, rfi_text.py, evidence_text.py, details/commercial.py |
| T06 | Schedule screen (no cost screen exists): Enter, plain text, schedule and snapshot Details | T00 S2 | full | schedule_screen.py, schedule_text.py, details/schedule.py |
| T07 | Review queue: Enter on a proposal; review values carry `target` RecordRef so Enter has an id | T00 S2 | full | review_queue.py (+ its text) |
| T08 | Record tabs and shared panels: context panel, record grid type column, links tab, thread tab | T00 S2 | full | context_panel.py, grid.py, links_tab.py, thread_tab.py |
| T09a | Integration registry: Enter on rows, service labels, no ids (with T07) | T00 S2 | full | integration_screen.py, integration_text.py |
| T09b | Accounts and about:config screens plain (r3: schema part split to T09c) | T00 | full | admin_text.py, settings_text.py, admin_screen.py, setting_history.py, settings_screen.py |
| T09c | Schema workbench and review plain (split from T09b, r3) | T00 | full | schema_text.py, schema_review_text.py, schema_screen.py, schema_review_screen.py |
| T09d | Enter on schema package rows opens the record screen (after S2; written then) | S2 T09c | full | schema_screen.py |
| T09e | about:config layer words in the panel line and the edit form (T09b review leftovers, r4) | T09b | lite | settings_text.py, setting_form.py |
| T10 | Toggle key `Ctrl+D`, help (from keymap), palette entry, refresh hook, T00 LO nit F1 (find_technical dedupe) | T00 | full | app.py, keymap.py, commands.py, display.py |
| T11 | Walking test (screen list generated from keymap.py, plain user greps each; hidden = missing) and `dev/demos/P1-UX.sh` (sets document/RFI/correspondence values) | T01-T10, T13 | full | tests, dev/demos/ |
| T12 | Tour re-shot (phase0, phase1, new section), narratives, PHASE-1-TOUR.md; tour world sets `document_data`, `rfi_data`, `correspondence_data` values (dev/tour/tourkit.py, phase1.py `update_psets`) | T11 | lite | dev/tour/, docs/reports/ |
| T13 | Main screen plain (`t f`): feed pane, header, main area, ref tray, link picker | T00 S2 | full | feed_pane.py, header.py, main_area.py, ref_tray.py, link_picker.py |

17 tickets plus 2 pieces (r3: T09c, T09d added); the plan check (below) is applied. Record tabs other than Details and Properties are T08;
the screens T11 walks are every entry the keymap opens (generated, not hand-written).

## Order of work
1. Wave 1: T00 and S3 in parallel (disjoint: `tl_tui/display.py` vs `schema/`, `generated/`, `dev/seed`, tl-tui pins).
2. Wave 2: S2, T09b, T10 (S2 needs T00 and S3; T09b and T10 need T00 only).
3. Wave 3: T01 T02 T03. Wave 4: T04 T05 T06. Wave 5: T07 with T09a, T08 with T13 (two workflows).
4. Wave 6: T11. Wave 7: T12.
5. DONE: full gate, `gate-pg` on touched directories, security review `Sec: S2 (routes/reference.py record_id,
   record_screen hidden=missing), S3`, range `4b2cda0..<head>`, one reviewer per item.
Checkpoints: C1 T00+S3 merged; C2 S2 merged; C3 T01-T10 and T13 merged; C4 T11-T12 merged and DONE.

## Risks and escalation triggers
- Snapshot churn: every screen ticket regenerates its own TUI snapshots and names the snapshot test in its gate
  (L-P1-I8-13). T10 adds a keymap line and a palette entry: both snapshots.
- Postgres/SQLite parity of anything S2 reads (L-P1-I5-1): S2 runs its tests on both.
- Viewer defaults to the lowest clearance (L-P1-I5-2): tests that read a restricted record run inside `use_viewer`.
  A route or tool change needs the five-reader walking test; `GET /schema/forms?record_id` is the one new surface.
- A modal closed with `pop_screen()` does not run its callback; the record screen and tests use `dismiss`
  (L-P1-I8-15).
- Tests that need "no session" in the CLI set `AUTO_SIGN_IN = False` (L-P1-I3-7); the demo script signs in as a
  plain user and as an admin explicitly.
- In-place fixture edit may move pinned counts or hashes in `tl-schema`, `schemareg`, `tl-tui` tests and
  `dev/demos/p1_i8_demo.py` anchors. S3 owns finding and fixing them. Escalate if a pinned effective-schema hash in
  a committed sample must change.
- Detail renderers need the typed view for a record id; the documents, correspondence and schedule clients take
  project plus number, not an id. S2 proves one renderer end to end; a missing id-keyed client method is an
  escalation (a contract change), not a ticket.
- Hidden text is a moving target; the leak finder (T00) and the walking test (T11) are the guard.
- Escalate to the orchestrator if: a screen needs text that no schema label provides and S3 cannot add it; the
  admin-only toggle needs a role the client cannot report; Postgres parity fails on a detail view.

## Blocked / Decision
(filled during escalation)

## Plan check
`4 PLANCHK` answered by the orchestrator (r2). Go with fixes; every finding accepted and applied.
- F1 HI applied: S2 Allowed paths add `tl_api/client/links.py` and its client test (remote `form_metadata` sends `record_id`).
- F2 MD applied: rule words, set label and the `Effective schema #…` line go to S2; T08 = context_panel, grid, links_tab, thread_tab.
- F3 MD applied: T11 lists the walked screens (generated from keymap); record tabs to T08; new T13 for the main screen.
- F4 MD applied: T09 split into T09a (integration, with T07) and T09b (admin, settings, schema); Q1 rejected; T05 stays lite, drops its T04 dependency.
- F5 MD applied: `find_technical(text, labels=None)`; domain keys only for domains the labels know; ignore test adds `m/s`, `kg/m3`, `N/A`, `2026/10/21`.
- F6 MD applied: S3 Allowed paths add the tl-tui pins, snapshots and `test_schema_text.py` that render 3.2.0.
- F7 LO applied: T12 sets the three data sets' values in the tour world; T11 does the same in `P1-UX.sh`.
- F8 LO applied: integration registry rows get Enter (T09a); T05 names the commercial State/Status duplicate column drop.
- F9 LO applied: waves as in Order of work.
- F10 LO applied: S1 is Haiku ticket T00 (sentinel and 4 mutants kept), id renamed (D9).
- F11 LO applied: DONE security review rows and range in Order of work.
- F12 LO applied: T11 generates its screen list from keymap.py; S2 keeps documents the only bespoke renderer, others generic, getters escalated.
Q2 and Q3 answered: D8, D7.
