"""F1 (P2-X4 S1 review): a non-text hook ref is a ``ModuleLoadError``, not a ``TypeError``."""

from __future__ import annotations

from typing import Any

import pytest
from tl_core.modules import ModuleLoadError, ModuleSpec


def build(**hooks: Any) -> ModuleSpec:
    return ModuleSpec(
        name="x4refs", record_types=frozenset({"x4refs.Thing"}), projectors=list, **hooks
    )


@pytest.mark.parametrize(
    ("field", "value", "item"),
    [
        ("read_routers", (3,), "3"),
        ("tools", (None,), "None"),
        ("cli_groups", (b"x",), "b'x'"),
        ("read_routers", ("tl_mod_x4refs.routes:router", 3), "3"),
    ],
)
def test_a_non_text_ref_item_is_a_module_load_error_naming_module_and_field(
    field: str, value: tuple[Any, ...], item: str
) -> None:
    with pytest.raises(ModuleLoadError) as caught:
        build(**{field: value})
    message = str(caught.value)
    assert "x4refs" in message and field in message
    assert item not in message


def test_a_non_text_commands_ref_is_a_module_load_error_too() -> None:
    with pytest.raises(ModuleLoadError, match="x4refs.*commands"):
        build(commands=7)


def test_text_refs_still_build() -> None:
    spec = build(
        commands="tl_mod_x4refs:COMMANDS",
        read_routers=("tl_mod_x4refs.routes:router",),
        tools=("tl_mod_x4refs:register",),
        cli_groups=("tl_mod_x4refs.cli:x4refs_app",),
    )
    assert spec.tools == ("tl_mod_x4refs:register",)
