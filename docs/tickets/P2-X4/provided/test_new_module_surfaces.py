"""P2-X4 T02b: `tl new module` emits a read route, an agent tool and a CLI group.

Provided by the supervisor; the ticket copies it byte-identical to
``packages/tl-cli/tests/test_new_module_surfaces.py``.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from fastapi import APIRouter, FastAPI
from mcp.server.mcpserver import MCPServer
from scaffold_support import tl_new
from tl_cli.main import _add_module_groups, _group_name  # pyright: ignore[reportPrivateUsage]
from tl_core.modules import ModuleSpec, resolve_hook, use_modules
from typer.testing import CliRunner

PACKAGE = "tl_mod_inspection"


@pytest.fixture
def spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleSpec]:
    assert tl_new(tmp_path, "module", "inspection").exit_code == 0
    monkeypatch.syspath_prepend(str(tmp_path / "packages/tl-modules/inspection/src"))
    module = importlib.import_module(f"{PACKAGE}.module")
    yield module.spec()
    for name in [n for n in sys.modules if n == PACKAGE or n.startswith(PACKAGE + ".")]:
        del sys.modules[name]


def test_the_three_hooks_name_own_package_refs_and_resolve(spec: ModuleSpec) -> None:
    assert spec.read_routers == (f"{PACKAGE}.routes:router",)
    assert spec.tools == (f"{PACKAGE}.tools:register_tools",)
    assert spec.cli_groups == (f"{PACKAGE}.cli:inspection_app",)
    (router,) = resolve_hook(spec, "read_routers")
    assert isinstance(router, APIRouter)
    (register,) = resolve_hook(spec, "tools")
    assert callable(register)
    (group,) = resolve_hook(spec, "cli_groups")
    assert isinstance(group, typer.Typer)
    assert _group_name(spec.cli_groups[0]) == "inspection"


def test_the_route_serves_one_ping_path(spec: ModuleSpec) -> None:
    (router,) = resolve_hook(spec, "read_routers")
    api = FastAPI()
    api.include_router(router)  # type: ignore[arg-type]
    assert list(api.openapi()["paths"]) == ["/modules/inspection/ping"]


def test_the_registrar_adds_one_read_only_tool(spec: ModuleSpec) -> None:
    (register,) = resolve_hook(spec, "tools")
    server = MCPServer("probe")
    register(server, None)  # type: ignore[operator]
    tools = asyncio.run(server.list_tools())
    assert [tool.name for tool in tools] == ["inspection_ping"]
    assert tools[0].annotations is not None
    assert tools[0].annotations.read_only_hint is True


def test_the_cli_group_prints_the_module_name(spec: ModuleSpec) -> None:
    root = typer.Typer()
    root.command("other")(lambda: None)
    with use_modules([spec]):
        _add_module_groups(root, [spec])
    result = CliRunner().invoke(root, ["inspection", "ping"])
    assert result.exit_code == 0
    assert result.stdout == "inspection\n"
