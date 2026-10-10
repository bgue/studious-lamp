"""Export and import of a layer's settings as YAML (brief 30.4)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import yaml
from settings_world import ALICE, P1, SRC, World
from tl_adapters.db import DbTarget, open_uow
from tl_core import settings as S
from tl_core.services.errors import (
    InvalidSettingValueError,
    ReasonRequiredError,
    SettingLockedError,
    SettingScopeError,
    SettingsDocumentError,
    UnknownSettingError,
)


def export(world: World, layer: str) -> str:
    with open_uow(world.db, readonly=True) as uow:
        return S.export_yaml(uow.conn(), layer=layer)


def do_import(world: World, text: str, layer: str, **kw: object) -> list[object]:
    with open_uow(world.db) as uow:
        return list(S.import_yaml(uow, text, layer=layer, actor=ALICE, source=SRC, **kw))  # type: ignore[arg-type]


def test_an_export_lists_what_the_layer_holds_and_nothing_inherited(world: World) -> None:
    world.set("t.limit", "company", 20)
    world.set("t.plain", P1, "mine")
    document = yaml.safe_load(export(world, P1))
    assert document == {"version": 1, "layer": P1, "settings": {"t.plain": "mine"}}
    company = yaml.safe_load(export(world, "company"))
    assert company["settings"] == {"t.limit": 20} and "locks" not in company


def test_the_company_export_carries_locks_and_bounds(world: World) -> None:
    world.lock("t.limit")
    world.lock("t.plain", locked=False, bounds=None)
    world.lock("project.mode", locked=False, bounds={"choices": ["live"]})
    document = yaml.safe_load(export(world, "company"))
    assert document["locks"] == {
        "t.limit": {"locked": True, "bounds": None},
        "project.mode": {"locked": False, "bounds": {"choices": ["live"]}},
    }


def test_an_export_is_the_same_text_every_time_and_skips_resets_and_scheduled(
    world: World,
) -> None:
    from settings_world import future

    world.set("t.limit", P1, 5)
    world.set("t.plain", P1, "x")
    world.reset("t.plain", P1)
    world.set("t.every", "company", "10s", applies_at=future())
    assert export(world, P1) == export(world, P1)
    assert yaml.safe_load(export(world, P1))["settings"] == {"t.limit": 5}
    assert yaml.safe_load(export(world, "company"))["settings"] == {}


def test_importing_an_export_back_changes_nothing(world: World) -> None:
    world.set("t.limit", P1, 5)
    world.set("t.plain", P1, "x")
    text = export(world, P1)
    head = world.head()
    applied = do_import(world, text, P1)
    assert len(applied) == 2 and world.head() == head


def test_an_export_is_a_template_for_another_project(world: World) -> None:
    world.set("t.limit", P1, 5)
    world.set("t.plain", P1, "x")
    do_import(world, export(world, P1), "project:P2")
    assert world.value("t.limit", project="P2") == 5
    assert world.value("t.plain", project="P2") == "x"
    assert [e.scope for e in world.events()[-2:]] == ["project:P2", "project:P2"]
    assert [e.actor for e in world.events()] == [ALICE] * 4


def test_the_company_locks_travel_with_the_company_file(
    world: World, new_db: Callable[[], DbTarget]
) -> None:
    world.set("t.limit", "company", 20)
    world.lock("t.limit")
    text = export(world, "company")
    other = World(new_db())
    do_import(other, text, "company", reason="template")
    assert other.get("t.limit").locked is True and other.value("t.limit") == 20


def test_one_refused_key_refuses_the_whole_file(world: World) -> None:
    text = yaml.safe_dump({"settings": {"t.limit": 5, "t.plain": "x", "t.every": "1s"}})
    with pytest.raises(InvalidSettingValueError, match="t.every"):
        do_import(world, text, "company")
    assert world.head() == 0 and world.rows("cur_setting") == []


def test_a_locked_key_refuses_a_project_import_and_keeps_none_of_it(world: World) -> None:
    world.lock("t.limit")
    text = yaml.safe_dump({"settings": {"t.plain": "y", "t.limit": 5}})
    with pytest.raises(SettingLockedError):
        do_import(world, text, P1)
    assert world.head() == 1  # only the lock event
    assert world.value("t.plain", project="P1") == "x"


def test_advanced_keys_take_the_reason_of_the_import(world: World) -> None:
    text = yaml.safe_dump({"settings": {"t.advanced": "b", "t.limit": 3}})
    with pytest.raises(ReasonRequiredError):
        do_import(world, text, "company")
    do_import(world, text, "company", reason="template v2")
    assert world.value("t.advanced") == "b"
    assert {e.payload["reason"] for e in world.events()} == {"template v2"}


def test_locks_can_only_be_imported_into_the_company(world: World) -> None:
    text = yaml.safe_dump({"locks": {"t.limit": {"locked": True, "bounds": None}}})
    with pytest.raises(SettingsDocumentError, match="company layer"):
        do_import(world, text, P1, reason="r")
    applied = do_import(world, text, "company", reason="r")
    assert len(applied) == 1 and world.get("t.limit").locked is True


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("settings: [", "not valid YAML"),
        ("- a\n- b", "must be a mapping"),
        ("version: 2\nsettings: {}", "unsupported"),
        ("stuff: 1", "unknown top-level"),
        ("settings: [1, 2]", "`settings:` must be a mapping"),
        ("locks: 3", "`locks:` must be a mapping"),
        ("locks: {t.limit: 5}", "must be a mapping with"),
        ("locks: {t.limit: {locked: true, extra: 1}}", "must be a mapping with"),
        ("x: " + "y" * 270_000, "longer than"),
    ],
)
def test_a_file_that_is_not_a_settings_document_is_refused(
    world: World, text: str, message: str
) -> None:
    with pytest.raises(SettingsDocumentError, match=message):
        do_import(world, text, "company", reason="r")
    assert world.head() == 0


def test_unknown_keys_and_layers_are_refused(world: World) -> None:
    with pytest.raises(UnknownSettingError):
        do_import(world, yaml.safe_dump({"settings": {"no.such": 1}}), "company")
    with pytest.raises(SettingScopeError):
        do_import(world, yaml.safe_dump({"settings": {"t.limit": 1}}), "nowhere")
    with open_uow(world.db, readonly=True) as uow, pytest.raises(SettingScopeError):
        S.export_yaml(uow.conn(), layer="nowhere")


def test_the_number_of_keys_in_a_file_is_bounded(world: World) -> None:
    many = {"settings": {f"a.k{i}": 1 for i in range(1001)}}
    with pytest.raises(SettingsDocumentError, match="more than 1000"):
        do_import(world, yaml.safe_dump(many), "company")
