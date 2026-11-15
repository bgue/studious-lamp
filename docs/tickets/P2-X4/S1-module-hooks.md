# P2-X4 S1 — ModuleSpec hooks as lazy references; ModuleCommand; load checks; unique names

kind: piece
review: full
branch: p2/x4-s1-hooks
worktree: /home/user/wt/x4/s1
Depends on: ADR-0029 on trunk, I6 T03 on trunk. Gated: core interface (APPROVALS line before merge).

## Why
`tl_api/commands.py:101-110,172-232` imports each module's command table by name, `tl_api/app.py:325-349` lists routers by hand,
`tl_mcp/server.py:38-53,140-151` lists tool registrars, `tl_cli/main.py:136-200` lists groups. `ModuleSpec` (`tl_core/modules.py`)
holds none of them. ADR-0029 decisions 1 and 7: a policy names a command, so names must be unique across modules, and each command
can carry `meta["delegation"]` (`eligible | excluded:<reason>`, missing means excluded).

## Facts the plan did not have (checked 2026-11-15)
- 11 modules are installed, not 8: awp, correspondence, cost, documents, engineering, legacy, materials, quality, requisitions, schedule,
  schemareg. `legacy` has no commands (`module.py`: `command_words={}`). Declare hooks for every module that has the surface.
- `CommandSpec` lives in `tl_api.commands` (it has `module=`, `needs_holds`, `takes_roles`); `tl-core` cannot import it. Each module has
  its own row type (`ApiCommand`, `AwpCommand`, `PunchCommand`, `RequisitionCommand`, materials `CommandSpec`), all with `model`,
  `handler`, `access`. So S1 adds a core row `ModuleCommand`; S2 maps it onto `CommandSpec`.
- Routers, tool registrars and CLI apps of the in-tree modules live in `tl_api.routes.*`, `tl_mcp.*_tools`, `tl_cli.*`, not in the
  module packages (modules depend on `tl-core` only). See STATE Q1 for the ref rule used below.
- Requisitions commands are in `REQUISITIONS_COMMANDS` (`tl_mod_requisitions/module.py:77`) but not in `tl_api.COMMANDS`; punch is.
  S1 declares the hook for requisitions; S2 decides how its rows join the API (STATE Q2).
- Command rows that are not module-owned (`CreateRecord`, rules, links, constraints, ...) stay in `tl_api.commands` and are untouched.

## Goal
In `packages/tl-core/src/tl_core/modules.py` (no import of fastapi, starlette, typer, mcp, tl_api, tl_mcp, tl_cli):
1. `@dataclass(frozen=True) class ModuleCommand`: `module: str`, `model: type[Command]`, `handler`, `access: str`,
   `needs_holds: bool = False`, `takes_roles: bool = False`, `meta: Mapping[str, str]` (empty by default), property `name`
   (`model.__name__`). Handlers keep their present signature `(UnitOfWork, Any) -> CommandResult`.
2. New `ModuleSpec` fields, all defaulting to nothing: `commands: str | None`, `read_routers: Sequence[str] = ()`,
   `tools: Sequence[str] = ()`, `cli_groups: Sequence[str] = ()`. A ref is `"<dotted.module>:<Name>"`; `commands` names a tuple or a
   zero-argument callable returning one, of rows with `model`, `handler`, `access` (and optional `needs_holds`, `takes_roles`,
   `meta`). Order of a sequence is the registration order (some routers must precede others, see `app.py` comments).
3. `__post_init__` checks, raising `ModuleLoadError` with no echo of the offending text beyond the field name: ref shape
   (`^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*:[A-Za-z][A-Za-z0-9_]*$`, so no private or dotted object names); then the prefix rule:
   `commands` and every ref must sit in `tl_mod_<name>` or `tl_mod_<name>.…` (a sibling like `tl_mod_<name>x` is refused); in
   addition, and only until STATE Q1 changes it, `read_routers` may sit under `tl_api.routes.`, `tools` under `tl_mcp.`,
   `cli_groups` under `tl_cli.`. Implement the rule in one function `_check_ref(name, kind, ref)` so a different rule is a one-function change.
