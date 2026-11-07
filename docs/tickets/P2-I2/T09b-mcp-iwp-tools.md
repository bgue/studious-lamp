# P2-I2-T09b — MCP reads and proposals: IWPs, constraints, readiness

Status: staged (dispatch after T04c1 merges: it needs `visible_readiness`; T04c2 is not a dependency, the tools read the views, not a client)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, read, confidentiality, access
Depends on: T04c1 (`visible_readiness`), C2 (merged), T04a, T04a2 (merged)
Branch: `p2/i2-t09b-mcp-iwp-tools`
Worktree: harness-created under `/home/user/wt/i2/t09b` (from `p2/i2` head)

## Goal
An agent reads IWPs, constraints and readiness through seven read-only tools and proposes a constraint or an IWP scope addition through two proposing tools; nothing changes until a person accepts. Model: P2-I1 T06 (`docs/tickets/P2-I1/T06-mcp-tools.md`; `tl_mcp/awp_tools.py` is the pattern, `materials_tools.py` the module-local actions frozenset). The tools are closed until listed in the agent actions.

## Tools and access words (names exact; decided here, do not reopen)
| Tool | Args | Reads | Action word |
|---|---|---|---|
| `list_iwps` | project, state?, discipline?, foreman? | `iwp_views.iwp_list` | `mcp.list_iwps` |
| `get_iwp` | project, number | `iwp_views.iwp_detail` (None = the missing/hidden error) | `mcp.get_iwp` |
| `list_iwp_scope` | project, number | `iwp_views.iwp_scope` (None = the same error) | `mcp.list_iwp_scope` |
| `get_iwp_readiness` | project, number | `readiness.views.visible_readiness(conn, scope, number, viewer)` (D32; never `readiness()`); route model shape: no `facts_hash` | `mcp.get_iwp_readiness` |
| `list_constraints` | project, subject?, state?, category?, phase?, blocking?, owner? | `tl_core.constraints.list_constraints` and `count_constraints` (rows plus total) | `mcp.list_constraints` |
| `get_constraint` | project, key | `get_constraint` (hidden subject = the missing error) | `mcp.get_constraint` |
| `constraint_groups` | project, by (`owner\|category\|age`) | `review_groups` | `mcp.constraint_groups` |
| `propose_constraint` | project, subject (record key), phase, severity, category, owner?, description?, due_at?, summary? | proposal of core `RaiseConstraint` (source kind fixed `manual`; the tool has no `source_kind`, `check_name`, `facts_hash`, `target*` arguments) | `mcp.propose_constraint`; accepting person holds `user` |
| `propose_iwp_scope` | project, iwp (number), items (record keys, at most 50), summary? | proposal of `AddIwpScope` | `mcp.propose_iwp_scope`; accepting person holds `user` |
Read tools use the same `guarded(ctx, ...)` as `list_cwps` (needs `document.read`). The three constraint reads first check `core.constraint.view` for the agent's actor in the project scope before any lookup, with the helper `tl_cli.constraint_read.require_view` pattern (D25; copy the few lines, tl-mcp must not import tl-cli); a refusal reads as the tool's normal access error. `subject` and `iwp` keys are resolved to ids with `tl_core.services.queries.get_record` under the agent's viewer; an unknown or hidden key answers one text, `no record with that key`. Default summaries: `Raise a <severity> <category> constraint on <subject>`; `Add <n> scope items to <iwp>`.
Proposal declarations: two lines in `PROPOSABLE` of `tl_mod_awp/module.py`: `ProposableCommand("propose_constraint", RaiseConstraint, handle_raise_constraint, "user")` (handler `tl_core.constraints.handlers.handle_raise_constraint`) and `ProposableCommand("propose_iwp_scope", AddIwpScope, handle_add_iwp_scope, "user")` (`tl_mod_awp.handlers.scope`); append at the tuple end. Action list: `IWP_MCP_ACTIONS` frozenset in `iwp_tools.py` (the nine words), imported into `identity.py` and OR-ed into `MCP_ACTIONS` as `MATERIALS_MCP_ACTIONS` is.

## Interfaces (create)
```python
# tl_mcp/iwp_tools.py: <tool>_impl(ctx, *, ...) per tool, register_iwp_tools(server, ctx), IWP_MCP_ACTIONS
# Annotated arg types and READ_ONLY / PROPOSES / ProposalResult / Summary / _result as in awp_tools.py
```

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/awp_tools.py` (all), `materials_tools.py` lines 1-60, `identity.py` lines 20-30 and 85-110, `server.py` lines 130-150, `write_tools.py` lines 300-325
- `packages/tl-mcp/tests/test_confidentiality_walk.py` lines 36-60 (argument candidates), `dev/accept/P2-I1/T06.py` (the harness use), `docs/reports/P2-I2/T04c1.md`
- `packages/tl-core/src/tl_core/constraints/commands.py` lines 82-135 (RaiseConstraint fields; reuse its `Literal`s), `packages/tl-modules/awp/src/tl_mod_awp/commands.py` lines 586-598

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/iwp_tools.py` (create), `server.py` (import and one `register_iwp_tools(server, ctx)` line), `identity.py` (the import and the OR line)
- `packages/tl-modules/awp/src/tl_mod_awp/module.py` (the two `PROPOSABLE` entries and their imports only)
- `packages/tl-mcp/tests/test_confidentiality_walk.py` (only `values()`: add `"number"`, `"key"`, `"subject"`, `"iwp"` candidates if absent)
- `dev/accept/P2-I2/T09b.py` (create), `docs/reports/P2-I2/T09b.md` (create)

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T09b.py
just gate packages/tl-mcp/tests/test_confidentiality_walk.py packages/tl-mcp/tests/test_mcp_server.py packages/tl-mcp/tests/test_mcp_identity.py packages/tl-mcp/tests/test_mcp_propose_dispatch.py
```
`T09b.py` (MCP harness on a copy of a C2/S4 world ledger, as `dev/accept/P2-I1/T06.py`): `PASS <tool> <n>` for the seven reads; `PASS hidden` a low-clearance agent gets the same error text for a hidden IWP, readiness and constraint as for a missing one, no hidden row in a list or its total; `PASS no-ids` no `facts_hash`, no 32-hex id in any read result, hidden refs absent from the readiness; `PASS word` an agent whose actor lacks `core.constraint.view` is refused by the three constraint reads before any lookup; `PASS propose` each proposing tool files a pending proposal and no row is written until a person accepts (accept via the harness as T06 does; the accepted constraint has source `manual`); `PASS closed` the nine words are in `MCP_ACTIONS`; a tool name not listed is refused. Ends `T09b ok`.

## Tests to add
None (S5 walks every new tool as five readers).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Subject `P2-I2-T09b: ...`; trailer is the attribution lines your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- Stop and write *Blocked* if the server test counts tools or actions in a way that needs a change outside Allowed paths (list it), or `ProposableCommand` refuses a core handler.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
