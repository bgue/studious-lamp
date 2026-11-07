# P2-WEB1-T21 — The other 13 logs show their panel as a Page (web look v2, part 2)

Status: ready (S7 merged)
Tier: haiku
Kind: ticket
Review: lite
Labels: web
Depends on: S7 (merged: `WebLog.panel_page`, `templates/page.html`).
Branch: `p2/web1-t21-panels-to-pages`   (from p2/web1)

## Goal
Spec `docs/build-spec/specs/web-look-v2.md`, item 1. In each page module below, the panel is built today as
`return present.plain_lines(<something>_page(...))` inside `panel_text`. Change each to `panel_page` returning that
Page object (the call inside `plain_lines`), and delete `panel_text` from the module (the base class derives it).
Keep every early return: where `panel_text` returned a fixed line for `row is None` or a missing record (for example
`["No stock on hand"]`), return `layout.Page(sections=(layout.Section("", note="No stock on hand"),))` — or keep a
`panel_text` override for exactly that case if that is simpler; the shown text must not change.

Modules: `pages/receipts.py`, `path.py`, `wbs.py`, `mto.py`, `movements.py`, `cwps.py`, `cwas.py`, `packages.py`,
`correspondence.py`, `items.py`, `stock.py`, `locations.py` (and any other `pages/*.py` still calling `plain_lines`;
`grep -rn plain_lines packages/tl-web/src/tl_web/pages` must print nothing at the end).

## Steps
1. Convert one module, run its test file, fix the assertions that read the `<pre>` text so they read the same facts
   from the HTML (the S7 report shows how), repeat.
2. Re-take the screenshots the test files write (`-k screenshot`), Read two of them (stock, receipts) and say in the
   report what the panel shows.

## Allowed paths
- `packages/tl-web/src/tl_web/pages/*.py` except `rfis.py`
- `packages/tl-web/tests/**`
- `docs/reports/P2-WEB1/T21.md` (create)

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-web/tests | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
