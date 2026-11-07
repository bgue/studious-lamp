# P2-WEB1-T20 — Demo: sign in and open the 11 twin pages

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: demo
Depends on: T08 (merged), all twins (merged)
Branch: `p2/web1-t20-demo-twins`   (from p2/web1)

## Goal
`dev/demos/P2-WEB1.sh` gets clauses 6 and 7, each ending `PASS clause n`, on sqlite and postgres.

## Context (read these, nothing else)
- `dev/demos/P2-WEB1.sh` (the helpers `fetch`, `has`, `lacks`, `sign_in`; run_backend's tail)
- `packages/tl-web/src/tl_web/log.py` (region ids in the template: the same eight ids as REGION_IDS)
- `packages/tl-web/tests/test_web_demo_clauses.py` (how the demo clauses are pinned; keep it green)
- `docs/reports/P2-WEB1/T17.md` (what the materials seed holds, for expected words)
may explore: `tl --help` groups for awp and materials, only to find seeding commands that exist

## Allowed paths
- `dev/demos/P2-WEB1.sh`
- `packages/tl-web/tests/test_web_demo_clauses.py` (only if it counts clauses or lines)
- `docs/reports/P2-WEB1/T20.md` (create)

## Steps
1. Seed what the CLI can seed through the existing `tl` commands (CWP/CWA/WBS/packages/materials) as the
   admin, after the RFI seed. The test fakes (T17) cannot run in a real server; do not import them. A page
   with no CLI seed is opened on an empty ledger and the clause expects the empty-state words instead.
2. Clause 6 (M3): amy signs in; for each of cwps, cwas, wbs, packages, path open `/web/p/P123/<slug>`:
   200, the eight REGION_IDS in order. Where seeded, one row text appears.
3. Clause 7 (M4): same for stock, movements, receipts, mto, items, locations. Also: a `?mode=technical`
   open of locations still 200; an unknown project slug page answers the generic 404 page.
4. Update the header comment (clauses 6, 7). Do not change clauses 1-5.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest packages/tl-web/tests/test_web_demo_clauses.py -q
just demo P2-WEB1 | tail -12
```
Expected: the demo ends with PASS for clauses 1 to 7 on both backends (postgres up: `just dev up`).

## Report requirements
Standard haiku report <= 60 lines; list which of the 11 pages were seeded and which ran empty.

## Escalation triggers
- A page 500s on the real server: stop, report the URL and the last 5 log lines (a fix ticket follows).
- A seed command needs a schema or access change: stop.
