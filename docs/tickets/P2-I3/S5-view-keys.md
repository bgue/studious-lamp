# P2-I3-S5 — View keys for the screens (movement/lot For, received_by, MTO line detail, item quantities per project)

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core-module, api
Depends on: T04a, T04b, T05a (merged); decision Q6 = YES (r6)
Branch: `p2/i3-s5-view-keys`  (from p2/i3 at the r6 state commit; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
The screens of T06 (and their web twins) need facts the views carry only as ids (D26). After this piece they have them, additively: every new field of an existing
model has a default, so nothing that builds those models today (fakes, T06a fixtures, T07) breaks. Two new reads and their routes and client methods carry what no
route returned: one MTO line with its lot reservations and the open receipts for its item, and the per-project quantities of one company item.

## Brief references
> Spec `docs/build-spec/specs/m4-materials.md` §7 (screens: Lot reservations `For`; Movement `For`; Receipt `Received by`; MTO line Coverage lot table and Open receipts; Item Projects table) and §9.
> Text contracts `docs/tickets/P2-I3/text-contracts.md` (Deferred section: this piece supplies exactly those).
> Views are viewer-filtered (ADR-0016): a hidden record answers as one that never existed. Routes pass no viewer (D23); the API and embedded unit of work set it. New SQL goes through
> the same `_hide(...)` / class-filter helpers as the existing views; nothing is read from an event table without the viewer's filter.

## Interfaces (keep these names; shapes are the contract T06b-g and T05d call)
Existing models, new fields (all with defaults):
```python
class MovementView:     mto_line: str | None = None; work_package: str | None = None; cost_code: str | None = None
    # mto_line = the MTO line key; work_package = its work package number; cost_code = the cost code's code (not its id)
class ReservationView:  work_package: str | None = None      # work package number of the reserved MTO line
class ReceiptDetailView: received_by: str | None = None      # the actor that filed the receipt (see Escalation)
```
New models and functions (a new module `tl_mod_materials/views_detail.py`; unique class names, openapi renames duplicates):
```python
class OpenReceiptView(BaseModel): number: str; state: str; received_on: str; qty: Decimal; uom: str; supplier_text: str
    # a receipt in state Received or Inspected with a line of this item; qty = sum of its lines of that item
class MtoLineDetailView(MtoLineView): reservations: list[ReservationRowView]; open_receipts: list[OpenReceiptView]
    # reservations = lot reservations against this line (lot, location, qty; same rows as reservations_for_iwp but for one line)
class ItemProjectView(BaseModel): project: str; title: str; on_hand: Decimal; reserved: Decimal; available: Decimal; uom: str
    # one row per visible project that adopted the item; the sum of stock rows of that item in that project
def mto_line_detail(conn, scope: str, key: str, *, viewer: Viewer | None = None) -> MtoLineDetailView   # unknown/hidden: MtoLineNotFoundError (exists)
def item_projects(conn, code: str, *, viewer: Viewer | None = None) -> list[ItemProjectView]            # unknown/hidden item: []
```
Routes (guard `document.read`, as T04a; `ctx.backend(True)`, no viewer):
- `GET /projects/{project}/materials/mto-line?key=<line key>` operation `get_materials_mto_line` -> `MtoLineDetailView` (key in a query: it holds `/` and `@`; `MtoLineNotFoundError` -> 404 as the existing table row)
- `GET /companies/materials/item-projects?code=<item code>` operation `list_materials_item_projects` -> `list[ItemProjectView]`
Client (all four: `ApiClient` via `client/materials.py`, `ClientInterface`, `EmbeddedClient`, `FakeClient`; pattern = T04b):
```python
get_materials_mto_line(self, project, key) -> MtoLineDetailView
list_materials_item_projects(self, code) -> list[ItemProjectView]
# fake: put_mto_line_details(project, details), put_item_projects(code, rows); unknown line raises MtoLineNotFoundError(key)
```

## Context (read these, nothing else)
- `packages/tl-modules/materials/src/tl_mod_materials/views.py` (models; `_hide`, `_movement_row`, `lot_detail`, `receipt_detail`, `_line_view`, `reservations_for_iwp`), `limits.py`, `errors.py`
- `packages/tl-api/src/tl_api/routes/materials.py`, `packages/tl-api/src/tl_api/client/materials.py`
- `packages/tl-tui/src/tl_tui/client.py`, `embedded.py` (materials blocks), `packages/tl-tui/tests/fakes_materials.py`
- `docs/reports/P2-I3/T04a.md`, `T04b.md` (route and client patterns, pins, MIN_ROUTES)
may explore: `projectors/receipts.py`, `projectors/stock.py`, `handlers/receipts.py` (where `received_by` can come from)

## Allowed paths
- `packages/tl-modules/materials/src/tl_mod_materials/views.py`, `views_detail.py` (create)
- `packages/tl-api/src/tl_api/routes/materials.py`, `packages/tl-api/src/tl_api/client/materials.py`
- `packages/tl-tui/src/tl_tui/client.py`, `embedded.py` (materials block only), `packages/tl-tui/tests/fakes_materials.py`
- `packages/tl-api/tests/test_confidentiality_walk.py` (`MIN_ROUTES` +2), `docs/reference/openapi.json` (regenerate)
- `dev/accept/P2-I3/S5.py` (create), `docs/reports/P2-I3/S5.md` (create)
Consequential pins (rule 12): a test that lists client methods or routes and breaks only for the new names is updated and listed. No schema, no projector, no handler change.

## Acceptance (run once; no pytest; tests are T11's)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/S5.py
just gate packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_error_table.py packages/tl-api/tests/test_auth_review.py packages/tl-tui/tests/test_fakes.py tests/api/test_client_roundtrip.py
```
`S5.py` (exit 0, one `PASS <check>` per line, sqlite seed copy; Postgres too if `TL_PG_URL` is set): the seed movements for lot `P123-RCPT-0001@1` carry `mto_line`/`work_package` for a reserve or issue
movement and `cost_code` for a consumable issue (add one through the commands if the seed has none, in a temp copy); lot reservations carry `work_package` `P123-CWP-PIP-0001`; the receipt `P123-RCPT-0001` has
a non-empty `received_by`; `mto_line_detail` of the first seeded line has its reservations and an `open_receipts` list (empty when all receipts are accepted; create an Inspected one in a temp copy and see it);
unknown key raises `MtoLineNotFoundError`; `item_projects` of a seeded item adopted by `P123` has one row with `on_hand` equal to the sum of `views.stock` for that item, an unknown code gives `[]`;
embedded, API and fake agree on both new methods (`model_dump` equal); old constructors without the new fields still validate; routes: 200, unknown key 404, no token 401; the ten new/changed names exist on all four client classes.

## Tests to add
None under `tests/` (T11). Mutation guards for T11: list in the report (3 lines, `file:line`): the class filter on `received_by`, the hidden-project filter in `item_projects`, the `Received/Inspected` filter in `open_receipts`.

## Report requirements
Piece report (<= 60 lines): deviations first; pins changed; acceptance output (<= 5 lines per command); builder return <= 15 lines in Code 92.
Commit subjects `P2-I3-S5: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
Stop and write *Blocked* if: `received_by` has no source readable with the viewer's class filter and without a schema, projector or handler change (then say what the cheapest source is); a new `ServiceError` class is
needed; a field must lose its default; or `MovementView` work-package/cost-code lookups need a join that the existing tables do not support.

## Blocked
(builder writes here)

## Decision
(supervisor writes here)
