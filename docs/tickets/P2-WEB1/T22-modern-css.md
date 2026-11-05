# P2-WEB1-T22 — The new stylesheet (web look v2, part 3)

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: web, css
Depends on: nothing. Runs beside S7 (S7 changes templates and Python, never `tl.css`).
Branch: `p2/web1-t22-modern-css`   (from p2/web1)

## Goal
Rewrite `packages/tl-web/src/tl_web/static/tl.css` to the spec `docs/build-spec/specs/web-look-v2.md`, sections
"Tokens" and "Components", exactly (token names and values as written). Keep every selector the templates use today
(`.tl-bar .tl-brand main .tl-log .tl-crumb .tl-filter .tl-body .tl-table .tl-flex .tl-drop .tl-panel .tl-panel-img
.tl-panel-text .tl-actions .tl-action .tl-keys .tl-muted .tl-status .tl-action-form .tl-form .tl-error #rec-tabs
.tl-rec-header .tl-history`) and add the new ones S7 and T21 emit (`.tl-page-id .tl-badge .tl-done .tl-waiting .tl-bad
.tl-neutral .tl-summary .tl-sec .tl-props .tl-mini .tl-mini-wrap .tl-line .tl-note .tl-btn .tl-primary kbd`). Keep the
two layout media queries (panel beside the list from 1280px; the `.tl-drop` rules) with their breakpoints. Style
`.tl-action` the same as `.tl-btn` (old markup until S7 merges). No `@import`, no `url()` to another host, no inline
style anywhere (CSP). `viewer.css` is not touched.

## Steps
1. Write the file: tokens on `:root`, the dark block, base (`body` background `--bg`, colour `--text`), then each
   component in the spec's order. Comments: one line per block.
2. Look at it: run the existing screenshot tests (`uv run pytest packages/tl-web/tests -k screenshot -q`), Read three
   PNGs from `/home/user/wt/<your worktree>/.accept/shots/` or wherever the tests write them (sign-in if any, RFI
   log, stock) and fix what looks wrong (overflow, contrast, a missing token). Say in the report what each shows.

## Allowed paths
- `packages/tl-web/src/tl_web/static/tl.css`
- `packages/tl-web/tests/**` only if a test pins a CSS string (say which)
- `docs/reports/P2-WEB1/T22.md` (create)

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-web/tests | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
