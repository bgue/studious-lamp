# ADR-0023 — A locator interface maps a record to drawing regions and model views

Status: proposed (2026-11-07, for orchestrator review; touches confidentiality, so it is a human gate under §25.5)
Date: 2026-11-07
Deciders: repository owner (brief for the panel); orchestrator (acceptance)
Brief sections: §10.6 sketches 9 and 10, §23 (models), §9 M1 (documents), §8 (permissions)
Amends: nothing. Applies the ADR-0010 module seam and the ADR-0016 viewer. Spec: `docs/build-spec/specs/drawings-model-panel.md`.

## Context
The owner wants a side panel, in the web client and the TUI, that shows where any record appears on the drawings and in
the 3D model and opens at the right sheet region or model view. The thing that knows (an index of tags on sheets, a
GUID and line-number map, geolocation bounds) does not exist yet and will arrive in pieces: M12 maps model objects in
Phase 3, a drawing index later. The panel, the API and the tests must be built now against something fixed. The index
will also be the first place that returns pointers to documents on behalf of a record, so it is a new confidentiality
path: ADR-0016 says a new route that can carry record text needs a walking test as five kinds of reader.

## Decision
1. **A new core Protocol, `tl_core.locators.Locator`**, with one method:
   `locate(query: LocatorQuery, viewer: Viewer, *, limit: int, cursor: str | None) -> LocatorPage`.
   `LocatorQuery` holds the record id, tag, `idents` (scheme and value pairs), optional bounds and CRS, and the kinds
   wanted. `LocatorPage` holds ranked `DrawingHit` and `ModelHit` values (fields in the spec, section 1), `index_as_of`
   and the next cursor. The types are frozen in `contract.py`, like `tl_core.integration.contract`.
2. **Implementations are found by entry point, group `throughline.locators`** (as extractors and enrichers are). One is
   active, chosen by `TL_LOCATOR`; the default `none` answers no hits and the clients do not offer the panel.
   `fake` ships in `tl_core/locators/fake.py` with fixture data keyed on the demo project's tags, for development and tests.
3. **The route owns confidentiality, not the locator.** `GET /records/{id}/locations` checks the record is visible,
   passes the viewer to the locator (so a real index can push the filter down), then drops every hit whose document or
   model the viewer cannot read, in one batch per page. The answer has no total and no count; the empty text is the same
   for no hits and all hits hidden; a hidden record answers `record_not_found`. A locator that ignores the viewer is
   still safe.
4. **The index never builds URLs.** The server builds each hit's `open.href` from its own configuration (web viewer route,
   model workspace route, or `TL_MODEL_VIEWER_URL`), http or https only. Index text is shown as text.
5. **One client method**, `ClientInterface.locations(record_id, ...)`, over HTTP and the embedded client, so the TUI
   calls what the web and an agent would call. The route is new and denied until allowed (AGENTS.md); an MCP read tool
   is added only when someone allows it, and an agent sees `internal` documents only.
6. **Scope.** The index, its data and the model workspace are not decided here. M12 (Phase 3 I6, I7) and a later drawing
   index implement `Locator`; the contract does not change when they arrive, except by a new ADR.

## Consequences
- Contracts changed: `tl_core.locators` is new; `ClientInterface` gains `locations`; `tl_api` gains the route and a
  preview route; `tl_web` and `tl_tui` gain the panel. No schema change, no event, no table: the interface reads only.
- Confidentiality: two new walking-test entries (locations, preview), a twin test that compares the empty answers
  byte for byte, and a fixture hit on a restricted document that must never reach a user. Listed under `SECURITY_REVIEW`.
  Known limit: response time rises with the number of hidden hits, up to a work bound of 10 raw pages per request.
- Gates affected: the filter is a confidentiality filter (§25.5 human gate); the first S piece names a human approver.
- Cost: one more entry-point group to document (`docs/reference`), and a hit shape every real index must be able to fill:
  drawing regions as page fractions, a model view as camera, section box and GUIDs.

## Alternatives considered
- **Pull-through from the web only (no core interface).** Fastest, but the TUI would need its own copy, tests could not
  share a fake, and the filter would live in a page handler rather than a read path. Rejected.
- **Store hits as records or links.** Re-uses the ledger, but a record write per tag-on-sheet is thousands of events (the
  ADR-0022 argument), the data is derived and rebuildable, and links carry no region. Rejected.
- **Let the index filter by clearance and trust it.** One less loop, but a bug in an external index would leak a
  restricted sheet; ADR-0016 wants every read path filtered where the record data is read. Rejected, though the viewer is
  passed so the index may help.
- **A fixed HTTP index service, no Protocol.** Couples the build to one deployment shape and makes the fake a mock server.
  An entry point lets an HTTP client be one implementation.
- **Return a count so the rail can show a badge.** A count is a leak when hits are hidden. Rejected.
