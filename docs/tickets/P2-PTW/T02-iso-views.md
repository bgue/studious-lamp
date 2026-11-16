# P2-PTW-T02 - Isolation and gas test read views `iso_views.py`

Status: ready (written r5; base `p2/ip-r3`; PTW-S3 merged; provided test staged)
Tier: haiku
Kind: ticket
Review: full
Labels: permits, read, confidentiality
Depends on: P2-PTW-S3 (isolation and gas-test records, six commands), P2-PTW-T01 (`views.py` pattern), merged
Branch: `p2/ptw-t02-iso-views`
Worktree: `/home/user/wt/ptw/t02` (from `p2/ip-r3`)

## Goal
`tl_mod_permits/iso_views.py` answers the isolation register, one isolation, the gas tests of one permit and both exports, as frozen dataclasses over the S3 projections, with the viewer's class filter before `LIMIT` and before counting. Later tickets (CLI, routes, tools) only call it.

## Rules
- The contract is the provided test `docs/tickets/P2-PTW/provided/T02_test_iso_views.py`: copy it byte-identical to `packages/tl-modules/permits/tests/test_iso_views.py` (pre-linted: ruff format and check clean; do not edit it) and make it pass. Names, fields, orders, columns and the `viewer` default (`cf.LOWEST`, keyword-only) are read from it, not re-derived.
- Pattern: `views.py` of this package (T01): joins, `_joins(viewer)`, `LIMIT` after the filter, `total` from the same filtered source, `export_rows` shape (`ValueError("... csv or jsonl")` for another format). Read it for the filter helper; do not write a second one.
- Hidden rules (design section 9): an isolation is hidden when its own `point_record_id` is hidden from the viewer; a gas test is hidden through its permit (the permit's `for_record_id`); `depends` and `IsolationDetail.permits` count and name only the permits the viewer can read (one statement for all rows, no query per row); a permit key never appears for a viewer who cannot read it.
- No clock, no write, no SQL outside the module's projection tables; the S3 report lists the table and column names (`docs/reports/P2-PTW/S3.md`; read the projectors only for column names).
- Decimals: readings are `Decimal` in `GasRow`, empty cell in CSV, `null` in JSONL (the test pins both).

## Context (read these, nothing else)
- `docs/tickets/P2-PTW/provided/T02_test_iso_views.py` (whole), `docs/reports/P2-PTW/S3.md`
- `packages/tl-modules/permits/src/tl_mod_permits/views.py` (whole), `projectors/` (column names only), `guards.py` (`dependent_permits`, for the event-based link read: do not copy it, `depends` reads the link projection if S3 made one, else the same events the guard reads, one statement)
- `packages/tl-modules/permits/tests/permit_world.py`, `conftest.py`

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/iso_views.py` (create)
- `packages/tl-modules/permits/tests/test_iso_views.py` (create, the provided test)
- `docs/reports/P2-PTW/T02.md` (create)

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits
uv run ruff check packages/tl-modules/permits
uv run pyright packages/tl-modules/permits/src/tl_mod_permits/iso_views.py packages/tl-modules/permits/tests/test_iso_views.py
just gate packages/tl-modules/permits/tests/test_iso_views.py
just gate-pg packages/tl-modules/permits/tests/test_iso_views.py
```
Expected: clean; all provided tests pass on both adapters; `gate: PASS`. No `just check`, no whole-repo pyright.

## Escalation triggers
The provided test contradicts a stored field (stop: a finding for the supervisor; never edit the test); `depends` cannot be read without a query per row; a view would need a write or a clock.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; state `101` (test byte-identical). Commit subjects `P2-PTW-T02: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
