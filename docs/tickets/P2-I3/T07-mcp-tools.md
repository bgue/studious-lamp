# P2-I3-T07 — Materials MCP tools (nine reads and `propose_reservation`)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: mcp
Depends on: T04a (merged), S3 (merged)
Branch: `p2/i3-t07-mcp-tools`

## Goal
`packages/tl-mcp/src/tl_mcp/materials_tools.py` with `register_materials_tools(server, ctx)`: nine read-only tools over the materials views and one proposing tool.
An agent reads stock, lots, movements, receipts, locations, PO lines, take-off lines and the item library; it never changes anything: `propose_reservation` files a pending
proposal that a person with `materials.reserve` accepts (module.py already lists `ProposableCommand("propose_reservation", ReserveStock, handle_reserve_stock, "user")`).
The registry lines (`server.py` call, `identity.py` `MCP_ACTIONS`) are NOT in this ticket: the supervisor adds them when P2-I1 has merged. The module exports
`MATERIALS_MCP_ACTIONS: frozenset[str]` (the ten `mcp.<tool>` names) for that glue.

## Brief references (pasted)
> Every tool names its resource for the authorizer (`guarded`). Reading needs `document.read`. A new tool is closed to agents until it is in `MCP_ACTIONS`.
> Views are viewer-filtered; the MCP context's unit of work sets the viewer from the actor, tools pass none (as `schedule_read_tools.py`). Never read a record without the class filter.
> `propose_reservation` {project, lot, location, mto_line, qty, summary?}: dry-run by `proposals.submit`; `ReserveStock` carries one `Movement(lot_key, qty, uom, from_location, mto_line_id)`;
> `mto_line` is the line KEY (as the tools list it), resolved to its id here; `uom` is the lot's (from `lot_detail`). An unknown lot or line is a `ToolError` with the module's message.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views: stock(conn, scope, *, lot, location, item, heat, subtree, limit) -> list[StockRowView];  lot_detail(conn, scope, key) -> LotDetailView
#   movements(conn, scope, *, lot, since, until, kind, limit);  receipts(conn, scope, *, open_only, missing_mtr, limit);  receipt_detail(conn, scope, number)
#   locations_tree(conn, scope, *, limit);  po_lines(conn, scope, q, *, limit);  mto_lines(conn, scope, *, work_package, short_only, limit);  items(conn, *, project, limit)
# tl_mod_materials.handlers.movements: Movement(lot_key, qty: str, uom, from_location, mto_line_id, ...), ReserveStock(actor, source, scope, movements=[Movement])
# tl_core.services.proposals.submit(ctx.factory, tool=..., agent=ctx.actor, command=..., summary=...) -> view;  tl_mcp.write_tools: PROPOSES, ProposalResult, Summary, _result
```
Tool names (the resource kind is `materials`, parts `(project,)`; items use `resource_name("materials", "company")`):
`list_material_stock`, `get_material_lot`, `list_material_movements`, `list_material_receipts`, `get_material_receipt`, `list_material_locations`, `list_po_lines`, `list_mto_lines`,
`list_material_items`, `propose_reservation`. Parameters as the T04b client methods, text parameters `Field(max_length=MAX_PART)`, `limit` `ge=1, le=1000` default 200, `qty` string `max_length=32`.
Every read has `annotations=READ_ONLY`, the proposing tool `PROPOSES`. Docstrings say, in plain words, what the tool returns and what its filters do (the agent reads them).

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/schedule_read_tools.py` (pattern for `*_impl` + registration) and `schedule_tools.py` (pattern for the proposing tool)
- `packages/tl-modules/materials/src/tl_mod_materials/views.py` (signatures; read only) and `handlers/movements.py` lines 83-140 (`Movement`, `ReserveStock`)
- `packages/tl-mcp/tests/mcp_harness.py` and `tests/test_mcp_schedule_read_tools.py` (how a server is built and a tool called)
- `dev/accept/P2-I3/S3.py` (`--keep` writes the seed ledger `.accept/p2-i3.db`: lots `P123-RCPT-0001@1`, `@2`, MTO `ISO-1234@A/MTO`)
may explore: `packages/tl-mcp/src/tl_mcp/identity.py` (read only)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/materials_tools.py` (create)
- `dev/accept/P2-I3/T07.py` (create), `docs/reports/P2-I3/T07.md` (create)
Not here: `server.py`, `identity.py`, `schedule_*`, any test file, `views.py`, the module's `module.py`.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T07.py
```
`T07.py` (you write it, exit 0, one `PASS <check>` per line): it builds the server as the harness does, calls `register_materials_tools(server, ctx)` on it and an authorizer that allows
`MATERIALS_MCP_ACTIONS` for the test agent (a local hook, not an edit of `identity.py`); the ledger is a copy of the seed ledger. Checks: `MATERIALS_MCP_ACTIONS` has ten names, each equals `mcp.` + a registered tool;
each read answers (stock `>= 2` lots; `heat` narrows; lot detail; receipt `P123-RCPT-0001` has 2 lines; locations 9; po lines 15; mto lines for `P123-CWP-PIP-0001` 3; items 50);
an unknown lot raises `ToolError`; a part over `MAX_PART` is refused before the hook runs; with an authorizer that denies, a read raises `ToolError` and nothing is returned;
`propose_reservation` on lot `P123-RCPT-0001@1`, its location, line `ISO-1234@A/MTO/001`, qty `1` files one pending proposal (`PROPOSES`), changes no stock (the stock rows are equal before and after),
and an over-reservation (qty `100000`) is a `ToolError` with the handler's message; the file contains no `viewer`/`Viewer` argument (grep).
Confidentiality is plumbing here; the five-reader MCP walk over classified materials records is T11's (recorded in the report).

## Tests to add
None (T11: `packages/tl-mcp/tests/test_materials_tools.py` and the MCP walk entries).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines. Commit subjects `P2-I3-T07: ...`; the commit trailer is the attribution
lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if `proposals.submit` rejects `propose_reservation` as not proposable, if a view signature differs, or if reading needs an action name that is not `document.read`.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
