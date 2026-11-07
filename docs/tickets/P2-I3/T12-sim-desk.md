# P2-I3-T12 — Simulator: MaterialsDesk and the materials coordinator (an agent that proposes reservations)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: T04b, T07 (merged); Q10 (may run beside T06j: disjoint paths)
Branch: `p2/i3-t12-sim-desk`   (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
The simulator has a materials actor. `MaterialsCoordinator` is an agent like `WorkfacePlanner` (precedent: copy its shape, `actors/workface_planner.py`): it reads the project's short take-off lines and the stock over MCP and files `propose_reservation` proposals that a person accepts. It writes nothing itself. Off unless named in a scenario.

## Brief references (pasted)
> T07 (merged): MCP reads `list_material_stock`, `get_material_lot`, `list_material_movements`, `list_receipts`, `get_receipt`, `list_material_locations`, `list_po_lines`, `list_mto_lines`, `list_material_items`, and `propose_reservation(project, lot, location, mto_line, qty, summary?)`. `list_mto_lines(project, work_package?, short_only, limit)` answers `MtoLineView` rows; `list_material_stock(project, ...)` answers balance rows by lot, location and item. Each tool name is checked in `packages/tl-mcp/src/tl_mcp/materials_tools.py` (`MATERIALS_MCP_ACTIONS`).
> WorkfacePlanner pattern: `AwpDesk` Protocol in `tl_sim/client.py` (`@runtime_checkable`), `SimClient.areas()` calls `self._mcp.call_tool(...)`, raises `McpUnavailableError` when no caller is wired; the actor checks the client is the Desk or raises `ProposeUnavailableError`; `identity = ASSISTANT`; params class in `scenario.py` (`WorkfacePlannerParams`), switched on by name in `ActorsConfig` (default None), name added to `ACTOR_NAMES`; built in `actors/registry.py`.

## Interfaces (names are the contract)
```python
# tl_sim/client.py, next to AwpDesk
@runtime_checkable
class MaterialsDesk(Protocol):
    def short_lines(self, *, limit: int = 50) -> list[dict[str, Any]]: ...      # list_mto_lines(short_only=True)
    def stock(self, *, limit: int = 200) -> list[dict[str, Any]]: ...           # list_material_stock
    def propose_reservation(self, lot: str, location: str, mto_line: str, qty: str) -> dict[str, Any]: ...
# SimClient implements the three over self._mcp (same unwrapping of a `result` list as areas() does for a dict)
# tl_sim/scenario.py
class MaterialsCoordinatorParams(Strict):
    reservations_per_day: Count = 1
# ActorsConfig.materials_coordinator: MaterialsCoordinatorParams | None = None   # off unless named: needs materials stock
# tl_sim/actors/materials_coordinator.py
class MaterialsCoordinator(BaseActor):  name = "materials_coordinator"
```
Working day (`act`), in this order, draws from `ctx.rng` only where stated:
1. Draw `n = draw(params.reservations_per_day, ctx.rng)`. If 0, stop.
2. The client must be a `MaterialsDesk` (`ProposeUnavailableError` otherwise). Read `short_lines()`; with none, stop. Read `stock()`; keep rows with a positive `available`; with none, stop.
3. For each of the `n` proposals, in order: draw a short line `ctx.rng.choice(lines)` (lines sorted by key), then a stock row `ctx.rng.choice(rows)` (rows sorted by lot, location) whose `item_code` equals the line's `item_code`. Quantity is the smaller of the row's `available` and the line's `short`, as a plain decimal string; propose it.
Each proposal is recorded like the planner's (`rec` call and `Rec` fields: copy what `workface_planner.py` does). A refused proposal (the tool raises) is recorded as the planner records it and the day goes on.

## Context (read these, nothing else)
- `packages/tl-sim/src/tl_sim/actors/workface_planner.py`, `actors/registry.py`
- `packages/tl-sim/src/tl_sim/client.py` (AwpDesk, `areas()`, imports), `scenario.py` (WorkfacePlannerParams, ActorsConfig, ACTOR_NAMES)
- `packages/tl-mcp/src/tl_mcp/materials_tools.py` (argument names; `views.MtoLineView`, balance row field names in `packages/tl-modules/materials/src/tl_mod_materials/views.py`)
may explore: `packages/tl-sim/src/tl_sim/orchestrator_names.py`, `scenario_loader.py` only if a name list there must carry the new actor (say so in the report)

## Allowed paths
- `packages/tl-sim/src/tl_sim/client.py`, `scenario.py`, `actors/registry.py`, `actors/materials_coordinator.py` (create)
- `dev/accept/P2-I3/T12.py` (create), `docs/reports/P2-I3/T12.md` (create)
- Consequential pins (rule 12): an existing sim test that lists actor names or Desk protocols and breaks only for the new name, updated and listed
No test file of its own (T11 owns `test_materials_coordinator.py`). No MCP, API or materials change.

## Acceptance (run once; no pytest)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T12.py
```
Expected: exit 0, one `PASS <check>` per check. `T12.py` uses a fake McpCaller (a class with `call_tool`, no ledger) for: no short lines -> no call to `propose_reservation`; one short line and one matching stock row -> one proposal with the expected lot, location, line and quantity (the smaller of available and short); a stock row of another item -> no proposal and no extra draw (same rng state afterwards as after a day with `n=0` plus the two draws of step 3); `n=0` draws once only; same seed gives the same proposals twice; a client that is not a `MaterialsDesk` raises `ProposeUnavailableError`. One real check over a copy of `.accept/p2-i3.db` if `SimClient` can be built there as in the other sim acceptance scripts (copy one); otherwise say so in the report.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`, <= 60 lines) plus the output of each acceptance command (<= 5 lines each). More than 7 files changed means stop and say why.
Commit subjects `P2-I3-T12: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report Blocked if `MtoLineView.short` / `StockRowView.item_code` are missing from the MCP answer.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
