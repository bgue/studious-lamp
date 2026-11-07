# P2-I3-T04b — Materials client methods (ApiClient, ClientInterface, embedded, fake)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: api, tui
Depends on: T04a (merged)
Branch: `p2/i3-t04b-client-methods`

## Goal
The screens (T06a-e), the web twins and the simulator read materials through `ClientInterface`. After this ticket the nine T04a routes have a client method each
(same name, parameters and return type on `ApiClient`, the TUI `ClientInterface`, `EmbeddedClient` and `FakeClient`), plus one write door, `materials_command(name, cmd)`.
`RemoteClient` passes them through by `__getattr__`; the existing round-trip test compares the signatures.

## Brief references (pasted)
> Views (viewer-filtered) in `tl_mod_materials.views`; API GET (`materials.view` role, guard `document.read`): see T04a. Writes are `POST /commands/<Name>` from `MATERIALS_COMMANDS`.
> Errors: `LotNotFoundError`, `ReceiptNotFoundError` are rebuilt by the client from the 404 body (as `CostCodeNotFoundError` is in `client/cost.py`).
> The viewer is never passed by the client or the embedded call (D23: the API and the embedded unit of work set it; same as `list_cost_codes`).

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views models: StockRowView LotDetailView MovementView ReceiptView ReceiptDetailView LocationView PoLineView MtoLineView MaterialItemView
# tl_mod_materials.limits.MAX_VIEW_ROWS == 1000;  tl_mod_materials.commands.MATERIALS_COMMANDS: tuple[CommandSpec, ...]  (.model, .handler)
# the methods to add, on all four classes (limit defaults to 1000):
list_materials_stock(self, project, *, lot=None, location=None, item=None, heat=None, subtree=False, limit=1000) -> list[StockRowView]
get_materials_lot(self, project, key) -> LotDetailView
list_materials_movements(self, project, *, lot=None, since=None, until=None, kind=None, limit=1000) -> list[MovementView]
list_materials_receipts(self, project, *, open_only=False, missing_mtr=False, limit=1000) -> list[ReceiptView]
get_materials_receipt(self, project, number) -> ReceiptDetailView
list_materials_locations(self, project, *, limit=1000) -> list[LocationView]
list_materials_po_lines(self, project, *, q=None, limit=1000) -> list[PoLineView]
list_materials_mto_lines(self, project, *, work_package=None, short_only=False, limit=1000) -> list[MtoLineView]
list_materials_items(self, *, project=None, limit=1000) -> list[MaterialItemView]
materials_command(self, name: str, cmd: Command) -> CommandResult      # name must be a model name in MATERIALS_COMMANDS and type(cmd) is that model, else ForbiddenError
```
Pattern to copy: `client/cost.py` (`CostApi`: `_get_json`, `_models`, `_model`, `quote`), `ClientInterface.list_cost_codes` docstring style in `tl_tui/client.py`, `EmbeddedClient.list_cost_codes` and
`schemareg_command` in `embedded.py`, `FakeScheduleSupport` in `tests/fakes_schedule.py`. Routes and query names: `docs/tickets/P2-I3/T04a-api-reads.md` Interfaces.
Note `list_materials_items` calls `GET /companies/materials/items` with `project` optional; the embedded call passes `project=f"project:{project}"` when given, else `None` (as the route does).

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/client/cost.py`, `packages/tl-api/src/tl_api/client/__init__.py` (the mixin list)
- `packages/tl-tui/src/tl_tui/client.py` (the cost block near line 848 and `schemareg_command`; add a block `# --- materials (P2-I3) ---` after the cost block)
- `packages/tl-tui/src/tl_tui/embedded.py` (cost block near line 1463, `schemareg_command`)
- `packages/tl-tui/tests/fakes_schedule.py` (shape of a fake support class), `packages/tl-tui/tests/fakes.py` (the `FakeClient(...)` bases list)
may explore: `packages/tl-tui/tests/test_client_roundtrip.py` (the signature comparison), `packages/tl-api/src/tl_api/routes/materials.py`

## Allowed paths
- `packages/tl-api/src/tl_api/client/materials.py` (create: `MaterialsApi(ApiClientBase)`), `packages/tl-api/src/tl_api/client/__init__.py` (import and one base)
- `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py` (the new block only)
- `packages/tl-tui/tests/fakes_materials.py` (create: `FakeMaterialsSupport`), `packages/tl-tui/tests/fakes.py` (import and one base)
- `dev/accept/P2-I3/T04b.py` (create), `docs/reports/P2-I3/T04b.md` (create)
Consequential pins (rule 12): a test that lists `ClientInterface` or `ApiClient` methods and breaks only for the new names is updated and listed in the report.
Not here: `views.py`, routes, `remote.py` (passes through), screens.

## Fake behaviour
`FakeMaterialsSupport` holds per-project lists and answers the reads with the same filters as the routes (stock: lot, location, item, heat, subtree by `location` prefix of the codes in `locations`;
movements: lot, kind, since/until on `recorded_at[:10]`; receipts: `open_only` keeps Received and Inspected, `missing_mtr` keeps `mtr == "missing"`; po-lines `q` substring on key, item_code, supplier_text;
mto-lines `work_package`, `short_only` keeps `short > 0`; items `project` ignored). Setters: `put_materials(project, *, stock=(), movements=(), receipts=(), locations=(), po_lines=(), mto_lines=(), lots=(), receipt_details=())`
and `put_material_items(items)`. Unknown lot key raises `LotNotFoundError(key)`, unknown receipt `ReceiptNotFoundError(number)`. `limit` cuts the list. `materials_command` appends `cmd` to `self.materials_commands`
and returns `CommandResult(stream_id="MAT-1", key=None, version=1, events=[])` after the same name check as the embedded one.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T04b.py
just gate packages/tl-tui/tests/test_client_roundtrip.py packages/tl-tui/tests/test_fakes.py
```
`T04b.py` (you write it, exit 0, one `PASS <check>` per line): on `EmbeddedClient` over a copy of `.accept/p2-i3.db` (build it as `test_embedded_schedule.py` builds its client) and on the API client over
the harness of `packages/tl-api/tests/harness.py`: every list method returns the same rows (`model_dump` equal) as the other and as the view call; seeded counts stock `>= 2` lots, locations 9, po-lines 15,
mto-lines for `P123-CWP-PIP-0001` 3, items 50; `get_materials_lot` of an unknown key raises `LotNotFoundError` on both; `get_materials_receipt("P123-RCPT-0001")` has 2 `line_rows`; `materials_command("NoSuch", cmd)`
raises `ForbiddenError`; `FakeClient` answers the same filters on a small set (stock with `heat`, receipts with `missing_mtr`) and `isinstance`/signature check: the ten method names exist on all four classes.

## Tests to add
None (T11: `packages/tl-tui/tests/test_client_materials.py`).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines. Commit subjects `P2-I3-T04b: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a route's parameter differs from the list above, if the round-trip test needs more than a method-name pin, or if `materials_command` needs a gate outside `_command_gate`.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
