"""Module tools are closed by the platform and never shadow a core tool (P2-X4 S6; SR-X4 F1, F2)."""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from tl_api.auth import Forbidden
from tl_core.modules import ModuleSpec, load_modules, use_modules
from tl_mcp.context import McpContext

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "ext_demo"))

from load import ext_demo_spec  # noqa: E402  # pyright: ignore[reportMissingImports]


def _fake(name: str, ref: str) -> ModuleSpec:
    return ModuleSpec(
        name=name, record_types=frozenset({f"{name}.Thing"}), projectors=list, tools=(ref,)
    )


@pytest.fixture
def fakes() -> Iterator[None]:
    """``tl_mcp.fake_a_tools`` (a tool that forgets ``guarded``, plus one named like a core tool)
    and ``tl_mcp.fake_b_tools`` (one clean tool)."""
    a = types.ModuleType("tl_mcp.fake_a_tools")
    b = types.ModuleType("tl_mcp.fake_b_tools")
    c = types.ModuleType("tl_mcp.fake_c_tools")
    d = types.ModuleType("tl_mcp.fake_d_tools")

    def register_a(server: MCPServer, ctx: McpContext) -> None:
        @server.tool()
        def fake_open() -> str:  # no ``guarded``: the platform must close it
            return "reached"

    def register_b(server: MCPServer, ctx: McpContext) -> None:
        @server.tool()
        def fake_clean() -> str:
            return "reached"

    def register_c(server: MCPServer, ctx: McpContext) -> None:
        @server.tool()
        def fake_before_clash() -> str:
            return "module"

        @server.tool(name="search_records")  # a core tool name
        def shadow() -> str:
            return "shadowed"

    def register_d(server: MCPServer, ctx: McpContext) -> None:
        @server.tool(name="fake_open")  # a name an earlier module has
        def second() -> str:
            return "second"

    e = types.ModuleType("tl_mcp.fake_e_tools")
    f = types.ModuleType("tl_mcp.fake_f_tools")

    def register_e(server: Any, ctx: McpContext) -> None:
        @server.tool()
        def fake_tool_first() -> str:
            return "x"

        @server.resource("tl://record/{scope}/fixed")
        def fake_resource() -> str:
            return "shadow"

    def register_f(server: Any, ctx: McpContext) -> None:
        @server.tool()
        async def fake_async() -> str:  # no ``guarded``; async
            return "async reached"

    e.register = register_e  # type: ignore[attr-defined]
    f.register = register_f  # type: ignore[attr-defined]
    a.register = register_a  # type: ignore[attr-defined]
    b.register = register_b  # type: ignore[attr-defined]
    c.register = register_c  # type: ignore[attr-defined]
    d.register = register_d  # type: ignore[attr-defined]
    mods = {
        "fake_e_tools": e,
        "fake_f_tools": f,
        "fake_a_tools": a,
        "fake_b_tools": b,
        "fake_c_tools": c,
        "fake_d_tools": d,
    }
    for key, mod in mods.items():
        sys.modules[f"tl_mcp.{key}"] = mod
    try:
        yield
    finally:
        for key in mods:
            del sys.modules[f"tl_mcp.{key}"]


def _names(env: McpHarness) -> set[str]:
    return {t.name for t in env.server._tool_manager.list_tools()}  # noqa: SLF001


def _core_names(tmp_path: Path) -> set[str]:
    (tmp_path / "core").mkdir()
    with use_modules([]):
        env = McpHarness.build(tmp_path / "core")
    try:
        return _names(env)
    finally:
        env.close()


def test_a_tool_that_forgets_guarded_is_closed_by_the_platform(tmp_path: Path, fakes: None) -> None:
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    with use_modules([_fake("cost", "tl_mcp.fake_a_tools:register")]):
        env = McpHarness.build(tmp_path, authorize_hook=authorizer)
    try:
        with pytest.raises(ToolError, match="not allowed"):
            env.call("fake_open")
        allowed.add("mcp.fake_open")
        assert env.structured("fake_open") == {"result": "reached"}
    finally:
        env.close()


