"""P2-X4 S1: the in-tree surface rule (orchestrator decision Q1) and two guards."""

from __future__ import annotations

import pytest
from tl_core.modules import ModuleCommand, ModuleLoadError, ModuleSpec
from tl_core.services.commands import Command


def _spec(name: str, **hooks: object) -> ModuleSpec:
    return ModuleSpec(
        name=name,
        record_types=frozenset({f"{name}.Thing"}),
        projectors=list,
        **hooks,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "hooks",
    [
        {"read_routers": ("tl_api.routes.punch:router",)},
        {"tools": ("tl_mcp.punch_tools:register_punch_tools",)},
        {"cli_groups": ("tl_cli.punch:app",)},
    ],
)
def test_a_module_outside_the_in_tree_set_may_not_name_a_surface(hooks: dict[str, object]) -> None:
    with pytest.raises(ModuleLoadError) as err:
        _spec("stranger", **hooks)
    assert "punch" not in str(err.value)
    assert "stranger" in str(err.value)


def test_an_in_tree_module_may_name_its_surface() -> None:
    _spec("quality", read_routers=("tl_api.routes.punch:router",))


def test_meta_default_is_not_shared() -> None:
    class Cmd(Command):
        pass

    a = ModuleCommand(module="m", model=Cmd, handler=lambda u, c: None, access="user")  # type: ignore[arg-type,return-value]
    b = ModuleCommand(module="m", model=Cmd, handler=lambda u, c: None, access="user")  # type: ignore[arg-type,return-value]
    assert a.meta is not b.meta
