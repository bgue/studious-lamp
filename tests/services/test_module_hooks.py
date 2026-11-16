"""P2-X4 S1: module-supplied command, route, tool and CLI hooks (lazy dotted references).

Provided by the supervisor; the piece copies it byte-identical to
``tests/services/test_module_hooks.py``.
"""

from __future__ import annotations

import subprocess
import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest
from tl_core.modules import (
    ModuleCommand,
    ModuleHookError,
    ModuleLoadError,
    ModuleSpec,
    hook_failures,
    load_modules,
    module_commands,
    resolve_hook,
    use_modules,
)
from tl_core.services.commands import Command

#: Installed modules that declare no API command (checked by name, so a new one fails here).
NO_COMMANDS = {"legacy"}


class Ping(Command):
    pass


class Pong(Command):
    pass


def _handler(uow: Any, command: Any) -> Any:
    raise AssertionError("never run")


def _fake(name: str, **hooks: Any) -> ModuleSpec:
    return ModuleSpec(
        name=name,
        record_types=frozenset({f"{name}.Thing"}),
        projectors=list,
        **hooks,
    )


@pytest.fixture
def fake_package() -> Iterator[None]:
    """Two importable packages: ``tl_mod_fake`` (Ping), ``tl_mod_other`` (Pong, Ping)."""
    fake = types.ModuleType("tl_mod_fake")
    fake.COMMANDS = (  # type: ignore[attr-defined]
        types.SimpleNamespace(model=Ping, handler=_handler, access="user"),
    )
    fake.PRIVATE = 1  # type: ignore[attr-defined]
    other = types.ModuleType("tl_mod_other")
    other.COMMANDS = (  # type: ignore[attr-defined]
        types.SimpleNamespace(model=Pong, handler=_handler, access="admin"),
    )
    other.CLASHES = (  # type: ignore[attr-defined]
        types.SimpleNamespace(model=Ping, handler=_handler, access="user"),
    )
    sys.modules["tl_mod_fake"] = fake
    sys.modules["tl_mod_other"] = other
    try:
        yield
    finally:
        sys.modules.pop("tl_mod_fake", None)
        sys.modules.pop("tl_mod_other", None)


def test_every_installed_module_declares_commands_that_resolve() -> None:
    declared = {spec.name for spec in load_modules() if spec.commands}
    assert declared == {spec.name for spec in load_modules()} - NO_COMMANDS
    assert hook_failures() == {}
    for spec in load_modules():
        for kind in ("commands", "read_routers", "tools", "cli_groups"):
            resolve_hook(spec, kind)  # raises ModuleHookError when a ref does not resolve


def test_hook_command_names_equal_the_api_table() -> None:
    from tl_api.commands import COMMANDS

    from_hooks: dict[str, set[str]] = {}
    for row in module_commands():
        from_hooks.setdefault(row.module, set()).add(row.name)
    in_table: dict[str, set[str]] = {}
    for spec in COMMANDS:
        if spec.module is not None:
            in_table.setdefault(spec.module, set()).add(spec.name)
    for module, names in in_table.items():
        assert from_hooks[module] == names, module
    # the one module the API table does not carry yet (S2 of this increment decides how it joins)
    assert set(from_hooks) - set(in_table) <= {"requisitions"}


def test_rows_keep_model_handler_access_and_an_empty_meta() -> None:
    by_name = {row.name: row for row in module_commands()}
    assert by_name["RaisePunchItem"].module == "quality"
    assert by_name["RegisterMnemonic"].access == "admin"
    for row in by_name.values():
        assert isinstance(row, ModuleCommand)
        assert callable(row.handler)
        assert dict(row.meta) == {}


def test_command_names_are_unique_across_modules(fake_package: None) -> None:
    clash = _fake("fake", commands="tl_mod_fake:COMMANDS")
    other = _fake("other", commands="tl_mod_other:CLASHES")
    with use_modules([clash, other]), pytest.raises(ModuleLoadError) as err:
        module_commands()
    assert str(err.value) == "command 'Ping' is declared by 'fake' and 'other'"
    ok = _fake("other", commands="tl_mod_other:COMMANDS")
    with use_modules([clash, ok]):
        assert [row.name for row in module_commands()] == ["Ping", "Pong"]


@pytest.mark.parametrize(
    "hooks",
    [
        {"commands": "os.path:join"},  # outside the module's package
        {"commands": "tl_mod_fakery:COMMANDS"},  # a package that merely starts with the name
        {"commands": "tl_mod_other:COMMANDS"},  # another module's package
        {"commands": "tl_mod_fake"},  # no object
        {"commands": "tl_mod_fake:"},
        {"commands": "tl_mod_fake:PRIVATE.x"},
        {"commands": "tl_mod_fake:_hidden"},
        {"commands": "tl_mod_fake:__class__"},
        {"tools": ("tl_api.routes.punch:router",)},  # a route surface is not a tool surface
        {"read_routers": ("tl_mcp.punch_tools:register_punch_tools",)},
        {"cli_groups": ("tl_api.routes.punch:router",)},
        {"read_routers": ("tl_api.routes.admin:router_x:y",)},
    ],
)
def test_a_ref_outside_its_surface_or_malformed_is_refused(hooks: dict[str, Any]) -> None:
    with pytest.raises(ModuleLoadError):
        _fake("fake", **hooks)


def test_in_tree_surface_refs_are_accepted() -> None:
    # an in-tree module (IN_TREE_SURFACES, orchestrator Q1) may name the surface packages
    _fake(
        "quality",
        read_routers=("tl_api.routes.punch:router",),
        tools=("tl_mcp.punch_tools:register_punch_tools",),
        cli_groups=("tl_cli.punch:app",),
    )


def test_a_missing_object_fails_that_module_only(fake_package: None) -> None:
    broken = _fake("other", commands="tl_mod_other:NOPE")
    good = _fake("fake", commands="tl_mod_fake:COMMANDS")
    with use_modules([good, broken]):
        assert [row.name for row in module_commands()] == ["Ping"]
        assert hook_failures() == {"other": "module 'other': hook 'commands' cannot be resolved"}
        with pytest.raises(ModuleHookError) as err:
            resolve_hook(broken, "commands")
        assert str(err.value) == "module 'other': hook 'commands' cannot be resolved"
        assert "NOPE" not in str(err.value)


def test_a_missing_package_fails_that_module_only(fake_package: None) -> None:
    broken = _fake("ghost", commands="tl_mod_ghost:COMMANDS")
    with use_modules([_fake("fake", commands="tl_mod_fake:COMMANDS"), broken]):
        assert [row.name for row in module_commands()] == ["Ping"]
        assert set(hook_failures()) == {"ghost"}


def test_the_core_imports_no_web_cli_or_mcp_code() -> None:
    code = (
        "import sys\n"
        "from tl_core.modules import load_modules, module_commands\n"
        "load_modules(); module_commands()\n"
        "bad = [m for m in ('fastapi', 'starlette', 'typer', 'mcp', 'tl_api', 'tl_mcp', 'tl_cli')"
        " if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-400:]