4. `resolve_hook(spec, kind) -> tuple[object, ...]`: imports each ref (`importlib`, lazily, never at `ModuleSpec` build) and returns the
   objects; any import or attribute failure raises `ModuleHookError(ModuleLoadError)` with exactly
   `module 'x': hook 'commands' cannot be resolved` (no exception text, no ref). For `commands`, rows become `ModuleCommand` (module =
   spec name, `meta` taken from the row when it has one, else `{}`); a row without `model`, `handler`, `access` fails the same way.
5. `module_commands() -> tuple[ModuleCommand, ...]` over `load_modules()` in module-name order, rows in declared order. A module whose
   `commands` hook fails is skipped and recorded; `hook_failures() -> dict[str, str]` returns module name to that fixed message
   (recomputed per call or cached on the identity of the `load_modules()` tuple; `use_modules` must not leak a cache). Two modules
   declaring one command name raise `ModuleLoadError("command 'Ping' is declared by 'fake' and 'other'")` (names sorted), never skipped:
   an ambiguous name must stop the process. The same name twice inside one module is the same error.
6. Declare the hooks in each module's `module.py` `spec()` (strings only; no new import at module load). Take each ref list from the hand
   lists now in `app.py`, `server.py` and `main.py` for that module, in their order. Do not edit those three files.
   Commands: awp `tl_mod_awp.commands:AWP_COMMANDS`, correspondence/cost/documents/engineering/schedule/schemareg
   `tl_mod_<m>.commands:API_COMMANDS`, materials `tl_mod_materials.commands:MATERIALS_COMMANDS`, quality
   `tl_mod_quality.module:PUNCH_COMMANDS`, requisitions `tl_mod_requisitions.module:REQUISITIONS_COMMANDS`; legacy none.

## Allowed paths
- `packages/tl-core/src/tl_core/modules.py`
- `packages/tl-modules/<m>/src/tl_mod_<m>/module.py` for the 11 modules (spec() fields only)
- `tests/services/test_module_hooks.py` (create: byte-identical copy of `docs/tickets/P2-X4/provided/test_module_hooks.py`)
- `docs/reports/P2-X4/S1.md` (create)
Read-only, do not touch: `tl_api/*`, `tl_mcp/*`, `tl_cli/*`, `tl_core/services/agent_scope.py`, `tl_core/services/proposals.py`,
`tl_api/errors.py` (P2-X2 is rewriting them on `p2/x2`; if a change seems to need one, stop and report).

## Tests to add
`tests/services/test_module_hooks.py` is provided (9 tests, red until this piece): every installed module declares what it has and all refs
resolve; hook command names equal the `tl_api.COMMANDS` rows per module (requisitions excepted); rows keep access and an empty `meta`;
a name clash is refused with the fixed text; malformed, out-of-package and wrong-surface refs are refused; in-tree surface refs pass; a
missing object or package fails that module only with the fixed text; `tl_core` imports no web, CLI or MCP code. Add nothing else unless a
guard below has no test; if you add one, put it in the same file's sibling `tests/services/test_module_hooks_extra.py`.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); `just gate tests/services/test_module_hooks.py tests/services/test_modules.py tests/services/test_modules_offline.py tests/services/test_module_role_seams.py tests/services/test_module_guards.py packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_api_module_roles.py packages/tl-modules/correspondence/tests/test_module.py packages/tl-modules/cost/tests/test_module.py packages/tl-modules/documents/tests/test_module.py packages/tl-modules/engineering/tests/test_module.py packages/tl-modules/schedule/tests/test_module.py packages/tl-modules/quality/tests/test_module_spec.py packages/tl-modules/requisitions/tests/test_module_spec.py`.
Name files, not directories (tl-api whole directory OOMs). No `gate-pg`: no adapter or ledger change.

## Mutation cap
One sentinel plus at most 5 targeted mutants: prefix check accepts a sibling package; name-clash check removed; hook failure raises
instead of being recorded; `_check_ref` allows `tools` under `tl_api.routes.`; `meta` default made shared and mutable. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; first line: deviations or none; list the ref table per module. Commit
`P2-X4-S1: ...` with the session trailers; no model names in committed text.
