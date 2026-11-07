# Drawings and model panel: where a record appears on the sheets and in the 3D model

Status: design v0.1 (proposed). Owner brief: a collapsible panel on the right of the web client and an equivalent
side panel in the TUI, for any record type, that opens straight to the right sheet and region or the right model view.
Out of scope: the index itself (what finds tags on sheets, maps GUIDs, reads geolocation). This spec assumes an index
behind the contract in section 1. The core interface it adds is in `docs/adr/0023-drawings-model-locator.md`.
Builds on: web look v2 (`web-look-v2.md`), the log standard (`packages/tl-tui/README.md` "Log screens"), the PDF viewer
(`templates/viewer.html`, `static/pdfview.js`), M12 Models (`module-designs/models.md`), ADR-0016.

## 1. The contract the viewer consumes
One read route, `GET /records/{record_id}/locations`, served by `tl_api`, called by the web, the TUI (through
`ClientInterface.locations(...)`) and, later, an MCP read tool. The route reads the record's own tag and identifiers
and adds any the caller passes. Core Protocol `Locator` (ADR-0023) sits behind it; the route owns filtering and paging.

**Request** (query string; the record id is the path)
| Field | Meaning |
|---|---|
| `tag` | Tag id. Default: the record's own tag, if it has one |
| `ident` (repeatable) | `scheme:value` for other identifiers: `guid:` (IFC GlobalId), `line:`, `iso:`, `spool:`, `weld:`. Open set, lower case |
| `bounds` and `crs` | `minx,miny,maxx,maxy` for a located record; `crs` is `site` (default) or `EPSG:nnnn` |
| `kind` (repeatable) | `drawing` or `model`; default both |
| `limit`, `cursor` | 1 to 50 (default 20); opaque cursor from the last answer |

**Answer** `{record_id, index_as_of, hits[], next_cursor}`. No total, no count of any kind.
Hits are ordered by confidence (high first), then drawings before models, current revision before superseded, then
`hit_id`, so one request always gives one order. Fields every hit has:
| Field | Meaning |
|---|---|
| `hit_id` | Opaque, stable for the same index state; used by the preview route |
| `kind` | `drawing` or `model` |
| `rank` | 1-based position in the whole ranked list |
| `confidence` | 0 to 1, two decimals |
| `matched_on` | `tag`, `guid`, `line`, `iso`, `bounds` ... (what found it) |
| `label` | Plain text, at most 120 characters, e.g. `P&ID 4701 sheet 2 rev C: V-1027` |

Drawing hit adds: `document_id`, `document_number`, `revision`, `is_current`, `sheet` (label), `page` (1-based),
`page_size {w, h}` in PDF points, and `region {x0, y0, x1, y1}` as fractions of the page (0 to 1, origin top left, so
it survives any zoom or render size).
Model hit adds: `model_id` (the model document), `model_number`, `version` (revision), and `view`:
`camera {type: perspective|orthographic, position[3], target[3], up[3], fov_deg or scale}`, `section_box {min[3], max[3]}`
or null, `selection` (up to 200 element GUIDs; `selection_truncated` when cut), `crs`.
Both kinds carry `open {kind: web|workspace|external|none, href}`, built by the server (section 2), never by the index.
Text from the index is untrusted: shown as text, never as HTML, control characters stripped in the TUI.

