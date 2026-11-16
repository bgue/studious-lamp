# P2-INSP-T06 - API read routes for inspections and checklists

Status: ready (written r4; base `p2/ip-r3`; INSP-S2 and T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: api, quality, confidentiality
Depends on: P2-INSP-S2 (hook list), P2-INSP-T01 (views), merged
Branch: `p2/insp-t06-api-routes`
Worktree: `/home/user/wt/insp/t06` (from `p2/ip-r3`)

## Goal
`tl_api/routes/insp.py` holds the five GET routes of the design section 7 on a `router` the quality module names in `read_routers`. Thin: one call into `insp_views` per route under `current_viewer()`; a hidden or unknown key is one 404 body.

## Rules
- Pattern: `tl_api/routes/punch.py` whole (`_view_reader`: `guard("document.read")` then `require_word` for `quality.view` on `project:P`; `ctx.backend(True)`; `current_viewer()`; the 404 text). Same dependency, same `Reader` alias.
- Routes (project as the query parameter `project`, required): `GET /quality/inspections` (filters `state`, `point`, `area`, `inspector`, `subject`, `for`, `limit` 1..`MAX_LIMIT`), `GET /quality/inspections/export?format=csv|jsonl` (declared BEFORE the `{key}` route; same filters), `GET /quality/inspections/{key}`, `GET /quality/checklists` (`state`, `discipline`, `limit`), `GET /quality/checklists/{key}`. Responses are the view dataclasses; `export` is `text/csv` or `application/x-ndjson`.
- 404 `record_not_found` text `no inspection` / `no checklist` for missing, hidden and other-project keys alike (the key is not echoed); a bad state or point is 422 (the views raise `ValueError`: map it as `punch.py` maps its own).
- Hook: append `"tl_api.routes.insp:router"` to `read_routers` in `tl_mod_quality/module.py` (the tuple holds the punch router; append only).
- No SQL; no write; no import of `tl_cli`, `tl_mcp`.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/punch.py` (whole), `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (signatures, `MAX_LIMIT`), `module.py` (156-180)
- `packages/tl-api/tests/test_api_punch.py` (1-140: Harness, readers), `packages/tl-api/tests/test_module_hooks_api.py` (1-60: the route-order pin), `packages/tl-modules/quality/tests/insp_world.py`

## Allowed paths
- `packages/tl-api/src/tl_api/routes/insp.py` (create)
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` (the one `read_routers` line)
- `packages/tl-api/tests/test_api_insp.py` (create)
- `packages/tl-api/tests/expected/route_order.txt`, `docs/reference/openapi.json`, `docs/reference/openapi.baseline.json` as the five routes require (regenerate with the repo command; list in the report)
- `docs/reports/P2-INSP/T06.md` (create)

## Tests to add (`test_api_insp.py`; ledger from `InspWorld`, readers as `test_api_punch.py`)
1. Five readers (no clearance, cleared, restricted subject, company admin, agent token) on every route: the reader who cannot see the subject gets no row, no count in `total`, and for a key the same status and body as an unknown key; the checklist routes answer all readers who hold the word.
2. A person without `quality.view` gets 403 `forbidden` before any read.
3. List filters and `total`; export rows equal list rows (csv and jsonl); `export` is not captured by `{key}`.
4. Bad `state` or `point` is 422; `limit` above the maximum is 422.
5. The five routes are in the route-order pin and OpenAPI; nothing else moved.

## Acceptance
```
uv run ruff format --check packages/tl-api/src/tl_api/routes/insp.py packages/tl-api/tests/test_api_insp.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run ruff check packages/tl-api/src/tl_api/routes/insp.py packages/tl-api/tests/test_api_insp.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run pyright packages/tl-api/src/tl_api/routes/insp.py packages/tl-api/tests/test_api_insp.py packages/tl-modules/quality/src/tl_mod_quality/module.py
just gate packages/tl-api/tests/test_api_insp.py
just gate packages/tl-api/tests/test_module_hooks_api.py
```
Expected: clean on those paths; `gate: PASS` on each line. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
A view leaks a count or a key to a reader who cannot see the subject (stop: that is a finding); the route needs a `tl_api` change beyond the new file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins and regenerated files outside Allowed paths. Commit subjects `P2-INSP-T06: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
