# P2-PUNCH-T05 — MCP reads and `propose_punch_item`

Status: staged (dispatch after T01 merges; needs only the views, not a client)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, read, confidentiality, access
Depends on: T01
Branch: `p2/punch-t05-mcp`
Worktree: harness-created under `/home/user/wt/punch/t05` (from `p2/punch` head)
Approver: orchestrator (the new tools are closed until listed; ADR-0027)

## Goal
An agent reads punch items and proposes a new one; nothing changes until a person accepts. The new file is `packages/tl-mcp/src/tl_mcp/punch_tools.py`, built exactly on `packages/tl-mcp/src/tl_mcp/iwp_tools.py` (`propose_iwp_scope` is the model for the proposal: key resolved to an id with `get_record` under the agent's viewer, `proposals.submit`, `_result`; the reads use `guarded`, `ctx.factory(True)`, one error text for missing and hidden). The P2-I5 demo gap was a missing propose tool file: this ticket is that file for punch, and demo clause 6 calls it. There is no tool that clears, verifies, reopens or voids.

## Tools (names exact; action word `mcp.<tool>`)
| Tool | Args | Reads |
|---|---|---|
| `list_punch_items` | project, state?, area?, system?, assignee?, category?, overdue? (the tool passes `date.today()`) | `views.punch_list` under `confidentiality.current_viewer()` (rows and total) |
| `get_punch_item` | project, key | `views.punch_detail`; `None` is the missing error (`no punch item <key>`) |
| `propose_punch_item` | project, subject, description?, area?, system?, due_on?, category? (A/B/C), assignee?, from_key? (any record key), summary?, intent (`IntentParam`) | proposal of `RaisePunchItem`; `from_key` resolved to an id as above (unknown or hidden: `no record with that key`); there is no `raised_by` argument; default summary `Raise punch item: <subject>` |
Declaration: the `PROPOSABLE` row `propose_punch_item` exists in `tl_mod_quality/module.py` (S2; do not edit). Action list: `PUNCH_MCP_ACTIONS` frozenset (the three words) in the new file, imported into `identity.py` and OR-ed into `MCP_ACTIONS` as `IWP_MCP_ACTIONS` is. The agent's filing check needs the module's `user` word on the scope (ADR-0027 plan check F1), as the existing proposing tools do. The row-or-exclusion test (`tests/tools`) must stay green.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/iwp_tools.py` (all), `identity.py` (lines 20-30 and 95-110), `server.py` (lines 40-50 and 145-155)
- `packages/tl-mcp/tests/{test_awp_tools.py (lines 1-60), test_confidentiality_walk.py (lines 30-70), mcp_harness.py}`
- `packages/tl-modules/quality/src/tl_mod_quality/{views.py, commands.py, module.py}`, `docs/reports/P2-PUNCH/{S2,T01}.md`

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/punch_tools.py` (create), `server.py` (import and one `register_punch_tools(server, ctx)` line), `identity.py` (import and OR line)
- `packages/tl-mcp/tests/test_punch_tools.py` (create), `packages/tl-mcp/tests/test_confidentiality_walk.py` (only the argument candidates `values()`: `key`, `from_key`, `subject` if absent)
- pins in union form, listed: `test_mcp_server.py`, `test_mcp_identity.py`, `test_intent_param.py`, `test_mcp_write_tools.py` (tool and action counts)
- `docs/reports/P2-PUNCH/T05.md` (create)
The dependency `tl-mod-quality` is already in `packages/tl-mcp/pyproject.toml` (S1).

## Acceptance
```
just check
just gate packages/tl-mcp/tests/test_punch_tools.py packages/tl-mcp/tests/test_confidentiality_walk.py packages/tl-mcp/tests/test_mcp_server.py packages/tl-mcp/tests/test_mcp_identity.py packages/tl-mcp/tests/test_mcp_propose_dispatch.py packages/tl-mcp/tests/test_intent_param.py packages/tl-mcp/tests/test_mcp_write_tools.py tests/tools
```
(`tests/tools` takes about 10 minutes: background.)

## Tests to add
`packages/tl-mcp/tests/test_punch_tools.py` (MCP harness as `test_awp_tools.py`; ledger built by commands through `punch_world.py` loaded by path; no projection writes): the two reads return rows and the page total; a missing key and a key of another project give one text; `propose_punch_item` files a pending proposal and no punch row exists until `uma` (a `user`) accepts it, then `P123-PUN-0001` exists with `raised_by` `user:uma` (the accepting person, not the agent); the same with `from_key` an IWP key (the `raised_against` link exists after accept); an unknown `from_key` and a restricted correspondence item's key (low-clearance agent) are refused with the one text `no record with that key`; an item raised from a restricted item (helper) is absent from `list_punch_items` and `get_punch_item` gives the missing text for the agent; `mcp.clear_punch_item`, `mcp.verify_punch_item` are not in `MCP_ACTIONS` and not tools; the three `mcp.` words are in `MCP_ACTIONS` and a tool name not listed is refused; five kinds of reader on the reads, as the walk file does.

## Escalation triggers
- The server test counts tools in a way that needs a change outside Allowed paths (list it); `ProposableCommand` refuses the handler; the row-or-exclusion test fails.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-PUNCH-T05: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
