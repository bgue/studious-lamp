# P2-QR-T06 - API read router of the QR module

Status: ready (written r4; base `p2/ip-r3`; QR-S2 and T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: api, qr, confidentiality
Depends on: P2-QR-S2 (resolver, hook `tl_mod_qr.routes:router`), P2-QR-T01 (views), merged
Branch: `p2/qr-t06-api-router`
Worktree: `/home/user/wt/qr/t06` (from `p2/ip-r3`)

## Goal
`tl_mod_qr/routes.py` holds three GET routes on the module's `router` (the hook already includes it): the register of one record's codes, its export, and a JSON resolve. All read through the viewer's class filter; none writes; none ever returns a code or hash (the resolve route takes one in the path and returns the card).

## Rules
- Routes (one `Depends(guard("qr.read"))` first: `qr.read` is on no agent list, so an agent token gets the closed guard's 403 before any lookup; a signed-in person passes):
  - `GET /qr/codes?project=P&record=KEY` -> `list[CodeRow]` fields as JSON (`id`, `label_text`, `size`, `issued_by`, `issued_at`, `expires_on`, `state`, `revoked_at`, `replaced_by_id`). Order: `views.codes_for_record`.
  - `GET /qr/codes/export?project=P&record=KEY&format=csv|jsonl` -> `views.export_rows` as `text/csv` or `application/x-ndjson`; the rows equal the list route's.
  - `GET /qr/resolve/{code}` -> `ScanCard` as JSON from `resolve.resolve(conn, code, current_viewer())`; a miss of any kind is the one 404 `record_not_found` with the text `no such code`; header `Cache-Control: no-store` on every answer of this route.
- After the guard, `require_word` for `qr.view` on `project:P` (the pattern of `tl_api/routes/punch.py:_view_reader`, `holder_for_principal`) before any read, for the first two routes.
- The record KEY resolves to an id with `tl_core.services.queries.get_record` under `current_viewer()`; hidden, unknown and other-project keys give the same 404 body as each other (`no record <KEY>` is NOT echoed: use `no such record`).
- Reads open `ctx.backend(True)` and pass `viewer=current_viewer()`; never the views' LOWEST default.
- No `tl_mod_qr.cli`, `service` write path or command import; no new dependency (`fastapi` is declared).

## Context (read these, nothing else)
- `packages/tl-modules/qr/src/tl_mod_qr/routes.py` (the stub), `views.py`, `resolve.py` (signature only)
- `packages/tl-api/src/tl_api/routes/punch.py` lines 1-110 (guard, require_word, Reader, `ctx.backend(True)`, 404 text pattern)
- `packages/tl-api/tests/test_api_punch.py` lines 1-130 (Harness, five readers, session sign-in pattern), `packages/tl-api/tests/test_module_hooks_api.py` (the route-order pin, lines 1-60)
- `packages/tl-modules/qr/tests/qr_world.py`
may explore: `packages/tl-api/tests/harness.py`

## Allowed paths
- `packages/tl-modules/qr/src/tl_mod_qr/routes.py` (edit)
- `packages/tl-api/tests/test_api_qr.py` (create)
- `packages/tl-api/tests/expected/route_order.txt`, `docs/reference/openapi.json`, `docs/reference/openapi.baseline.json` only as the three new routes require (rule 12; regenerate openapi with the repo command, list it in the report), `packages/tl-api/tests/test_module_hooks_api.py` only if a count pin moves
- `docs/reports/P2-QR/T06.md` (create)

## Tests to add (`test_api_qr.py`; ledger from `qr_world`, readers as `test_api_punch.py`)
1. Five readers (no clearance, cleared, restricted subject, company admin, agent token) on each route: the agent gets 403 on all three before any lookup (assert no read ran: a statement counter or a monkeypatched view that raises); the reader who cannot see the record gets the same status and body as an unknown key, on the list and the export.
2. The list rows equal the export rows (csv and jsonl); no response body contains a code or code hash (grep the 16-character code and the stored hash).
3. Resolve: a live code gives the card JSON (banner, key, lines) with `Cache-Control: no-store`; unknown, revoked, expired, hidden record and a reader without the view word give byte-identical 404 bodies.
4. A person without `qr.view` on the project gets the 403 `forbidden` on list and export.
5. The three routes appear in the route-order pin and OpenAPI; nothing else moved.

## Acceptance
```
uv run ruff format --check packages/tl-modules/qr packages/tl-api/tests/test_api_qr.py
uv run ruff check packages/tl-modules/qr packages/tl-api/tests/test_api_qr.py
uv run pyright packages/tl-modules/qr packages/tl-api/tests/test_api_qr.py
just gate packages/tl-api/tests/test_api_qr.py
just gate packages/tl-api/tests/test_module_hooks_api.py
```
Two separate gate calls (the box OOMs on combined tl-api runs). Expected: clean, `gate: PASS` twice. No `just check`, no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
`guard("qr.read")` is not refused for agents (then name the closed action in the report and stop); the route needs a change to `tl_api/*`; a viewer-filter gap in `views.py`.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list the pins and regenerated files outside Allowed paths. Commit subjects `P2-QR-T06: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
