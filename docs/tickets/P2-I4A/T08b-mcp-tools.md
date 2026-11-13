# P2-I4A-T08b — MCP tools: four reads and `propose_requisition`

Status: staged (dispatch after T04a merges)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, read, confidentiality
Depends on: T04a
Branch: `p2/i4a-t08b-mcp-tools`
Worktree: harness-created under `/home/user/wt/i4a/t08b` (from `p2/i4a` head)
Approver: orchestrator (the new tool is closed until listed; ADR-0027)

## Goal
An agent reads requisitions and work orders and proposes a new requisition; nothing changes until a person accepts. The new file is `packages/tl-mcp/src/tl_mcp/requisition_tools.py`, built exactly on the pattern of `packages/tl-mcp/src/tl_mcp/iwp_tools.py` (`propose_iwp_scope` is the model for the proposal: keys resolved to ids with `get_record` under the agent's viewer, `proposals.submit`, `_result`; the reads use `guarded`, `ctx.factory(True)`, one error text for missing and hidden). The demo gap of P2-I5 was a missing propose tool: this ticket is that tool, and the demo (T10b) calls it.

## Tools (names exact; action word `mcp.<tool>`)
| Tool | Args | Reads |
|---|---|---|
| `list_requisitions` | project, kind?, state?, requester?, for_key? | `views.requisition_list` (under `confidentiality.current_viewer()`) |
| `get_requisition` | project, key | `views.requisition_detail`; `None` is the missing error |
| `list_work_orders` | project, state?, assigned_to? | `views.work_order_list` |
| `get_work_order` | project, key | `views.work_order_detail`; `None` is the missing error |
| `propose_requisition` | project, kind (`labor`/`material`/`general`/`scaffold`), subject, need_by?, priority?, for_key? (IWP or CWP key), craft?, headcount?, start_date?, end_date? (labour); lines? (list of item key, qty, uom; material); general_type? ; purpose?, duration_days? (scaffold); summary?, intent (`IntentParam`) | proposal of `RaiseRequisition`; `for_key` and item keys resolved to ids as above (unknown or hidden: `no record with that key`); the kind's required fields are checked by the command model, a bad combination is a `ValueError` with the model's text; no `requester` argument |
Declaration: the `PROPOSABLE` row `propose_requisition` already exists in `tl_mod_requisitions/module.py` (S2; do not edit). Action list: `REQUISITION_MCP_ACTIONS` frozenset (the five words) in the new file, imported into `identity.py` and OR-ed into `MCP_ACTIONS` as `IWP_MCP_ACTIONS` is. Default summary `Raise a <kind> requisition: <subject>`. The row-or-exclusion test (`tests/tools`) must stay green.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/iwp_tools.py` (all), `identity.py` (lines 20-30 and 95-110), `server.py` (lines 40-50 and 145-155)
- `packages/tl-mcp/tests/{test_awp_tools.py (lines 1-60), test_confidentiality_walk.py (lines 30-70), mcp_harness.py}`
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/{views.py, commands.py (lines 91-175), module.py (lines 100-110)}`, `docs/reports/P2-I4A/T04a.md`

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/requisition_tools.py` (create), `server.py` (import and one `register_requisition_tools(server, ctx)` line), `identity.py` (import and OR line)
- `packages/tl-mcp/tests/test_requisition_tools.py` (create), `packages/tl-mcp/tests/test_confidentiality_walk.py` (only the argument candidates `values()`: `kind`, `for_key`, `subject` if absent)
- tool-count or action-list pins (`test_mcp_server.py`, `test_mcp_identity.py`; union form, listed)
- `docs/reports/P2-I4A/T08b.md` (create)

## Acceptance
```
just check
just gate packages/tl-mcp/tests/test_requisition_tools.py packages/tl-mcp/tests/test_confidentiality_walk.py packages/tl-mcp/tests/test_mcp_server.py packages/tl-mcp/tests/test_mcp_identity.py packages/tl-mcp/tests/test_mcp_propose_dispatch.py tests/tools
```
(`tests/tools` takes about 10 minutes: run it in the background.)

## Tests to add
`packages/tl-mcp/tests/test_requisition_tools.py` (MCP harness as `test_awp_tools.py`; ledger built by commands through the `req_world.py` helper loaded by path; no projection writes): the four reads return rows; a missing key and a key of another project give one text; `propose_requisition` for a labour requisition files a pending proposal and no requisition row exists until `sue` or `uma` (a `user`) accepts it, then `P123-REQ-LAB-0001` exists and its requester is the accepting person (not the agent); the same for a material proposal with an item key; an unknown `for_key` is refused with the one text; an agent cannot approve (no such tool; `approve_requisition` is not in `MCP_ACTIONS`); the five `mcp.` words are in `MCP_ACTIONS` and a tool name not listed is refused; five kinds of reader on the reads, as the walk file does.

## Escalation triggers
- The server test counts tools in a way that needs a change outside Allowed paths (list it); `ProposableCommand` refuses the handler; the row-or-exclusion test fails.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T08b: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