def test_a_module_tool_named_like_a_core_tool_is_refused_and_the_core_tool_stays(
    tmp_path: Path, fakes: None, caplog: pytest.LogCaptureFixture
) -> None:
    core = _core_names(tmp_path)
    specs = [
        _fake("cost", "tl_mcp.fake_c_tools:register"),
        _fake("legacy", "tl_mcp.fake_b_tools:register"),
    ]
    (tmp_path / "with").mkdir()
    with caplog.at_level(logging.WARNING, logger="tl_mcp"), use_modules(specs):
        env = McpHarness.build(tmp_path / "with")
    try:
        names = _names(env)
        assert names == core | {"fake_clean"}  # none of the clashing module's tools
        by_name = {t.name: t for t in env.server._tool_manager.list_tools()}  # noqa: SLF001
        assert by_name["search_records"].fn.__name__ == "search_records"
    finally:
        env.close()
    messages = [r.getMessage() for r in caplog.records if r.name == "tl_mcp"]
    assert messages == ["module 'cost': hook 'tools' cannot be resolved"]


def test_a_tool_name_an_earlier_module_has_is_refused(
    tmp_path: Path, fakes: None, caplog: pytest.LogCaptureFixture
) -> None:
    specs = [
        _fake("cost", "tl_mcp.fake_a_tools:register"),
        _fake("legacy", "tl_mcp.fake_d_tools:register"),
    ]
    with caplog.at_level(logging.WARNING, logger="tl_mcp"), use_modules(specs):
        env = McpHarness.build(tmp_path)
    try:
        assert env.structured("fake_open") == {"result": "reached"}  # the first one stays
    finally:
        env.close()
    assert [r.getMessage() for r in caplog.records if r.name == "tl_mcp"] == [
        "module 'legacy': hook 'tools' cannot be resolved"
    ]


def _module_tools_denied(tmp_path: Path, specs: list[ModuleSpec]) -> None:
    """Every module tool refuses a caller the authorizer denies, before its body runs."""
    seen: list[str] = []

    def deny_all(actor: str, action: str, resource: str) -> None:
        seen.append(action)
        raise Forbidden("closed")

    core = _core_names(tmp_path)
    (tmp_path / "walk").mkdir()
    with use_modules(specs):
        env = McpHarness.build(tmp_path / "walk", authorize_hook=deny_all)
    try:
        tools = {t.name: t for t in env.server._tool_manager.list_tools()}  # noqa: SLF001
        module_tools = sorted(set(tools) - core)
        assert module_tools, "the walk found no module tool"
        for name in module_tools:
            seen.clear()
            # no arguments: the platform's guard runs before the module's function sees any
            with pytest.raises(ToolError, match="not allowed"):
                tools[name].fn()
            assert seen[0] == f"mcp.{name}"
    finally:
        env.close()


def test_every_installed_module_tool_refuses_a_deny_all_authorizer(tmp_path: Path) -> None:
    _module_tools_denied(tmp_path, list(load_modules()))


def test_every_ext_demo_tool_refuses_a_deny_all_authorizer(tmp_path: Path) -> None:
    _module_tools_denied(tmp_path, [*load_modules(), ext_demo_spec()])


def test_a_module_that_registers_a_resource_is_refused_whole(
    tmp_path: Path, fakes: None, caplog: pytest.LogCaptureFixture
) -> None:
    core = _core_names(tmp_path)
    (tmp_path / "with").mkdir()
    with (
        caplog.at_level(logging.WARNING, logger="tl_mcp"),
        use_modules([_fake("cost", "tl_mcp.fake_e_tools:register")]),
    ):
        env = McpHarness.build(tmp_path / "with")
    try:
        assert _names(env) == core  # not even its tool
        assert not any("fake" in str(r.uri) for r in asyncio.run(env.server.list_resources()))
    finally:
        env.close()
    assert [r.getMessage() for r in caplog.records if r.name == "tl_mcp"] == [
        "module 'cost': hook 'tools' cannot be resolved"
    ]


def test_an_async_module_tool_is_awaited_behind_the_guard(tmp_path: Path, fakes: None) -> None:
    allowed: set[str] = set()

    def authorizer(actor: str, action: str, resource: str) -> None:
        if action not in allowed:
            raise Forbidden("closed")

    with use_modules([_fake("cost", "tl_mcp.fake_f_tools:register")]):
        env = McpHarness.build(tmp_path, authorize_hook=authorizer)
    try:
        with pytest.raises(ToolError, match="not allowed"):
            env.call("fake_async")
        allowed.add("mcp.fake_async")
        assert env.structured("fake_async") == {"result": "async reached"}
    finally:
        env.close()
