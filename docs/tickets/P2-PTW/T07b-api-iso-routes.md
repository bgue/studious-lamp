# P2-PTW-T07b - API routes of isolations and gas tests

Status: staged (written r5; base `p2/ip-r3` after PTW-T07 and PTW-T02 merge; routes of one permit set are in `routes.py`)
Tier: haiku
Kind: ticket
Review: full
Labels: api, permits, confidentiality
Depends on: P2-PTW-T07 (`routes.py` with the four permit routes), P2-PTW-T02 (`iso_views`), merged
Branch: `p2/ptw-t07b-api-iso-routes`
Worktree: `/home/user/wt/ptw/t07b` (from `p2/ip-r3`)

## Goal
Three GET routes of the design section 8 are added to the permits `router`: `/permits/isolations`, `/permits/isolations/{key}` and `/permits/{key}/gas-tests`. Thin: one `iso_views` call each under `current_viewer()`; a hidden or unknown key is one 404 body.

## Rules
- Edit `tl_mod_permits/routes.py` only, in the style of the T07 routes already there (same guard, `require_word` for `permits.view` on `project:P`, `ctx.backend(True)`, `current_viewer()`, query `project` required).
- Declaration order (fixed paths win over `{key}`): `GET /permits/isolations?project=P[&state, energy, limit]` (`isolation_list`; `limit` 1..the view's bound), `GET /permits/isolations/export?project=P&format=csv|jsonl[&state, energy]` declared BEFORE `/permits/isolations/{key}`, through `isolation_export_rows` (`text/csv` or `application/x-ndjson`), `GET /permits/isolations/{key}?project=P` (`isolation_detail`), and `GET /permits/{key}/gas-tests?project=P[&format=csv|jsonl]` (JSON list from `gas_tests_for`, or the export text through `gas_export_rows`). The two `/permits/isolations...` routes are declared BEFORE the T07 `GET /permits/{key}` (which would otherwise capture `/permits/isolations` as a key); `/permits/{key}/gas-tests` has a different shape and may follow it.
- The permit behind `/permits/{key}/gas-tests` is resolved with the permit detail view under the viewer: a hidden, unknown or other-project permit is 404 `record_not_found` text `no permit` (the same body as `/permits/{key}`); a visible permit with no tests is `[]` (200). A missing isolation is 404 text `no isolation` (key not echoed); a bad `state`/`energy`/`format`/`limit` is 422 (the views raise `ValueError`: map as T07 does).
- No SQL, no write, no import of `tl_cli`/`tl_mcp`. No body or error names an id or key of a hidden record. No new guard action; if one is needed, decide it in `packages/tl-api/tests/test_auth_review.py` (Allowed) and say so.

## Context (read these, nothing else)
- `packages/tl-modules/permits/src/tl_mod_permits/routes.py` (whole), `iso_views.py` (signatures), `views.py` (`permit_detail` signature)
- `packages/tl-api/tests/test_api_permits.py` (T07's harness; extend it), `packages/tl-api/tests/test_module_hooks_api.py` (1-60)

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/routes.py` (edit)
- `packages/tl-api/tests/test_api_permit_iso.py` (create; reuse the T07 harness by import or a copy of its fixture lines, do not edit `test_api_permits.py`)
- Pins: `packages/tl-api/tests/expected/route_order.txt`, `docs/reference/openapi.json` (regenerate with the repo command; `openapi.baseline.json` is a release step), `packages/tl-api/tests/test_auth_review.py` only if a guard action is added; list each in the report
- `docs/reports/P2-PTW/T07b.md` (create)

## Tests to add (`test_api_permit_iso.py`; ledger as the provided T02 test builds it, five readers as T07)
1. Five readers on all four paths (list, export, detail, gas-tests): the reader who cannot see the restricted point record gets no row, no count in `total`, and for the detail the same status and body as an unknown key; the hidden permit's gas tests read as `[]`/404 exactly as an unknown permit's (same body as `/permits/{key}`).
2. A person without `permits.view` gets 403 before any read; an agent token gets the closed 403 (no agent list names these routes).
3. `/permits/isolations` and `/permits/isolations/export` are not captured by a `{key}` route; export rows equal list rows (csv and jsonl); a visible permit with no gas test is 200 `[]`.
4. Bad `state`, `energy`, `format`, `limit` are 422.
5. The routes are in the route-order pin and OpenAPI; nothing else moved.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-api/tests/test_api_permit_iso.py
uv run ruff check packages/tl-modules/permits packages/tl-api/tests/test_api_permit_iso.py
uv run pyright packages/tl-modules/permits/src/tl_mod_permits/routes.py packages/tl-api/tests/test_api_permit_iso.py
just gate packages/tl-api/tests/test_api_permit_iso.py
just gate packages/tl-api/tests/test_api_permits.py
just gate packages/tl-api/tests/test_module_hooks_api.py
```
Expected: clean; `gate: PASS` on each line. No `just check`, no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
A view leaks a row, a count or a key to a reader who cannot see the record (a finding); a route needs a change to `tl_api/*`; the T07 routes need a change beyond reordering.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins and regenerated files. Commit subjects `P2-PTW-T07b: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
