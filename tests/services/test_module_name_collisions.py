"""``module_commands(reserved)``: a module naming a core command is skipped whole (SR-X4 F1)."""

from __future__ import annotations

import logging
import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest
from tl_core.modules import ModuleSpec, hook_failures, module_commands, use_modules
from tl_core.services.commands import Command


class X6Core(Command):
    pass


class X6Mine(Command):
    pass


def _handler(uow: Any, command: Any) -> Any:
    raise AssertionError("never run")


def _spec(name: str) -> ModuleSpec:
    return ModuleSpec(
        name=name,
        record_types=frozenset({f"{name}.Thing"}),
        projectors=list,
        commands=f"tl_mod_{name}:COMMANDS",
        command_words={"X6Mine": "user"} if name == "x6two" else {"X6Core": "user"},
    )


@pytest.fixture
def packages() -> Iterator[None]:
    row = types.SimpleNamespace
    one, two = types.ModuleType("tl_mod_x6one"), types.ModuleType("tl_mod_x6two")
    one.COMMANDS = (row(model=X6Core, handler=_handler, access="user"),)  # type: ignore[attr-defined]
    two.COMMANDS = (row(model=X6Mine, handler=_handler, access="user"),)  # type: ignore[attr-defined]
    sys.modules["tl_mod_x6one"], sys.modules["tl_mod_x6two"] = one, two
    try:
        yield
    finally:
        del sys.modules["tl_mod_x6one"], sys.modules["tl_mod_x6two"]


def test_without_reserved_names_both_modules_serve(packages: None) -> None:
    with use_modules([_spec("x6one"), _spec("x6two")]):
        assert [c.name for c in module_commands()] == ["X6Core", "X6Mine"]


def test_a_reserved_name_skips_that_module_whole_with_one_fixed_warning(
    packages: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING), use_modules([_spec("x6one"), _spec("x6two")]):
        rows = module_commands({"X6Core"})
        failures = hook_failures({"X6Core"})
    assert [c.name for c in rows] == ["X6Mine"]
    assert failures == {"x6one": "module 'x6one': hook 'commands' cannot be resolved"}
    assert [r.getMessage() for r in caplog.records] == [failures["x6one"]]


def test_a_module_whose_command_words_name_a_core_command_never_enters_the_word_index() -> None:
    from tl_core.auth.module_roles import command_index
    from tl_core.services import settings as _settings  # noqa: F401  # ChangeSetting is core

    bad = ModuleSpec(
        name="x6bad",
        record_types=frozenset({"x6bad.Thing"}),
        projectors=list,
        command_words={"ChangeSetting": "admin", "X6Own": "user"},
    )
    good = ModuleSpec(
        name="x6good",
        record_types=frozenset({"x6good.Thing"}),
        projectors=list,
        command_words={"X6Mine": "user"},
    )
    with use_modules([bad, good]):
        index = command_index()
    assert "ChangeSetting" not in index and "X6Own" not in index  # refused whole
    assert index["X6Mine"][0] == "x6good"
