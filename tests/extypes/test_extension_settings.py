"""The settings.yaml of a registered type reaches the settings registry (brief 31.1, 30).

Runs on each adapter (the ``world`` fixture uses ``new_db``).
"""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from pathlib import Path

import pytest
from extworld import LIFT, OBSERVATION, World
from tl_core.extypes import registry, settings_link
from tl_core.extypes.lock import write_lock
from tl_core.services.errors import UnknownSettingError
from tl_core.settings.registry import (
    definitions,
    get_definition,
    register_definitions,
    unregister_definitions,
)
from tl_core.settings.types import SettingDefinition
from tl_core.uow import UnitOfWork

KEY = "co.acme.lift_plan.max_load_tonnes"


def keys() -> set[str]:
    return {k for k in definitions() if k.startswith("co.acme.")}


def test_nothing_is_registered_before_a_type_is(world: World) -> None:
    assert keys() == set()
    with pytest.raises(UnknownSettingError):
        get_definition(KEY)


def test_sync_registers_the_keys_of_the_new_type_under_its_name(world: World) -> None:
    world.sync()
    assert keys() == {KEY}
    found = get_definition(KEY)
    assert found.owner == LIFT and found.default == 250 and found.type == "decimal"


def test_a_process_that_starts_later_finds_the_keys_when_it_attaches(world: World) -> None:
    world.sync()
    settings_link.forget_all()  # a fresh process: nothing registered yet
    assert keys() == set()
    world.source.refresh_settings()
    assert keys() == {KEY}


def test_editing_the_files_removes_the_keys_and_reverting_brings_them_back(world: World) -> None:
    world.sync()
    package = world.package()
    readme = package / "README.md"
    original = readme.read_bytes()
    readme.write_bytes(original + b"x")
    world.source.refresh_settings()
    assert keys() == set()
    readme.write_bytes(original)
    world.source.refresh_settings()
    assert keys() == {KEY}


def test_a_deprecated_type_keeps_its_keys(world: World) -> None:
    world.sync()
    registry.deprecate(
        world.factory, type_ref=f"{LIFT}@1.0.0", reason="old", actor="user:alice", source="test"
    )
    world.source.refresh_settings()
    assert keys() == {KEY}  # existing records stay; so do the values that tune them


def test_the_newest_version_defines_the_keys(world: World) -> None:
    world.sync()
    old = world.package()
    new = old.parent / "1.1.0"
    new.mkdir()
    for item in old.iterdir():
        if item.is_file() and item.name != "type.lock":
            (new / item.name).write_bytes(item.read_bytes())
        elif item.is_dir():
            (new / item.name).mkdir()
            for example in item.iterdir():
                (new / item.name / example.name).write_bytes(example.read_bytes())
    settings = (new / "settings.yaml").read_text()
    (new / "settings.yaml").write_text(
        settings.replace("default: 250", "default: 300").replace("since: 1.0.0", "since: 1.1.0")
    )
    write_lock(new)
    world.sync()
    assert get_definition(KEY).default == 300


def _clashing_package(world: World) -> Path:
    """SafetyObservation with a settings.yaml that repeats LiftPlan's key."""
    package = world.package(OBSERVATION)
    text = (
        (world.package() / "settings.yaml")
        .read_text()
        .replace("owner: co.acme.LiftPlan", f"owner: {OBSERVATION}")
    )
    (package / "settings.yaml").write_text(text)
    write_lock(package)
    return package


def test_sync_quarantines_a_package_that_repeats_another_types_key(world: World) -> None:
    _clashing_package(world)
    changed = world.sync()
    by_ref = {v.registration.type_ref: v for v in changed}
    assert by_ref[f"{LIFT}@1.0.0"].registration.status == "active"
    clashed = by_ref[f"{OBSERVATION}@1.0.0"]
    assert clashed.registration.status == "quarantined"
    with world.factory(readonly=True) as uow:
        report = [
            e for e in registry.list_quarantined(uow.conn()) if e.type_ref.startswith(OBSERVATION)
        ]
    issue = report[0].report[0]
    assert issue.kind == "settings" and issue.path == "settings.yaml"
    assert KEY in issue.detail and LIFT in issue.detail
    assert get_definition(KEY).owner == LIFT  # the first owner keeps the key


def test_a_clash_that_reaches_the_registry_is_logged_and_skipped(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    world.sync()
    settings_link.forget_all()
    squatter = SettingDefinition(
        key=KEY,
        type="decimal",
        default=1,
        description="Registered first by someone else.",
        scopes=["platform"],
        since="1.0.0",
        owner="co.acme.Squatter",
    )
    register_definitions([squatter], owner="co.acme.Squatter")
    try:
        with caplog.at_level(logging.WARNING, logger="tl_core.extypes"):
            world.source.refresh_settings()  # must not raise
        assert get_definition(KEY).owner == "co.acme.Squatter"
        assert any("settings not registered" in r.getMessage() for r in caplog.records)
    finally:
        unregister_definitions("co.acme.Squatter")


def test_an_unreadable_ledger_changes_nothing(world: World) -> None:
    world.sync()

    def broken(readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        raise RuntimeError("database is gone")

    settings_link.refresh_from_ledger(broken, world.source._loader.verify)  # pyright: ignore[reportPrivateUsage]
    assert keys() == {KEY}
