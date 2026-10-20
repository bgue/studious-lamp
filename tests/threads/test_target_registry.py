"""A module's dispatch target may replace a core placeholder, and nothing else."""

from __future__ import annotations

import pytest
from tl_core.threads.targets import TargetRegistry, core_targets, load_targets
from tl_core.threads.targets.raise_record import RaiseRecordTarget, RaiseRfiTarget


class ModuleRfi(RaiseRecordTarget):
    name = "rfi"
    placeholder = False


class ModuleRecord(RaiseRecordTarget):
    name = "record"


def registry() -> TargetRegistry:
    found = TargetRegistry()
    for target in core_targets():
        found.register(target)
    return found


def test_a_module_rfi_replaces_the_core_placeholder() -> None:
    found = registry()
    assert isinstance(found.get("raise", "rfi"), RaiseRfiTarget)
    module = ModuleRfi()
    found.register(module, module=True)
    assert found.get("raise", "rfi") is module


def test_nothing_else_is_replaced() -> None:
    found = registry()
    with pytest.raises(ValueError, match="two dispatch targets"):
        found.register(ModuleRfi())  # not from a module: a clash is an error
    with pytest.raises(ValueError, match="two dispatch targets"):
        found.register(ModuleRecord(), module=True)  # core `record` is not a placeholder
    with pytest.raises(ValueError, match="two dispatch targets"):
        found.register(core_targets()[0], module=True)  # nor are the other core targets


def test_the_default_registry_has_the_placeholder_only_for_rfi() -> None:
    found = load_targets(entry_points_group=None)
    placeholders = [
        key
        for key in found.names()
        if getattr(found.get(key[0], key[1]), "placeholder", False)  # type: ignore[arg-type]
    ]
    assert placeholders == [("raise", "rfi")]
