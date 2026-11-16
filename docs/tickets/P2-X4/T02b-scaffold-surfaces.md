# P2-X4-T02b — `tl new module` emits an example read route, tool and CLI group

Status: ready (T02a merged at 479f41bb; S2, S3, T01, S4 merged)
Tier: haiku
review: full
Labels: cli, tests
Depends on: T02a merged
Branch: `p2/x4-t02b-scaffold-surfaces`
Worktree: `/home/user/wt/x4/t02b`

## Goal
The module that `tl new module` writes also declares one read route, one agent tool and one CLI group in its own package, through the `read_routers`, `tools` and
`cli_groups` hooks. All three answer a fixed text and read no record (no confidentiality exposure; the author replaces them). Refs sit inside the module's own
package: ADR-0029 and Q1 allow `tl_api.routes.`, `tl_mcp.` and `tl_cli.` refs only to the 11 in-tree modules (`IN_TREE_SURFACES`). No example command (D7).

## Brief references (pasted)
- D7: the scaffold carries no example command (an access-worded handler is core work); `ext_demo` (S5) is the worked command.
- Tool closure: a tool is refused for agents until an allow row names `mcp.<tool>`; the example ships closed. The route uses `guard("document.read")`, the read word agents hold.
- Group name rule (T01 `_group_name`): ref `<pkg>.cli:<x>_app` gives group `<x>`.

## Provided test (copy byte-identical; checked ruff format, ruff check, pyright at the target path; red until this ticket)
`docs/tickets/P2-X4/provided/test_new_module_surfaces.py` to `packages/tl-cli/tests/test_new_module_surfaces.py` (4 tests; do not edit).

## Interfaces (verbatim from the merged tree)
`scaffold/module.py` `plan_module` has `values = {"name", "package", "distribution"}`, `src = f"{base}/src/{module.package}"`, and lines like
`plan.add(f"{src}/commands.py", render("module/commands_hook.py.tmpl", **values))`. `ModuleSpec` fields: `read_routers: Sequence[str]`, `tools`, `cli_groups`.

## Steps
1. Create three templates in `packages/tl-cli/src/tl_cli/scaffold/templates/module/`, text exactly as below (rendered and checked with ruff format, ruff check and pyright for the names `inspection` and the 20-character `abcdefghijklmnopqrst`; do not re-wrap).