**Errors** (the API's usual error body)
| Status, code | When |
|---|---|
| 404 `record_not_found` | Unknown record, or a record the viewer may not read (identical, ADR-0016) |
| 422 `bad_identifier`, `bad_bounds` | Malformed `ident` or `bounds` |
| 400 `bad_cursor` | Cursor not ours, or the index changed since; the panel starts again from the first page |
| 503 `locator_unavailable` | The index cannot answer; carries `retry_after`. Never says why |
| 403 | Route not allowed for this principal (authorization is closed until allowed) |
A hit on a hidden document or model is never an error and never a gap: it is not there.

**Fake for development and tests**
- Contract, dataclasses and the fake live in `tl_core/locators/` (`contract.py` frozen like the integration contract,
  `fake.py`, `registry.py`); the entry-point group is `throughline.locators`, the fake is registered as `fake`.
- Data is `schema/fixtures/locators/demo.yaml`: for the demo project's tags (`V-1027`, `T-101`, the `PID-470x` sheets)
  a fixed list of drawing hits (document number, revision, page, region) and model hits (model number, version, a camera,
  a section box, GUIDs). Hits name documents by number; the fake resolves them to ids at call time, so a document the
  viewer cannot see drops out the way a real index result would. The fixture includes a hit on a restricted document
  and a superseded revision on purpose. An unknown tag answers an empty list. No clock, no randomness, no network.
- Selected by `TL_LOCATOR` (`none` default, `fake`, or an entry-point name). With `none` the panel is not offered at all
  (the toggle is absent, which says only how the server is set up, not what exists).

## 2. Panel behaviour
| State | What the person sees |
|---|---|
| Collapsed | A 40 px rail on the right edge: an icon and the label "Drawings and model" as a tooltip. No request is made, no badge, no count |
| Expanded, loading | Header, a one-line "Looking up locations" note, the list area kept at its height |
| Hit list | One row per hit: kind icon (sheet or cube), label, confidence as a word (High 0.8+, Medium 0.5+, Low), dim `matched on tag`; superseded revisions dimmed with "superseded". "Show more" fetches the next page |
| Preview | The selected hit. Drawing: a cropped picture of the region (360 px wide, highlight box drawn) and **Open sheet**. Model: the view in words (model, version, "12 elements selected, section box on") and **Open in model**. No picture of a model until P3-Q13 says snapshots are built |
| Empty | "No drawing or model locations for this record." One text, always the same (section 5) |
| Error | "Locations are not available right now." with a Retry button; the rest of the page is unaffected |
The first hit is selected on open, so one click or Enter on **Open** goes to the best place.

**Opening a drawing.** The server builds `open.href` = `/web/p/{project}/documents/{document_id}/revisions/{revision}/view?page=2&box=x0,y0,x1,y1`.
A new thin route resolves the revision to its PDF rendition, applies the viewer filter (hidden = the same not-found
page as a missing file) and renders the existing `viewer.html`, adding `data-page` and `data-box`. `pdfview.js` then
scrolls to the page, draws an overlay `div.pdf-hit` (outline `--accent`, fill `--accent-weak`, set through the CSSOM so the
CSP stays free of inline style) over the box, and zooms so the box takes about 40% of the view within the existing
0.5 to 3 limits. A "Show whole sheet" button removes the overlay. Opens in a new tab so the log keeps its place.
**Opening a model.** `open.href` comes from configuration, never from index text:
| `open.kind` | When | Href |
|---|---|---|
| `workspace` | The model workspace exists (Phase 3 I7) | `/web/p/{project}/models/{model_id}?v={version}&view={view}` |
| `external` | `TL_MODEL_VIEWER_URL` is set (template with `{model}`, `{version}`, `{view}`; http or https only) | The filled template |
| `none` | Neither | No link; the preview still shows the view in words and the button is disabled with a reason |
`{view}` is the base64url JSON of the view, at most 2 KB (selection cut to 50 GUIDs when larger).
**Preview picture.** `GET /records/{record_id}/locations/{hit_id}/preview.png` renders the crop with the bounded
pypdfium2 worker already used for page 1 (`preview.render`: size limits, kill timer, no network), cached by content hash.
It checks visibility again at request time; an unknown, stale or hidden `hit_id` answers the same 404.

## 3. Following the selected record
**Web, log.** Each row already has `hx-get` to `/web/p/{project}/{log}/panel/{number}` which swaps `#log-panel` and
sends the actions bar, crumb and status out of band. The partial now also sends `#loc-panel` out of band. When the
rail is collapsed (cookie `tl_loc=0`) that is just the rail. When expanded it is a skeleton with
`hx-get="/web/p/{project}/records/{id}/locations/panel" hx-trigger="load delay:150ms" hx-sync="this:replace"`: the index
call is off the row's critical path, a quick run of Down keys makes one request, and a stale answer is cancelled.
Expanding or collapsing sets the cookie (a per-viewer convenience) and fetches or clears the panel.
**Web, record screen.** The same `locations_panel.html` sits right of the tabs, keyed on the record, not the tab; it does
not reload when the tab changes. **Layout:** from 1600 CSS px a third column of 360 px right of `#log-panel`; from 1280
to 1599 the expanded panel is a drawer over the right edge (it covers the record panel, Esc closes it); below 1280 it
sits under the record panel like the record panel sits under the list. **Key:** `L` toggles (the ticket checks it
against `OWN_KEYS` and `ACTION_UI`).
**TUI, log.** `LocationsPane` holds `selected_key: reactive[str | None]`. `LogScreen` already finishes a row change in
`_finish_row`; a new optional hook calls `self.locations_pane.follow(record_id)` there. `follow` sets the reactive, waits
200 ms (a run of keys makes one read), reads `ClientInterface.locations` in a worker thread and drops an answer whose
generation is old (the same pattern as `_load` and `_fetch_actions`). **TUI, record screen:** a tab `Locations`
(key `7`, present only when a locator is configured) loads when first shown, like Properties and Trace.

## 4. TUI
| Part | Behaviour |
|---|---|
| Toggle and layout | `L`. From 200 columns a 44-column pane right of the record panel; below that `L` pushes `LocationsScreen` (a modal, list and preview stacked, Esc back). The 160-column rule for the record panel is unchanged |
| List | One line per hit, `tui-layout` rules: `▣ P&ID 4701 sheet 2 rev C  High`, cube for a model; empty value `—`; a superseded revision says `superseded` |
| Open | Enter or `o`. Drawing and model hits open the server-built `open.href` in the system browser through `preview.viewer` (an argument list, never a shell). The web base is `TL_WEB_URL`; without it a drawing hit falls back to fetching the rendition into `PrivateTemp` and opening the PDF with the page number in the status line (viewers differ on page arguments) |
| Preview | Drawing hits only. The cropped picture from the preview route, drawn through the file-preview path: the optional extra `tl-tui[images]` (`textual-image`, to be licence-checked in its ticket) for kitty, iTerm2 or sixel when `image_protocol(env) != "none"`; otherwise the half-block picture (`rich-pixels`, already a dependency) where there is colour; otherwise text: `Sheet 2 of PID-4701 rev C, region 41% to 47% across, 22% to 28% down`. `TL_IMAGES=off` (tests) always gives the text |
| Status | Empty and error texts as in section 2; a refusal goes to the status line as `! text` |
No logic in the TUI: it calls `ClientInterface.locations` and shows what comes back.

## 5. Confidentiality (ADR-0016)
1. The route calls `require_visible` on `record_id` first: hidden or missing is `record_not_found`.
2. The `Locator` receives the viewer (so a real index can push the filter down), but the route never relies on it: every
   raw hit is checked, by document id or model id, against the viewer's document filter in one batch per page, and a
   hit on a hidden or unknown document is dropped. A model follows its document's class (M12).
3. The route pulls raw pages until it has `limit` visible hits or the index is empty, looking one hit ahead, and sets
   `next_cursor` only when a further visible hit exists. A first page can be short with a cursor when the work bound
   (10 raw pages) is reached; the client fetches on. Nothing exposes a total, a "hidden" count, a page size that depends on
   hidden hits, or a different empty text. Nothing is shown on the collapsed rail.
4. Preview and open routes check visibility at request time. Open hrefs name documents only after the filter.
5. The empty state is byte-identical for "nothing indexed" and "everything hidden". Tests: the walking test of
   `tl_api` classifies the new routes and runs them as the five readers (user, controller, agent, admin, system); a twin
   test asks about a record with no hits and one whose every hit is hidden and compares the whole response; the fake
   fixture's restricted hit must never reach a user. Known limit: response time grows with the number of hidden hits
   (up to the work bound); recorded in the ticket's report, not hidden.

## 6. Phasing, and effort
H = Haiku ticket (one file area, at most 150 changed lines, one gate); S = Sonnet builder piece (spans packages or holds
a security or layout decision).
| Phase | Item | Size |
|---|---|---|
| Phase 2, any free slot (no web dependency) | ADR-0023 accepted by orchestrator; `tl_core/locators` contract and registry | 1 S |
| | `FakeLocator` and `demo.yaml`, unit tests | 1 H |
| | Route, batch visibility filter, paging, errors, walking and twin tests; `ClientInterface.locations` (HTTP and embedded) | 1 S |
| | Preview route and `render_region` in the bounded worker | 1 S |
| | TUI `LocationsPane`, row hook, `LocationsScreen`, tab, open (text and browser) | 1 S + 1 H (tests) |
| | TUI picture: half-block, optional `tl-tui[images]` protocols | 1 H |
| Web increment after Phase 2 waves 3 and 4 (working name P2-WEB3; owner confirms) | Drawing view route, `pdfview.js` page and box overlay | 2 H |
| | `locations_panel.html`, out-of-band swap in `panel.html`, cookie, `L` key, CSS, layouts | 1 S + 1 H (CSS and tests) |
| | Record screen placement; docs, runbook, demo script | 2 H |
| Phase 3 I6 and I7 (M12) | Real index of model objects (mapping gives GUIDs), model hits with camera and section box; workspace route makes `open.kind = workspace`; snapshot preview if P3-Q13 says build | in the M12 plan |
| Later, owner to place | Real drawing index (tags and region extraction from sheet text or markup) as an extractor on the ADR-0014 pipeline | to be sized |
Total before Phase 3: 4 S and 7 H, of which the TUI side is 2 S and 2 H and can land before any web work.

## 7. A second mode: the TUI inside the web page
Options: (a) xterm.js in the page, a WebSocket to a server process that runs `tl tui` in a pseudo-terminal for each
session; (b) Textual's own web serving (`textual serve`), which does the same with its bundled terminal page.
| Cost | Detail |
|---|---|
| Security | A process per signed-in person: a shell-shaped surface. Needs the web session mapped to an API session handed over by environment variable (never argument or URL), WebSocket origin and CSRF checks (cross-site WebSocket hijack), a command that cannot be replaced, resource limits (memory, CPU, idle timeout, a cap on sessions), no file or clipboard bridge, and terminal escape sequences from record text reaching a real terminal emulator |
| Policy | The CSP and "no external host" rules mean vendoring xterm.js; the viewer filter must hold for the embedded client exactly as for a local one (it does, through the API, but it is one more path to walk-test) |
| Maintenance | Two ways to do every screen on one page; Textual web mode is aimed at demos and moves between releases; terminal canvases defeat browser search, screen readers, text zoom, phone keyboards and the HTMX pages already built; images and PDFs would need sixel or kitty support in the emulator instead of the real viewer |
| Operations | About 100 MB or more and a Python process per person, sticky routing, reconnection and session timeouts to design |
**Recommendation: no.** The web client already has native pages for the same data, and this panel gives the web the
sheet viewer and the model link directly. A terminal-in-a-page adds a remote-shell-shaped attack surface and a second
UI to maintain without adding a capability. Revisit only if the owner wants a read-only demo mode, then as a separate
flag behind an admin setting, never in the default build.

## Open questions for the owner
1. Is the working name P2-WEB3 right for the web increment, and may the TUI panel and the contract land before it?
2. `TL_WEB_URL` for the TUI: is one web address per site acceptable, or should the server hand it out?
3. Where does the real drawing index land (Phase 3 beside I6, or Phase 4)?
4. Confidence words (High, Medium, Low): are 0.8 and 0.5 the right cut points once a real index exists?
