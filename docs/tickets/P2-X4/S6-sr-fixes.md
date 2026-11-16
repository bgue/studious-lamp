# P2-X4 S6 — SR-X4 security fixes: no shadowing of core names (F1), module tools and routes closed by the platform (F2), CLI ref shape (F3)

kind: piece
review: full (security)
branch: p2/x4-s6-sr-fixes
worktree: /home/user/wt/x4/s6
Depends on: S1-S5 and T01, T02b merged (`p2/x4` @58cf3bcc). F4 (LO, `IN_TREE_SURFACES` trusts the module name) is deferred by the orchestrator.

## Why
- F1 (MD): nothing compares module-supplied names with core names. A module command named like a core one replaces its row in
  `TableCommandRunner` (handler, access, `AGENT_DIRECT_COMMANDS` keyed by name); a module tool registered before the core one wins
  (`add_tool` keeps the first); a module CLI group named like a core one wins (Typer last-wins; `tl new module record` emits one); a module
  router mounted before a core router takes the URL.
- F2 (MD): module tools and routes are closed only if each registrar remembers `guarded` / `Depends(guard(...))`. The platform wraps nothing.
- F3 (LO): `_group_name` raises a bare `ValueError` for a `cli_groups` ref whose attribute is not `app` or `<x>_app`.

## Allowed paths
`packages/tl-core/src/tl_core/modules.py`, `packages/tl-api/src/tl_api/{app,commands}.py`, `packages/tl-mcp/src/tl_mcp/server.py`,
`packages/tl-cli/src/tl_cli/{main,new}.py`; tests: the existing module-hook tests of each package (fixtures that lacked a guard get one),
new `tests/services/test_module_name_collisions.py`, `packages/tl-api/tests/test_module_collisions_api.py`,
`packages/tl-mcp/tests/test_module_tool_closure.py`, `packages/tl-cli/tests/test_module_cli_collisions.py`;
`docs/tickets/P2-X4/S6-sr-fixes.md`, `docs/reports/P2-X4/S6.md`. Nothing under `schema/**`.

## Interfaces
- `tl_core.modules.refused_hook(spec, kind) -> ModuleHookError` (the fixed text `module 'x': hook 'k' cannot be resolved`; no ref, no name echoed).
- `module_commands(reserved: Collection[str] = ())` and `hook_failures(reserved=())`: a module declaring a `reserved` name is skipped whole.
- `tl_api.commands`: core rows are built first (`_CORE_COMMANDS`); module rows come from `module_commands(core names)`.
- MCP: module registrars get a staging server; `_register_module_tools` runs after every core tool, refuses a module whose staged tool names
  hit a core tool, an earlier module or itself, and registers each function behind `guarded(ctx, <tool>, ...)`.
- API: `_include_module_routers(app, core_paths)` refuses a module with a route path (parameter names erased) equal to a core one or an
  earlier module's, or with a route that is not an `APIRoute` carrying a `guard(...)` dependency (`dependency.action`).
- CLI: `_add_module_groups` runs last in `main.py` and refuses a group name already a root command or group; `tl new module NAME` refuses a
  NAME that is a root command or group. `_check_ref` refuses a `cli_groups` attribute that is not `app` / `<x>_app` (`ModuleLoadError`,
  fixed text, no ref).

## Tests
Per surface with a fake module (command, tool, CLI group, route path): the module is skipped with the fixed warning and the core row, tool,
group and route still answer as before; the other modules still load. F2: a registrar that forgets `guarded` is denied under a deny-all
authorizer; a walk calls every module tool and route (installed modules, ext_demo, the generated template) under deny-all and expects a
refusal. A route without a guard is refused at mount. F3: bad attribute is a `ModuleLoadError`, no ref echoed. `tl new module record` fails.

## Gates
`just check`; `just gate` on the existing module-hook tests of each package plus the four new files; no `schema/**`; one pytest at a time.

## Sec row
SR-X4 F1 MD, F2 MD, F3 LO: closed by this piece, proved by the collision and deny-all walk tests; mutants: each collision check removed,
the tool wrapper skipped. Not touched: authorization tables (`MCP_ACTIONS`, access words), ledger, events.
