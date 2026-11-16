# P2-X4-T02b — `tl new module` emits an example read route, tool and CLI group

Status: staged (dispatch after T02a merged)
Tier: haiku
review: full
Labels: cli, tests
Depends on: T02a merged; S2, S3, T01 merged (C2)
Branch: `p2/x4-t02b-scaffold-surfaces`
Worktree: `/home/user/wt/x4/t02b`

## Goal
The module that `tl new module` writes also declares one read route, one agent tool and one CLI group in its own package, through the `read_routers`, `tools` and `cli_groups` hooks.
All three answer a fixed text and read no record (no confidentiality exposure yet; the author replaces them). Refs sit inside the module's own package (ADR-0029, Q1: only the 11 in-tree
modules may name `tl_api.routes.`, `tl_mcp.` or `tl_cli.`).

## Files to emit (templates under `templates/module/`; the supervisor pastes exact text in round 4 from the merged T02a and the S2/S3/T01 reports, so this section is the contract)
- `routes.py`: `router = APIRouter(tags=["${name}"])`; `GET /modules/${name}/ping` guarded by `guard("document.read")` (agents hold it: read only), returns `{"module": MODULE}`.
- `tools.py`: `register_tools(server: MCPServer, ctx: McpContext) -> None` registers read tool `${name}_ping` (`READ_ONLY`, wrapped with `guarded`, fixed text). Closed to agents until an allow row names `mcp.${name}_ping`.
- `cli.py`: `${name}_app = typer.Typer(help=...)` with command `ping` printing `MODULE`. Name rule: ref `${package}.cli:${name}_app` gives group `${name}` (T01 `_group_name`).
- `module_spec.py.tmpl` gains `read_routers=("${package}.routes:router",)`, `tools=("${package}.tools:register_tools",)`, `cli_groups=("${package}.cli:${name}_app",)`.
- `pyproject.toml.tmpl` gains dependencies the ticket names: `fastapi`, `typer`, `mcp`, `tl-api`, `tl-mcp` (check the pins in `packages/tl-modules/requisitions/pyproject.toml`; copy the specifier text, add nothing else).
- Generated `tests/test_module.py` gains tests: the three hooks resolve (`resolve_hook`), the router has the one path, the registrar is callable.
## Tests to add
`packages/tl-cli/tests/test_new_module_surfaces.py` (the ticket author writes it): scaffold, import, `resolve_hook` for the three kinds, the route path, the group name by `_group_name`,
and a `build_server`/`create_app` under `use_modules([spec])` that shows `/modules/<name>/ping` and tool `<name>_ping`; pin file lists in `test_cli_new_module.py` (consequential).
## Acceptance
```
just check
just gate packages/tl-cli/tests/test_new_module_surfaces.py packages/tl-cli/tests/test_new_module_spec.py packages/tl-cli/tests/test_cli_new_module.py packages/tl-cli/tests/test_scaffold_engine.py packages/tl-cli/tests/test_module_cli_groups.py
```
Allowed paths: the three new templates, `module_spec.py.tmpl`, `pyproject.toml.tmpl`, `test_module.py.tmpl`, `scaffold/module.py`, the new test, `docs/reports/P2-X4/T02b.md`; consequential pins in `test_cli_new_module.py`.
