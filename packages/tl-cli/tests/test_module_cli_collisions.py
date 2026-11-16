"""A module never shadows a core `tl` command; `tl new module` refuses such a name; the generated
module template is closed by the platform (P2-X4 S6; SR-X4 F1, F2, F3)."""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from scaffold_support import files_under, tl_new
from tl_api.app import create_app
from tl_api.auth import Forbidden
from tl_cli.main import _add_module_groups, app
from tl_core.modules import ModuleLoadError, ModuleSpec, use_modules
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[3]
for tests in ("tl-api", "tl-mcp"):  # the API and MCP harnesses build a real app and server
    sys.path.append(str(ROOT / "packages" / tests / "tests"))


def _spec(name: str, *refs: str) -> ModuleSpec:
    return ModuleSpec(
        name=name, record_types=frozenset({f"{name}.Thing"}), projectors=list, cli_groups=refs
    )


@pytest.fixture
def fakes() -> Iterator[None]:
    mods: list[str] = []

    def add(name: str, **groups: typer.Typer) -> None:
        mod = types.ModuleType(name)
        for key, group in groups.items():
            setattr(mod, key, group)
        sys.modules[name] = mod
        mods.append(name)

    def group(text: str) -> typer.Typer:
        grp = typer.Typer()
        grp.command("say")(lambda: typer.echo(text))
        return grp

    add("tl_mod_x6g1", record_app=group("shadow"), fine_app=group("fine"))
    add("tl_mod_x6g2", serve_app=group("shadow"))  # a root command, not a group
    add("tl_mod_x6g3", x6g3_app=group("one"))
    add("tl_mod_x6g4", x6g3_app=group("two"))
    try:
        yield
    finally:
        for name in mods:
            del sys.modules[name]


@pytest.mark.parametrize(
    ("module", "refs"),
    [
        ("x6g1", ("tl_mod_x6g1:record_app", "tl_mod_x6g1:fine_app")),
        ("x6g2", ("tl_mod_x6g2:serve_app",)),
    ],
)
def test_a_module_group_named_like_a_core_command_is_refused_whole(
    fakes: None, module: str, refs: tuple[str, ...], caplog: pytest.LogCaptureFixture
) -> None:
    root = typer.Typer()
    root.add_typer(typer.Typer(), name="record")
    root.command("serve")(lambda: typer.echo("core serve"))
    with caplog.at_level(logging.WARNING, logger="tl_cli"):
        _add_module_groups(root, [_spec(module, *refs)])
    names = [info.name for info in root.registered_groups]
    assert names == ["record"]  # neither the clashing group nor the module's other group
    assert CliRunner().invoke(root, ["serve"]).stdout == "core serve\n"
    assert [r.getMessage() for r in caplog.records if r.name == "tl_cli"] == [
        f"module '{module}': hook 'cli_groups' cannot be resolved"
    ]


def test_a_group_name_an_earlier_module_has_is_refused(fakes: None) -> None:
    root = typer.Typer()
    _add_module_groups(
        root, [_spec("x6g3", "tl_mod_x6g3:x6g3_app"), _spec("x6g4", "tl_mod_x6g4:x6g3_app")]
    )
    assert [info.name for info in root.registered_groups] == ["x6g3"]
    assert CliRunner().invoke(root, ["x6g3", "say"]).stdout == "one\n"


def test_the_real_root_keeps_every_core_group_when_a_module_names_one(fakes: None) -> None:
    before = {info.name: info.typer_instance for info in app.registered_groups}
    _add_module_groups(app, [_spec("x6g1", "tl_mod_x6g1:record_app")])
    after = {info.name: info.typer_instance for info in app.registered_groups}
    assert after == before


@pytest.mark.parametrize(
    "ref", ["tl_mod_x6bad.cli:main", "tl_mod_x6bad.cli:apps", "tl_mod_x6bad.cli:x"]
)
def test_a_cli_group_ref_with_no_group_attribute_is_a_load_error_that_does_not_echo_it(
    ref: str,
) -> None:
    with pytest.raises(ModuleLoadError) as caught:
        _spec("x6bad", ref)
    assert str(caught.value) == "module 'x6bad': cli_groups names no group attribute"


@pytest.mark.parametrize("name", ["record", "serve", "admin", "new"])
def test_tl_new_module_refuses_a_name_that_is_a_core_command_or_group(
    tmp_path: Path, name: str
) -> None:
    result = tl_new(tmp_path, "module", name)
    assert result.exit_code == 1
    assert "choose another name" in result.stderr
    assert files_under(tmp_path) == []


# --- the generated module template, closed by the platform (F2) ---------------------------


@pytest.fixture
def template_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleSpec]:
    assert tl_new(tmp_path, "module", "inspection").exit_code == 0
    monkeypatch.syspath_prepend(str(tmp_path / "packages/tl-modules/inspection/src"))
    module = importlib.import_module("tl_mod_inspection.module")
    yield module.spec()
    for name in [n for n in sys.modules if n.startswith("tl_mod_inspection")]:
        del sys.modules[name]


def test_the_generated_tool_is_denied_by_a_deny_all_authorizer(
    template_spec: ModuleSpec, tmp_path: Path
) -> None:
    from mcp_harness import McpHarness  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

    def deny_all(actor: str, action: str, resource: str) -> None:
        raise Forbidden("closed")

    (tmp_path / "mcp").mkdir()
    with use_modules([template_spec]):
        env = McpHarness.build(tmp_path / "mcp", authorize_hook=deny_all)
    try:
        tools = {t.name: t for t in env.server._tool_manager.list_tools()}  # noqa: SLF001
        assert "inspection_ping" in tools
        with pytest.raises(ToolError, match="not allowed"):
            tools["inspection_ping"].fn()
        with pytest.raises(ToolError, match="not allowed"):
            asyncio.run(env.server.call_tool("inspection_ping", {}))
    finally:
        env.close()


def test_the_generated_route_is_denied_by_a_deny_all_authorizer(
    template_spec: ModuleSpec, tmp_path: Path
) -> None:
    from harness import Harness  # pyright: ignore[reportMissingImports]
    from tl_api.tokens import TokenStore

    def deny_all(actor: str, action: str, resource: str) -> None:
        raise Forbidden("closed")

    h = Harness.build(tmp_path)
    try:
        with use_modules([template_spec]):
            api = create_app(
                h.backend,
                settings=h.settings,
                tokens=TokenStore(h.settings.tokens_path),
                authorize_hook=deny_all,
            )
        assert any(
            isinstance(r, APIRoute) and r.path == "/modules/inspection/ping" for r in _all(api)
        )
        client = TestClient(api, raise_server_exceptions=False)
        client.headers.update(h.headers())
        assert client.get("/modules/inspection/ping").status_code == 403
        client.close()
    finally:
        h.close()


def _all(api: object) -> list[object]:
    found: list[object] = []

    def walk(routes: object) -> None:
        for route in routes:  # type: ignore[attr-defined]
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(inner.routes)
            else:
                found.append(route)

    walk(api.routes)  # type: ignore[attr-defined]
    return found
