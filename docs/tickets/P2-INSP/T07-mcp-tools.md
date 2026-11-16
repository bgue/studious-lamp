# P2-INSP-T07 - MCP tools for inspections

Status: ready (written r4; base `p2/ip-r3`; INSP-S2 and T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, quality, confidentiality
Depends on: P2-INSP-S2 (`propose_inspection` row), P2-INSP-T01 (views), merged
Branch: `p2/insp-t07-mcp-tools`
Worktree: `/home/user/wt/insp/t07` (from `p2/ip-r3`)

## Goal
`tl_mcp/insp_tools.py` registers four reads (`list_inspections`, `get_inspection`, `list_checklists`, `get_checklist`) and `propose_inspection` (a pending proposal of `PlanInspection`, never a write). Each is closed to agents until an allow row lists it. There is no tool that schedules, records, verifies or cancels.

## Rules
- Pattern: `tl_mcp/punch_tools.py` whole (`guarded`, `McpContext`, `READ_ONLY`, `PROPOSES`, `IntentParam`, `proposals.submit`, the `PUNCH_MCP_ACTIONS` tuple and how `tl_mcp/identity.py` imports it into `MCP_ACTIONS`). Name the tuple `INSP_MCP_ACTIONS` and import it the same way (one line in `identity.py`).
- Reads under `guarded` (lowest clearance) with `insp_views.*`, `viewer=` explicit; a missing, hidden or other-project key answers `RecordNotFoundError("no inspection <key>")` as `punch_tools` does for a punch item; `list_*` take `project`, the same filters as the CLI list and `limit` (default 50, at most `MAX_PART`).
- `propose_inspection(project, subject_key, title, point, for_key?, area?, planned_on?, summary?, intent)`: resolves keys with `get_record` under the lowest viewer, files `proposals.submit(... command PlanInspection ...)` exactly as `propose_punch_item_impl`; the accepting person needs `quality.inspection.plan` (S2 already set the `PROPOSABLE` row).
- Hook: append `"tl_mcp.insp_tools:register_insp_tools"` to `tools` in `tl_mod_quality/module.py` (append only). `OLD_TOOL_NAMES` in `packages/tl-mcp/tests/test_module_tool_hooks.py` is extended for the five names by union.
- No SQL; no import of `tl_api`, `tl_cli`.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/punch_tools.py` (whole), `packages/tl-mcp/src/tl_mcp/identity.py` (the `PUNCH_MCP_ACTIONS` lines only)
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (signatures), `commands.py` (`PlanInspection`, lines 318-340), `module.py` (156-180)
- `packages/tl-mcp/tests/test_punch_tools.py` (1-140), `packages/tl-mcp/tests/test_module_tool_hooks.py` (the pin)

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/insp_tools.py` (create), `packages/tl-mcp/src/tl_mcp/identity.py` (the one import and the one tuple line)
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` (the one `tools` line)
- `packages/tl-mcp/tests/test_insp_tools.py` (create), `packages/tl-mcp/tests/test_module_tool_hooks.py` (the pin by union)
- `docs/reports/P2-INSP/T07.md` (create)

## Tests to add (`test_insp_tools.py`; ledger from `InspWorld`, harness as `test_punch_tools.py`)
1. Each read tool for the five readers: the reader who cannot see the subject gets no row and the same error as a missing key; list totals count after the filter.
2. An agent with no allow row is refused every tool (`agent_may` false); after the allow row from `INSP_MCP_ACTIONS` the reads work and `propose_inspection` files a pending proposal that changes no record.
3. Accepting the proposal as a person with `quality.inspection.plan` plans the inspection; without the word it is refused (`ProposalAccessError`).
4. No tool named schedule, record, verify, reinspect or cancel exists (`tools/list` check).
5. The tool names appear in the registry pin; nothing else moved.

## Acceptance
```
uv run ruff format --check packages/tl-mcp/src/tl_mcp/insp_tools.py packages/tl-mcp/src/tl_mcp/identity.py packages/tl-mcp/tests/test_insp_tools.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run ruff check packages/tl-mcp/src/tl_mcp/insp_tools.py packages/tl-mcp/src/tl_mcp/identity.py packages/tl-mcp/tests/test_insp_tools.py packages/tl-modules/quality/src/tl_mod_quality/module.py
uv run pyright packages/tl-mcp/src/tl_mcp/insp_tools.py packages/tl-mcp/src/tl_mcp/identity.py packages/tl-mcp/tests/test_insp_tools.py packages/tl-modules/quality/src/tl_mod_quality/module.py
just gate packages/tl-mcp/tests/test_insp_tools.py
just gate packages/tl-mcp/tests/test_module_tool_hooks.py
```
Expected: clean on those paths; `gate: PASS` on each line. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
An agent can read a hidden inspection or a count that includes one; `identity.py` needs more than the one tuple; a proposal field the intent parameter cannot carry.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins and regenerated files outside Allowed paths. Commit subjects `P2-INSP-T07: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
