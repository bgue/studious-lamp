# P2-I3-T04a — Materials API read routes

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: api
Depends on: S3 (merged)
Branch: `p2/i3-t04a-api-reads`

## Goal
Eight thin GET routes over the materials views, in `tl_api/routes/materials.py`, included in the app. Writes already exist (`POST /commands/<Name>` from
`MATERIALS_COMMANDS`, S3); the `/reports/{name}` route is T05's, not here.

## Brief references (pasted)
> API GET: `/projects/{p}/materials/stock`, `/lots/{key:path}`, `/movements`, `/receipts`, `/receipts/{number}`, `/locations`, `/po-lines`, `/mto-lines`;
> `/companies/items`. Every GET joins the confidentiality walking test (five readers).
> The API sets the viewer from the principal for the whole request; the views filter by it (ADR-0016). The route passes no `viewer`. A hidden record answers
> as one that never existed (404, same text). Bounds: every list has a `limit` query parameter, `ge=1, le=views.MAX_VIEW_ROWS` (`limits.MAX_VIEW_ROWS`, 1000).

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views (each takes conn first; scope is "project:<p>" except items, which takes project=None for the company library)
stock(conn, scope, *, lot=None, location=None, item=None, heat=None, subtree=False, limit=...) -> list[StockRowView]
lot_detail(conn, scope, key, *) -> LotDetailView               # raises LotNotFoundError
movements(conn, scope, *, lot=None, since=None, until=None, kind=None, limit=...) -> list[MovementView]
receipts(conn, scope, *, open_only=False, missing_mtr=False, limit=...) -> list[ReceiptView]
receipt_detail(conn, scope, number, *) -> ReceiptDetailView    # raises ReceiptNotFoundError
locations_tree(conn, scope, *, limit=...) -> list[LocationView]
po_lines(conn, scope, q=None, *, limit=...) -> list[PoLineView]
mto_lines(conn, scope, *, work_package=None, short_only=False, limit=...) -> list[MtoLineView]
items(conn, *, project=None, limit=...) -> list[ItemView]
```
Routes (path, operation_id, query parameters): `/projects/{project}/materials/stock` `list_materials_stock` (lot, location, item, heat, subtree, limit);
`/projects/{project}/materials/lots/{key:path}` `get_materials_lot`; `/projects/{project}/materials/movements` `list_materials_movements` (lot, since, until, kind, limit);
`/projects/{project}/materials/receipts` `list_materials_receipts` (open_only, missing_mtr, limit); `/projects/{project}/materials/receipts/{number}`
`get_materials_receipt`; `/projects/{project}/materials/locations` `list_materials_locations` (limit); `/projects/{project}/materials/po-lines`
`list_materials_po_lines` (q max 200, limit); `/projects/{project}/materials/mto-lines` `list_materials_mto_lines` (work_package max 64, short_only, limit);
`/companies/materials/items` `list_materials_items` (project optional, limit). Register `/lots/...` and `/receipts/{number}` after the list routes.
Guard: `Reader = Annotated[str, Depends(guard("document.read"))]` as `routes/cost.py` does (the fine word `materials.view` is the read role; agents read). `LotNotFoundError`
and `ReceiptNotFoundError` already have error-table rows (404); do not catch them. Query strings that name a lot, location, item or heat are `Query(max_length=200)`.
**Bound note (S3 review F3-info):** `views.mto_lines` with `short_only` scans every line of the scope before it stops at `limit`; do not change `views.py`, the route's
`limit` cap keeps the output bounded; write the scan as a one-line `# note` in the report, not in code.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/cost.py` (the pattern: `Ctx`, `Reader`, `ctx.backend(True)`, `uow.conn()`)
- `packages/tl-modules/materials/src/tl_mod_materials/views.py` (signatures and view models, read only)
- `packages/tl-api/src/tl_api/app.py` (the router list near `cost`, `schemareg`)
- `packages/tl-api/tests/test_confidentiality_walk.py` (`MIN_ROUTES`, `candidates`; read how the walk finds GET routes)
- `dev/accept/P2-I3/S3.py` (`--keep` writes the seed ledger `.accept/p2-i3.db`: 50 items, receipt `P123-RCPT-0001`, MTO `ISO-1234@A/MTO`)
may explore: `packages/tl-api/tests/harness.py` (a TestClient on a temp ledger)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/materials.py` (create)
- `packages/tl-api/src/tl_api/app.py` (one import name and one entry in the router tuple; nothing else)
- `docs/reference/openapi.json` (regenerated with `uv run python -m tl_api.openapi`)
- `packages/tl-api/tests/test_confidentiality_walk.py` (`MIN_ROUTES` raised by the number of new GET routes, and a `candidates` entry only if a path parameter name is new)
- `dev/accept/P2-I3/T04a.py` (create), `docs/reports/P2-I3/T04a.md` (create)
Not here: `views.py`, `commands.py`, `errors.py`, any other route file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T04a.py
just gate packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_error_table.py packages/tl-api/tests/test_auth_review.py
```
`T04a.py` (you write it; the harness pattern of `packages/tl-api/tests/harness.py` on a copy of `.accept/p2-i3.db` or on a ledger built with `S3.py`'s `World`; exit 0, one
`PASS <check>` per line): all nine routes answer 200 for a reader and appear in `app.openapi()` with the operation ids above; stock lists the seeded lots and `heat=H-7781`
narrows them; the lot detail of a seeded lot answers, an unknown key answers 404 `materials_lot_not_found`; `receipts/P123-RCPT-0001` answers with two lines, an unknown number
404 `materials_receipt_not_found`; `locations` returns 9; `po-lines` 15; `mto-lines?work_package=P123-CWP-PIP-0001` returns 3; `/companies/materials/items` 50; `limit=0` and
`limit=1001` answer 422; no token answers 401; an `agent:` token reads (200). Confidentiality here is plumbing only: no route passes a viewer (assert with a grep of the file in
the script); the five-reader walk over classified materials records is T11's, recorded in the report.

## Tests to add
None (T11: `test_api_materials.py` and the walk seed for materials records).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, the F3-info note above. Commit subjects `P2-I3-T04a: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a view signature differs from the list above, if the guard action needs an entry outside `tl_api` (an unknown action), or if the walk test
  fails on a materials route for a reason other than `MIN_ROUTES`.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
