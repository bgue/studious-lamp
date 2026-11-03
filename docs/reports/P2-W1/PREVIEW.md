# P2-W1-PREVIEW: wave-1 screenshots

Branch `p2/w1-preview` (main + p2/i1 + p2/i3 + p2/web1 merged). No product code changed.

## What it is
`dev/tour/wave1.py` (`just tour wave1`, run every half hour by `dev/tour/refresh_preview.sh`) builds a
fresh SQLite ledger with the frozen clock and writes `docs/reports/tour/wave1/`:
- web-NN-*.png: the web client in Chromium through `dev/tour/wave1_web.mjs` (Playwright from Node),
  1440x900 plus one at 390x844. `tl serve` runs with TL_WEB on at a free loopback port; the browser
  signs in as amy (sending Origin) and is stopped afterwards.
- tui-NN-*.svg: the terminal client headless through tourkit.
- cli-NN-*.svg: `tl` transcripts.
- index.json: ordered `[{file, title, caption}]`, one plain sentence each.

## Run (one run, 140 s)
- web 15: sign-in, RFI log with panel, RFI record in seven tabs (Details, Properties, History, Links,
  Trace, Thread, Files), correspondence log, document log with page-1 image, PDF viewer, a refused
  action (409), the hidden record (404), RFI log at phone width.
- tui 5: CWP register at 170 and 100 columns, WBS tree, CWA register, a CWP record.
- cli 5: awp cwp ls/show, awp wbs tree/show, the three awp reports, path/cwa/package, load targets.

## Skipped, printed as "not built yet"
- tui-06..11 (StockScreen, MovementLogScreen, ReceiptLogScreen, ReceiptEntryScreen, ItemLogScreen,
  MtoLogScreen): no such screens on this tree (M4 is not merged).
- cli-06, cli-07 (tl materials / tl mat): `mat.py` exists in tl_cli but is not mounted in main.py.
- `tl awp rollup` / `tl awp worker`: `awp_run.py` exists but is not mounted, so the WBS rollups and
  the cost report show no hours in the shots. The script runs them as soon as they are mounted.
- Packages log: no such screen on this tree.
Each absent item is detected at run time; nothing needs editing when the branches advance.

## Fixes in this resume
`has_command` check for the rollup verbs; the CLI group lookup uses the Click command tree.
