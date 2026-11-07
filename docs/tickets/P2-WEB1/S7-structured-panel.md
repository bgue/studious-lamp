# P2-WEB1-S7 — The panel renders the layout Page as HTML (web look v2, part 1)

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: web
Depends on: T19 (merged). Runs beside T22 (CSS only); T21 follows this piece.
Branch: `p2/web1-s7-structured-panel`   (from p2/web1)

## Goal
Spec: `docs/build-spec/specs/web-look-v2.md` sections "What changes" 1-3 (read it whole; it is short). The panel of every
log stops being terminal text in a `<pre>` and becomes HTML built from the `tl_tui.layout.Page` the log already makes.
This piece builds the mechanism and converts the RFI log (`pages/rfis.py`) as the pilot; T21 converts the other 13.

## Steps
1. `log.py`: add `WebLog.panel_page(self, row) -> layout.Page | None` (default `None`). The page context gets
   `panel_page` (the Page, or None) beside `panel` (lines). When `panel_page` is not None the panel shows the Page;
   otherwise it shows `panel` in `<pre class="tl-panel-text">` as today. `panel_text` stays (tests and the terminal
   twins read it): its default becomes `present.plain_lines(page)` when `panel_page` returns a Page, so a converted log
   implements only `panel_page`.
2. `templates/page.html`: one macro `render_page(page)` exactly as the spec, item 1 (identity, state badge with tone,
   summary, sections, grouped `dl.tl-props`, grouped `table.tl-mini` inside `div.tl-mini-wrap`, `p.tl-line`, `p.tl-note`).
   Tone: a small pure function `tone(style: str) -> str` in `present.py` (`green`→`done`, `yellow`→`waiting`,
   `red`→`bad`, else `neutral`), registered as a Jinja global or filter. Autoescape stays on; no `|safe`.
3. `panel_body.html`: the image (unchanged), then `render_page(panel_page)` or the `<pre>`.
4. State column badge (spec item 2): in the list, a cell whose column name is `State` renders
   `<span class="tl-badge tl-<tone>">text</span>` with the tone of `layout.state_style(text)`.
5. Actions (spec item 3): `actions.html` buttons read `{{ a.label }} <kbd>{{ a.key_label }}</kbd>` with class `tl-btn`;
   Open record is `<a class="tl-btn tl-primary" id="log-open" ...>Open <kbd>Enter</kbd></a>`. `tl.js` key handling
   must keep working (it reads `data-key`, not the text; check).
6. `pages/rfis.py`: implement `panel_page` (the `rfi_page(...)` it already builds) and drop its `panel_text`.
7. Tests: update the tl-web tests that pin the panel's `<pre>` text, the bracketed action labels or the State cell
   markup, so they assert the same facts on the new HTML (text content of the elements, not exact whitespace).
   Add `packages/tl-web/tests/test_web_page_render.py`: a Page with identity, state (each tone), summary, a section
   of props (one empty value → `—`), a section of two table rows plus a styled Cell, a str line, an empty section with
   a note → the expected elements and classes; escaping of `<script>` in a value.

## Allowed paths
- `packages/tl-web/src/tl_web/log.py`, `present.py`, `pages/rfis.py`
- `packages/tl-web/src/tl_web/templates/page.html` (create), `panel_body.html`, `log.html`, `actions.html`
- `packages/tl-web/src/tl_web/static/tl.js` (only if key handling read the bracketed label)
- `packages/tl-web/tests/**`
- `docs/reports/P2-WEB1/S7.md` (create)
No CSS change (T22 owns `tl.css`). No change outside `packages/tl-web` except the report.

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-web/tests | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
- Screenshot: run the RFI log screenshot test (`-k screenshot` in its test file, or the T15 test) and Read the PNG; say in
  the report what the panel shows now.