`routes.py.tmpl`
```
"""The example read route of the ${name} module (`tl new module`; ADR-0029).

It answers a fixed text and reads no record, so no confidentiality filter applies
yet. A route that returns record text reads through the viewer's class filter
(`tl_core.confidentiality`), and a hidden record answers as a missing one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from tl_api.auth import guard

from ${package} import MODULE

router = APIRouter(tags=["${name}"])


@router.get("/modules/${name}/ping")
def ping(_actor: Annotated[str, Depends(guard("document.read"))]) -> dict[str, str]:
    """The module name. `document.read` is the read word agents hold; the route is a read."""
    return {"module": MODULE}
```
`tools.py.tmpl`
```
"""The example agent tool of the ${name} module (`tl new module`; ADR-0029).

The tool is closed to agents until an allow row names the action
`mcp.${name}_ping`. It answers a fixed text and reads no record; a tool that
reads one runs under `guarded`, which sets the lowest clearance, so a hidden
record answers as a missing one.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from tl_mcp.context import McpContext
from tl_mcp.errors import guarded

from ${package} import MODULE

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


def register_tools(server: MCPServer, ctx: McpContext) -> None:
    @server.tool(name="${name}_ping", annotations=READ_ONLY)
    def ping() -> str:
        """The name of the ${name} module (fixed text; reads no record)."""
        with guarded(ctx, "${name}_ping", MODULE):
            return MODULE
```
`cli.py.tmpl`
```
"""The example CLI group of the ${name} module (`tl new module`; ADR-0029).

The hook ref `<package>.cli:${name}_app` names the group `${name}`.
An attribute `<x>_app` gives the group `<x>`.
"""

from __future__ import annotations

import typer

from ${package} import MODULE

${name}_app = typer.Typer(no_args_is_help=True)


@${name}_app.command()
def ping() -> None:
    """Print the module name."""
    typer.echo(MODULE)
```
2. `scaffold/module.py`: after the `commands.py` line add
```
    plan.add(f"{src}/routes.py", render("module/routes.py.tmpl", **values))
    plan.add(f"{src}/tools.py", render("module/tools.py.tmpl", **values))
    plan.add(f"{src}/cli.py", render("module/cli.py.tmpl", **values))
```
3. `module_spec.py.tmpl`: after the line `        commands="${package}.commands:COMMANDS",` add
```
        read_routers=("${package}.routes:router",),
        tools=("${package}.tools:register_tools",),
        cli_groups=("${package}.cli:${name}_app",),
```
4. `pyproject.toml.tmpl`: in `dependencies`, after `"tl-adapters",` add the lines `  "tl-api",`, `  "tl-mcp",`, `  "fastapi",`, `  "mcp",`, `  "typer",` (bare names, as `packages/tl-api`, `tl-mcp` and `tl-cli` pin them; add nothing else).
5. `test_module.py.tmpl`: replace the whole file with
```
"""The module package imports and its schema header names the module."""

from __future__ import annotations

from pathlib import Path

import ${package}
from tl_core.modules import resolve_hook
from ${package}.module import spec
from ${package}.routes import router

ROOT = Path(__file__).resolve().parents[4]


def test_the_package_names_its_module() -> None:
    assert ${package}.MODULE == "${name}"


def test_the_schema_header_names_the_module() -> None:
    header = ROOT / "schema" / "modules" / "${name}" / "module.yaml"
    assert "tl:module: ${name}" in header.read_text(encoding="utf-8")


def test_the_module_spec_names_the_module() -> None:
    assert spec().name == "${name}"


def test_each_surface_hook_resolves_to_one_object() -> None:
    for kind in ("read_routers", "tools", "cli_groups"):
        assert len(resolve_hook(spec(), kind)) == 1


def test_the_router_serves_the_one_ping_path() -> None:
    assert router.url_path_for("ping") == "/modules/${name}/ping"
```
6. Consequential pins (list in the report): `packages/tl-cli/tests/test_cli_new_module.py`: `EXPECTED` gains `.../src/tl_mod_inspection/cli.py`, `routes.py`, `tools.py` (sorted position); `3 passed` becomes `5 passed` in both places.
   `test_cli_new_record_type.py` and `test_cli_new_projector.py`: `5 passed` becomes `7 passed`.

## Allowed paths
- the three new templates, `module_spec.py.tmpl`, `pyproject.toml.tmpl`, `test_module.py.tmpl` (all under `packages/tl-cli/src/tl_cli/scaffold/templates/module/`)
- `packages/tl-cli/src/tl_cli/scaffold/module.py`
- `packages/tl-cli/tests/test_new_module_surfaces.py` (create, provided)
- consequential pins in `packages/tl-cli/tests/test_cli_new_module.py`, `test_cli_new_record_type.py`, `test_cli_new_projector.py`
- `docs/reports/P2-X4/T02b.md`

## Acceptance (two runs; one at a time)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-cli/tests/test_new_module_surfaces.py packages/tl-cli/tests/test_new_module_spec.py packages/tl-cli/tests/test_cli_new_module.py packages/tl-cli/tests/test_scaffold_engine.py packages/tl-cli/tests/test_module_cli_groups.py packages/tl-cli/tests/test_cli_new_record_type.py packages/tl-cli/tests/test_cli_new_projector.py
```
Name files, never directories. All green. A generated test that fails to import `tl_api` or `tl_mcp` is an environment fault: report it, do not add paths.
Report: first line deviations or none; the pin list; output lines of both commands (≤ 5 each). Commit `P2-X4-T02b: ...` with the session trailers; no model names in committed text.
