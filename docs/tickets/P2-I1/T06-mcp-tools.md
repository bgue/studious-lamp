# P2-I1-T06 — MCP read tools and `propose_cwp`

Status: ready
Tier: haiku
Review: full
Labels: mcp
Depends on: T03a (merged)
Branch: `p2/i1-t06-mcp`
Worktree: `/home/user/wt/i1/t06` (from `p2/i1` head)

## Goal
An agent reads CWPs, the WBS and the path of construction through four read-only tools and proposes a CWP through
`propose_cwp`; nothing changes until a person accepts. The tools answer from `tl_mod_awp.views` (same fields as the API and a screen)
under the agent's viewer, and are closed until listed in `MCP_ACTIONS`.

## Brief references (pasted; spec §9)
MCP read tools `list_cwps`, `get_cwp`, `wbs_tree`, `path_of_construction`; proposable tool `propose_cwp` (declared:
`tl_mod_awp/module.py` line 41, `ProposableCommand("propose_cwp", CreateCwp, handle_create_cwp, "user")`). Reading needs
`document.read` like the other reads (`guarded`). The agent may not create a CWP itself.

## Interfaces (verbatim)
```python
# tl_mod_awp.views: cwp_list(conn, scope, *, state=None, discipline=None, cwa=None) -> list[CwpRow]; cwp_detail(conn, scope, number) -> CwpDetail|None
#  wbs_tree(conn, scope, *, depth=None) -> list[WbsRow]; path(conn, scope, version=None) -> PathView|None
# tl_mod_awp.commands.CreateCwp: discipline, title, cwa_code, planned_start|None, planned_finish|None, budget_hours: str|None, quantities|None, contractor_text|None (+ actor, source, scope)
# pattern: tl_mcp/schedule_read_tools.py (xxx_impl(ctx, *, ...) + register_..._tools, READ_ONLY, guarded, resource_name) and tl_mcp/schedule_tools.py (propose_..._impl, proposals.submit, PROPOSES, _result)
```
Tools (names exact): `list_cwps(project, state?, discipline?, cwa?)`, `get_cwp(project, number)` (answers `RecordNotFoundError` text for a missing or hidden CWP,
as `get_schedule` does), `wbs_tree(project, depth? 1..20)`, `path_of_construction(project, version? >= 1)`, `propose_cwp(project, discipline, title, cwa_code,
planned_start?, planned_finish?, budget_hours?, summary?)`. `get_cwp` returns `cwp_detail` (no counts/timeline: those are an API/screen concern). Default summary of
the proposal: `Create a <discipline> CWP "<title>" in <cwa_code>`. `proposals.submit(..., tool="propose_cwp", ...)`.
Actions: add `mcp.list_cwps mcp.get_cwp mcp.wbs_tree mcp.path_of_construction mcp.propose_cwp` to `MCP_ACTIONS` (identity.py). The repo test that registers the
real server fails on a tool missing there or listed without existing; `write_tools.py` line 321 asserts every `PROPOSABLE_TOOLS` name has a mode: satisfy it the way the
schedule proposal does.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/schedule_read_tools.py` lines 1-60 and 181-215, `schedule_tools.py` (all), `server.py` lines 130-150
- `packages/tl-mcp/src/tl_mcp/identity.py` lines 25-100 (list), `write_tools.py` lines 300-330
- `packages/tl-mcp/tests/test_confidentiality_walk.py` lines 36-60 (argument candidates)
- `dev/accept/P2-I1/S4.py` lines 465-490 (`proposal(w)`: how a proposal is accepted)
may explore: `.accept/p2-i1.db`, `packages/tl-mcp/tests/mcp_harness.py`

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/awp_tools.py` (create), `server.py` (import and one `register_awp_tools(server, ctx)` line), `identity.py` (the five action lines)
- `packages/tl-mcp/tests/test_confidentiality_walk.py` (only `values()`: add `"number"` and `"code"` candidates `"P123-CWP-CIV-0001"`, `"1.1.1"` if absent)
- `dev/accept/P2-I1/T06.py` (create), `docs/reports/P2-I1/T06.md` (create)

## Steps
1. `awp_tools.py` with `list_cwps_impl`, `get_cwp_impl`, `wbs_tree_impl`, `path_impl`, `propose_cwp_impl` and `register_awp_tools`. Annotated argument types as in `schedule_read_tools.py`.
2. `T06.py` (`--db .accept/p2-i1.db`; build the MCP server on a copy of the seed as `mcp_harness.McpHarness` or `dev/accept/P2-I1/S4.py`'s World does): `PASS list_cwps 6 rows`, `PASS get_cwp`,
   `PASS get_cwp missing` (error text identical for a made-up number), `PASS wbs_tree`, `PASS path_of_construction`, `PASS propose_cwp waits` (a pending proposal, no CWP created: `list_cwps` still 6),
   `PASS accepted by a person` (accept as `user:uma`, as S4.py does; `list_cwps` 7), `PASS agent cannot` (an agent actor calling the command directly is refused). Ends `T06 ok`.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T06.py --db .accept/p2-i1.db
just gate packages/tl-mcp
```
Expected: `just check` clean; PASS lines and `T06 ok`; `gate: PASS` (the whole mcp package, including the action-list test and the walk).

## Tests to add
none (T11 writes `packages/tl-mcp/tests/test_awp_tools.py` and the awp walk entries).

## Report requirements
`docs/reports/P2-I1/T06.md` <= 60 lines, <= 5 decisive output lines per command; deviations first; pins outside Allowed paths (rule 12) listed. Subject `P2-I1-T06: ...`;
no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if a tool name collides with an existing one (`wbs_tree` is a route operation id, not an MCP name: check), if `propose_cwp` needs a `ProposableCommand` change, or if the walk fails on an awp tool.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
