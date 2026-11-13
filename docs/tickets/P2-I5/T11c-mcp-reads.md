# P2-I5-T11c — MCP read tools: weeks, look-ahead, progress, KPIs

Status: ready after T09 merges (S2, S3, S4a, T03 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, read, confidentiality
Depends on: T09
Branch: `p2/i5-t11c-mcp-reads`
Worktree: harness-created under `/home/user/wt/i5/t11c` (from `p2/i5` head)

## Goal
Five read tools so an agent sees the same weekly state as the CLI and the API: `list_weekly_plans`, `get_weekly_plan`, `get_iwp_progress`, `get_progress_rollup`, `list_kpis`. Reads only; the proposals `propose_progress` and `propose_week_commitment` already exist (rows written by S2 and S4a, ADR-0027). The look-ahead needs a schedule snapshot and stays off MCP this increment (D29).

## Brief references (pasted)
- Pattern: `tl_mcp/iwp_tools.py` (module docstring, `register_iwp_tools`, `guarded(ctx, name, resource_name(...))`, `ctx.factory(True)`, `READ_ONLY`). Each tool reads as the lowest clearance (the context's viewer), so a hidden record answers as a missing one. Tools: `list_weekly_plans(project)` -> `list[WeekRow]` (`week_views.list_weeks(conn, scope, viewer, limit=60)`); `get_weekly_plan(project, week)` -> `WeekDetail` (week `YYYY-Www`; id from `list_weeks(limit=520)`; unknown or hidden: `RecordNotFoundError`, one text); `get_iwp_progress(project, number)` -> `IwpProgressBody` (a pydantic model declared in the tool file: `number, pct, edition, items[key, pct, steps, hours], notes`; from `iwp_views.iwp_detail` then `engine.earned_fraction(conn, id, viewer=...)`); `get_progress_rollup(project)` -> `RollupBody` (pydantic, `model_validate(dataclasses.asdict(progress_rollup(conn, scope, viewer=...)))`); `list_kpis(project)` -> `list[KpiTile]` (`kpis.kpi_rows`). The viewer is `confidentiality.current_viewer()` inside the factory unit of work, as `visible_readiness` is called in `iwp_tools.get_iwp_readiness_impl`.
- Actions: add the five `mcp.<tool>` names to a new `WEEK_MCP_ACTIONS` frozenset and OR it into `MCP_ACTIONS` in `identity.py` (a tool not listed is refused). Agent grants for core words stay deferred (D37): these are `awp` reads only.
- Closed list: add the five names to `READING` and `TOOLS` in `tests/test_mcp_server.py` (union form) and to the docs list if the gate names one.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/{iwp_tools.py (1-60, 135-200, 203-275), identity.py (15-40), server.py (140-155), errors.py (guarded, resource_name)}`
- `packages/tl-mcp/tests/test_mcp_server.py` (95-125), `packages/tl-mcp/tests/test_mcp_write_tools.py` (a read-tool test as the pattern)
- `packages/tl-modules/awp/src/tl_mod_awp/{week_views.py, kpis.py, progress/engine.py (395-416), progress/rollup.py (139-150)}`

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/awp_week_tools.py` (create), `identity.py` (the import and one OR), `server.py` (import and one `register_week_tools(server, ctx)` line)
- `packages/tl-mcp/tests/test_mcp_week_tools.py` (create), `packages/tl-mcp/tests/test_mcp_server.py` (the closed lists, union)
- `docs/reports/P2-I5/T11c.md`; consequential pins (union): `packages/tl-mcp/tests/` lists the gate names, `docs/reference/` tool list if one exists

## Acceptance
```
just check
just gate packages/tl-mcp/tests/test_mcp_week_tools.py packages/tl-mcp/tests/test_mcp_server.py packages/tl-mcp/tests/test_mcp_write_tools.py packages/tl-mcp/tests/test_confidentiality_walk.py
```

## Tests to add
`test_mcp_week_tools.py` (harness as `test_mcp_server.py`, a `WeekWorld` ledger): each tool returns the declared keys; `get_weekly_plan` of a hidden plan and of `2099-W01` raise the same text; a hidden IWP's commitment is absent from the detail with the note; `get_iwp_progress` of a hidden IWP is the unknown-IWP error; every tool name is in `MCP_ACTIONS`; an agent token refused for a tool outside the list.

## Escalation triggers
- A tool needs a core word (agent grants are deferred); `MCP_ACTIONS` is built another way than an OR of frozensets.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T11c: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
