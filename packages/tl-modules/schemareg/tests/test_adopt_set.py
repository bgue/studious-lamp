"""AdoptSchemaSet: one optional set becomes effective for one project, by an extension (r5)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tl_core.auth.errors import ForbiddenError
from tl_mod_schemareg.errors import AdoptionError
from tl_mod_schemareg.handlers.adoption import AdoptSchemaSet
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DraftSchemaPackage,
    PublishSchemaPackage,
    SubmitSchemaPackage,
)
from tl_mod_schemareg.testing import (
    ADMIN,
    RegistryWorld,
    add_required_property,
    publish_version,
)

PKG = "co.acme.engineering"
SETS = ("inspection_data", "weld_data")


def add_sets(data: dict[str, Any]) -> None:
    for name in SETS:
        data["psets"][name] = {
            "label": name,
            "description": f"{name} example set.",
            "applies_to": ["core.Record"],
            "adoption": "optional",
            "properties": {"note": {"label": "Note", "description": "A note.", "range": "string"}},
        }


def add_sets_and_a_required_property(data: dict[str, Any]) -> None:
    add_sets(data)
    add_required_property(data)


def adopt(world: RegistryWorld, project: str, pset: str, **more: Any) -> Any:
    fields = {"scope": f"project:{project}", "project": project, "package": PKG}
    fields.update({"version": "3.3.0", "pset": pset, **more})
    return world.run(AdoptSchemaSet(actor=ADMIN, source="test", **fields))


def has(world: RegistryWorld, project: str, pset: str) -> bool:
    return pset in world.provider.effective(f"project:{project}").psets


def test_the_set_is_effective_for_that_project_only(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0", add_sets)
    others = {p: world.provider.effective(p).hash for p in ("company", "project:P998")}
    assert not has(world, "P123", "inspection_data")
    adopt(world, "P123", "inspection_data")
    assert has(world, "P123", "inspection_data") and not has(world, "P123", "weld_data")
    assert not has(world, "P998", "inspection_data")
    assert {p: world.provider.effective(p).hash for p in others} == others
    schema = world.provider.effective("project:P123")
    assert [p.version for p in schema.packages if p.name == PKG] == ["3.3.0"]
    # what the project's extension did before is still done
    assert schema.psets["valve_data"].extension == "x.P123@1.5.0"
    assert "fat_witness_by" in schema.psets["valve_data"].custom


def test_a_project_without_an_extension_gets_one_and_a_second_set_keeps_the_first(
    world: RegistryWorld,
) -> None:
    publish_version(world, "3.3.0", add_sets)
    adopt(world, "P999", "inspection_data")
    assert world.provider.effective("project:P999").psets["inspection_data"].extension == (
        "x.P999@1.0.0"
    )
    adopt(world, "P999", "weld_data")
    schema = world.provider.effective("project:P999")
    assert {"inspection_data", "weld_data"} <= set(schema.psets)
    assert schema.psets["weld_data"].extension == "x.P999@1.1.0"
    assert not has(world, "P998", "weld_data")


def test_the_scope_must_be_the_projects(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0", add_sets)
    with pytest.raises(ForbiddenError):
        adopt(world, "P123", "inspection_data", scope="project:P999")
    assert not has(world, "P123", "inspection_data")
    adopt(world, "P123", "inspection_data", scope="company")  # an administrator's scope
    assert has(world, "P123", "inspection_data")


def test_what_cannot_be_adopted_is_refused(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0", add_sets)
    with pytest.raises(AdoptionError, match="no set"):
        adopt(world, "P123", "no_such_set")
    with pytest.raises(AdoptionError, match="not optional"):
        adopt(world, "P123", "valve_data")
    with pytest.raises(AdoptionError, match="not in force"):
        adopt(world, "P123", "inspection_data", version="9.9.9")
    adopt(world, "P123", "inspection_data")
    with pytest.raises(AdoptionError, match="already adopted"):
        adopt(world, "P123", "inspection_data")


def test_a_project_with_several_extension_packages_is_an_administrators(
    world: RegistryWorld,
) -> None:
    publish_version(world, "3.3.0", add_sets)
    other = {
        "package": "z.P123",
        "version": "1.0.0",
        "kind": "extension",
        "description": "A second extension package of P123.",
        "project": "P123",
        "depends": {PKG: "3.2.0"},
        "extends": [],
    }
    package_id = world.do(DraftSchemaPackage, content=json.dumps(other)).stream_id
    world.do(AnalyseSchemaPackage, package_id=package_id)
    world.do(SubmitSchemaPackage, package_id=package_id)
    world.do(ApproveSchemaPackage, ADMIN, package_id=package_id)
    world.do(PublishSchemaPackage, ADMIN, package_id=package_id)
    with pytest.raises(AdoptionError, match="several extension packages"):
        adopt(world, "P123", "inspection_data")


def test_a_draft_or_unpublished_version_is_not_adopted_from(world: RegistryWorld) -> None:
    with pytest.raises(AdoptionError, match="not in force"):
        adopt(world, "P123", "inspection_data")


def test_a_constraining_version_is_an_administrators_to_adopt(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0", add_sets_and_a_required_property)
    with pytest.raises(AdoptionError, match="constraining"):
        adopt(world, "P999", "inspection_data")
    assert not has(world, "P999", "inspection_data")
    assert world.adoption("P999", PKG) is None
