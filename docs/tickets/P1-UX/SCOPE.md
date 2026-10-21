# P1-UX: usability increment before Phase 2 (scope)

Owner request, 2026-10-21. The Phase 1 register screens (documents, tags, correspondence, RFIs, commercial notices)
are lists with a fixed summary panel. They never show property sets, cannot open the full record, and show
technical detail a mainstream AEC user should not see. This increment fixes that in the TUI. No new domain
behaviour, no change to commands, events or stored data.

## Objective (owner's words, numbered as the clauses of the demo)

1. **One record screen for every type.** Enter on any row of any list (record grid, document register, tag
   register, correspondence register, triage inbox, clocks, RFI log, commercial register, schedule and cost lists,
   review queue, integration registry where a row is a record) opens the full record view with the tabs Details,
   Properties, Links, History and Thread. Details shows the module's own fields (side table, ADR-0010) with labels.
   Properties shows the property sets that apply to the record's type (the Phase 0 psets tab), so documents, tags,
   RFIs and letters show their sets alike. Escape returns to the list on the same row.
2. **Plain language by default.** Every screen shows readable names and labels with units: type labels, not
   class names (`Control valve`, not `ControlValve` or `engineering.Tag`); code-list names, not codes (`Piping`,
   not `PIP`); domain labels, not internal keys (`Letter`, not `general/letter`); property labels, not keys
   (`Body material`, not `valve_data.body_material`); set labels (`Valve data`). Hidden by default: record and
   event ids (ULIDs), hashes and digests, schema package names and versions, effective-schema hashes, internal
   keys, rule markers like `required@Design/Inst` (replace with plain words such as "required at Design"),
   clock ids, calendar ids and versions, actor ids of services (`svc:...`; show the service's label), stream ids.
   Duplicated columns go (commercial State and Status).
3. **Technical details toggle.** One key toggles a "technical details" mode that shows what item 2 hides.
   It is off by default, per viewer, not remembered across sessions unless a setting says so, and offered only to
   admins (schema stewards are admins today). A plain user pressing the key gets a one-line refusal. Pick a key
   free in `keymap.py` and put it in the help screen and palette.
4. **Property sets for documents, RFIs and correspondence.** Add example sets to the fixture company standard
   (`schema/fixtures/co.acme.engineering@*`, as a new published version through the P1-I8 registry lifecycle if
   the fixtures are versioned that way, else additive in place): `document_data` for documents (e.g. originator,
   area, system, confidentiality note, native file format, review due), `rfi_data` for RFIs (e.g. location or
   grid line, drawing reference, trade, cost estimate with currency, schedule impact days), `correspondence_data`
   for correspondence (e.g. contract clause, reference number of the other party, response required by, delivery
   method). Labels and units on every property; at least one `required` and one with a code list per set. Additive
   only: no existing record becomes nonconformant in a way that breaks a demo or test; seed values in the demo
   ledgers so the screens have something to show. The owner approved this schema change on 2026-10-21 (record it
   in APPROVALS.md).
5. **Tour re-shot.** `dev/tour/phase0.py` and `dev/tour/phase1.py` regenerate every screenshot; the narratives
   that quote screen text are updated; a new short section in PHASE-1-TOUR.md shows the record screen opened from
   each register with its properties, and the technical-details toggle on and off. Deterministic: a second run
   changes no file.

## Constraints

- Display only. Labels come from the schema (LinkML titles, pset labels and units), standards code lists and
  domain definitions that already exist; add a label where one is missing rather than hard-coding text in a screen.
  One shared label/formatting helper in tl-tui used by every screen, not per-screen string tables.
- The API, MCP and CLI keep their current output (scripts depend on it). A CLI `--plain` flag is out of scope.
- Confidentiality is unchanged: the record screen shows only what the viewer may read; hidden looks exactly like
  missing (ADR-0016). Opening a record the viewer may not read from any list must behave like opening a missing one.
- TUI snapshots will change; regenerate them in the ticket that changes the screen, never as a separate sweep.
- Process v2 (`subagent-throughput-process` skill). Expected size 6–10 tickets, Haiku-first; the shared label
  helper and the record-screen routing for module types are the likely builder pieces.

## Demo `just demo P1-UX` (SQLite and Postgres)

1. From each register, Enter opens the record screen; its Properties tab lists the set for that type with labels.
2. As a plain user, no screen shows a ULID, hash, schema version, internal key or clock or calendar id (a test walks
   the screens and greps the rendered text); the toggle key is refused.
3. As an admin, the toggle shows those details and hides them again.
4. A restricted record opened from a list by a plain user reads exactly like a missing one.
