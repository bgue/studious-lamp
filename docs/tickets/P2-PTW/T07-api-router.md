# P2-PTW-T07 - API read router of the permits module (permit routes)

Status: ready (written r4; base `p2/ip-r3`; PTW-S2 and T01 merged; the isolation and gas-test routes wait for T02)
Tier: haiku
Kind: ticket
Review: full
Labels: api, permits, confidentiality
Depends on: P2-PTW-S2 (hook `tl_mod_permits.routes:router`), P2-PTW-T01 (views), merged
Branch: `p2/ptw-t07-api-router`
Worktree: `/home/user/wt/ptw/t07` (from `p2/ip-r3`)

## Goal
`tl_mod_permits/routes.py` holds four GET routes of the design section 8 on the module's `router`: the register, the board, the export and one permit. The three routes of isolations and gas tests (`/permits/isolations`, `/permits/isolations/{key}`, `/permits/{key}/gas-tests`) are PTW-T07b after PTW-T02; none is written here.

## Rules
- Pattern: `tl_api/routes/punch.py` (guard `document.read`, `require_word` for `permits.view` on `project:P` with `holder_for_principal`, `ctx.backend(True)`, `current_viewer()`), imports of `tl_api.*` are allowed in the module package (no dependency is added).
- Routes (query `project` required), declared in this order so fixed paths win: `GET /permits/board?project=P[&area=A]` (`permit_board`), `GET /permits/export?project=P&format=csv|jsonl[&state, type, area, holder]` (`export_rows(permit_list(...).rows, fmt)`; `text/csv` or `application/x-ndjson`), `GET /permits?project=P[&state, type, area, holder, limit, offset]` (`permit_list`, `limit` 1..`MAX_LIMIT`), `GET /permits/{key}?project=P` (`permit_detail`).
- `now = tl_core.util.utcnow()` read once per request and passed to the views.
- A missing, hidden or other-project key is 404 `record_not_found` with the text `no permit` (key not echoed); a bad `state` is 422.
- No SQL; no write. The JSON carries the view fields as they are (`id` included, as the punch routes do); no 404 or error body names an id or key.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/punch.py` (whole), `packages/tl-modules/permits/src/tl_mod_permits/routes.py`, `views.py` (dataclasses and signatures only)
- `packages/tl-api/tests/test_api_punch.py` (1-140), `packages/tl-api/tests/test_module_hooks_api.py` (1-60), `packages/tl-modules/permits/tests/permit_world.py`

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/routes.py` (edit)
- `packages/tl-api/tests/test_api_permits.py` (create)
- `packages/tl-api/tests/expected/route_order.txt`, `docs/reference/openapi.json`, `docs/reference/openapi.baseline.json` as the four routes require (regenerate with the repo command; list in the report)
- `docs/reports/P2-PTW/T07.md` (create)

## Tests to add (`test_api_permits.py`; ledger from `permit_world.World`, readers as `test_api_punch.py`)
1. Five readers on every route: the reader who cannot see a restricted-for-record permit gets no row, no count in `total` or the board counts, and the same status and body as an unknown key on the detail route.
2. A person without `permits.view` gets 403 `forbidden` before any read.
3. A Lapsed permit shows `Lapsed` on all four routes and is first on the board; `export` rows equal `list` rows (csv and jsonl); `/permits/board` and `/permits/export` are not captured by `{key}`.
4. Bad `state`, `format` or `limit` is 422.
5. The four routes are in the route-order pin and OpenAPI; nothing else moved.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-api/tests/test_api_permits.py
uv run ruff check packages/tl-modules/permits packages/tl-api/tests/test_api_permits.py
uv run pyright packages/tl-modules/permits packages/tl-api/tests/test_api_permits.py
just gate packages/tl-api/tests/test_api_permits.py
just gate packages/tl-api/tests/test_module_hooks_api.py
```
Expected: clean on those paths; `gate: PASS` on each line. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
A view leaks a row or a count to a reader who cannot see the for-record (stop: a finding); the route needs a change to `tl_api/*`.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins and regenerated files outside Allowed paths. Commit subjects `P2-PTW-T07: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
