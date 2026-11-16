"""The confidentiality walk enumerates a module added through ``use_modules`` (P2-X4 S4, test 9).

A module that is not one of the installed ones brings one read tool. The walk lists it with the
other read tools, its own test fails on a tool whose required argument it cannot fill, and passes
a tool it can fill.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp_harness import McpHarness
from tl_core.modules import ModuleSpec, load_modules, use_modules
from tl_mcp.server import READ_ONLY, build_server


def _load_walk() -> Any:
    """The sibling walk, loaded by path: the tl-api tests have a file of the same name."""
    path = Path(__file__).with_name("test_confidentiality_walk.py")
    found = importlib.util.spec_from_file_location("mcp_confidentiality_walk", path)
    assert found is not None and found.loader is not None
    module = importlib.util.module_from_spec(found)
    sys.modules["mcp_confidentiality_walk"] = module
    found.loader.exec_module(module)
    return module


walk = _load_walk()
world = walk.world  # the walk's own fixture


def _registrar(tool: Callable[..., dict[str, str]]) -> Callable[[MCPServer, Any], None]:
    def register(server: MCPServer, ctx: Any) -> None:
        server.tool(annotations=READ_ONLY)(tool)

    return register


@pytest.fixture
def fake_package() -> Iterator[None]:
    package = types.ModuleType("tl_mod_x4walk")

    def x4walk_mystery(mystery: str) -> dict[str, str]:  # no value for this argument in the walk
        return {"ok": mystery}

    def x4walk_keyed(key: str) -> dict[str, str]:
        return {"ok": key}

    package.UNFILLABLE = _registrar(x4walk_mystery)  # type: ignore[attr-defined]
    package.FILLABLE = _registrar(x4walk_keyed)  # type: ignore[attr-defined]
    sys.modules["tl_mod_x4walk"] = package
    try:
        yield
    finally:
        sys.modules.pop("tl_mod_x4walk", None)


def spec_with(registrar: str) -> ModuleSpec:
    return ModuleSpec(
        name="x4walk",
        record_types=frozenset({"x4walk.Thing"}),
        projectors=list,
        tools=(f"tl_mod_x4walk:{registrar}",),
    )


def read_tool_names(env: McpHarness, tmp_path: Path) -> set[str]:
    server = build_server(env.factory, actor="user:bob", lake_dir=tmp_path / "lake")
    return {
        t.name
        for t in asyncio.run(server.list_tools())
        if t.annotations is not None and t.annotations.read_only_hint
    }


def test_the_walk_lists_an_added_tool_and_fails_on_one_it_cannot_fill(
    world: tuple[McpHarness, Any, Any],  # noqa: F811
    tmp_path: Path,
    fake_package: None,
) -> None:
    env = world[0]
    with use_modules([*load_modules(), spec_with("UNFILLABLE")]):
        assert "x4walk_mystery" in read_tool_names(env, tmp_path)
        with pytest.raises(AssertionError, match="add values for the argument 'mystery'"):
            walk.test_no_read_tool_shows_what_the_actor_may_not_read(world, "user:bob", tmp_path)


def test_the_walk_lists_an_added_tool_it_can_fill_and_passes_it(
    world: tuple[McpHarness, Any, Any],  # noqa: F811
    tmp_path: Path,
    fake_package: None,
) -> None:
    env = world[0]
    with use_modules([*load_modules(), spec_with("FILLABLE")]):
        names = read_tool_names(env, tmp_path)
        assert "x4walk_keyed" in names and "x4walk_mystery" not in names
        walk.test_no_read_tool_shows_what_the_actor_may_not_read(world, "user:bob", tmp_path)
