# Increment plan — P1-UX usability: one record screen, plain language, property sets

Status: planning
Supervisor session: 2026-10-21 (round 1)
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
| S1 | `tl_tui/display.py`: labels, plain-language rules, `DisplayMode`, leak finder | One shared helper every screen uses; its rules decide what the whole TUI hides | full | spec written |
| S3 | Schema: example sets in the fixture, `title` on record-type classes, generated `type_labels.py` | `schema/**` and the generator; human gate | full | spec written |
| S2 | Record screen for module types: `RecordScreen`, `open_record` helper, Details registry, `form_metadata(record_id)` through client, embedded, remote, fakes and the API route, Properties tab, `load_labels` | Touches the client contract and a route that can carry record text (ADR-0016 walking test) | full | spec written |

Specs: `S1-display-helper.md`, `S2-record-screen.md`, `S3-fixture-psets-and-labels.md`.

## Tickets (all `tier haiku`; written after the plan check, in round 2)
| ID | Title | Depends | Review | Allowed area |
|---|---|---|---|---|
| T01 | Documents register: Enter, plain text, document Details | S1 S2 S3 | full | document_register.py, document_text.py, details/documents.py |
| T02 | Tag register: Enter, plain text, tag Details | S1 S2 S3 | full | tag_register.py, tag_text.py, details/tags.py |
| T03 | Correspondence register, inbox, clocks: Enter, plain text, item and clock Details | S1 S2 S3 | full | correspondence_screen.py, correspondence_text.py, details/correspondence.py |
| T04 | Domain screen and RFI log: Enter on all three modes, plain RFI text, RFI Details | S1 S2 S3 | full | domain_screen.py, rfi_text.py, details/technical.py |
| T05 | Commercial and evidence views: plain text, commercial Details | T04 | lite | commercial_text.py, evidence_text.py, details/commercial.py |
| T06 | Schedule and cost lists: Enter, plain text, schedule and snapshot Details | S1 S2 | full | schedule_screen.py, schedule_text.py, details/schedule.py |
| T07 | Review queue: Enter on a proposal that names a record, plain text | S1 S2 | full | review_queue.py (+ its text) |
| T08 | Shared screens: record view header and History, Properties tab (rule words, set labels, no schema line), context panel, record grid type column | S1 S2 | full | record_view.py, psets_tab.py, context_panel.py, grid.py |
| T09 | Other screens plain: integration registry, accounts, settings, schema workbench and review (service labels, no ids) | S1 | full | integration_*.py, admin_*.py, settings_*.py, schema_*.py |
| T10 | Toggle key, help screen, palette entry, keymap and snapshot tests | S1 S2 | full | app.py, keymap.py, help_screen.py, palette.py |
| T11 | Walking test (plain user greps every screen; hidden = missing) and `dev/demos/P1-UX.sh` | T01-T10 | full | tests, dev/demos/ |
| T12 | Tour re-shot (phase0, phase1, new section), narratives, PHASE-1-TOUR.md | T11 | lite | dev/tour/, docs/reports/ |

12 tickets plus 3 pieces is above the ten-ticket line, so round 1 asks for the plan check (`4 PLANCHK`) and
dispatches nothing. Hooks for trimming if the check asks: merge T07 into T09; merge T05 into T04.

## Order of work
1. Batch 1: S1 and S3 in parallel (disjoint: `tl_tui/display.py` vs `schema/`, `generated/`, `dev/seed`).
2. Batch 2: S2 (needs S1 interface and S3 type labels).
3. Batch 3: T01, T02, T03. Batch 4: T04, T06, T07. Batch 5: T05, T08, T10 (T08 and T10 touch different files).
   T09 can join any batch after S1 (no overlap with the others).
4. Batch 6: T11 once every screen ticket is merged. Batch 7: T12. DONE round: full gate, `gate-pg` on touched
   directories, security review scoped to S2 (route, confidentiality) and S3 (schema).
Checkpoints: C1 S1+S3 merged; C2 S2 merged; C3 T01-T10 merged; C4 T11-T12 merged and DONE.

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
- Hidden text is a moving target; the leak finder (S1) and the walking test (T11) are the guard.
- Escalate to the orchestrator if: a screen needs text that no schema label provides and S3 cannot add it; the
  admin-only toggle needs a role the client cannot report; Postgres parity fails on a detail view.

## Blocked / Decision
(filled during escalation)

## Plan check
(written by the plan-check agent: `4 PLANCHK docs/tickets/P1-UX/README.md | F1 ... | 30`)
