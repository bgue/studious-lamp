"""Adoption: a project pins a published version of a company package (T01)."""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_mod_schemareg import analysis
from tl_mod_schemareg.errors import AdoptionError, ImpactReviewRequiredError
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_mod_schemareg.handlers.packages import (
    DeprecateSchemaPackage,
    RetireSchemaPackage,
)
from tl_mod_schemareg.testing import (
    ADMIN,
    RegistryWorld,
    add_optional_property,
    add_required_property,
    publish_version,
)

PKG = "co.acme.engineering"


def versions(world: RegistryWorld, project: str) -> list[str]:
    schema = world.provider.effective(f"project:{project}")
    return [p.version for p in schema.packages if p.name == PKG]


def adopt(world: RegistryWorld, project: str, version: str, **more: str):  # type: ignore[no-untyped-def]
    return world.do(
        AdoptSchemaPackage, ADMIN, project=project, package=PKG, version=version, **more
    )


def test_an_additive_version_is_pinned_without_an_impact_digest(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    assert versions(world, "P999") == ["3.2.0"]
    result = adopt(world, "P999", "3.3.0")
    assert result.key == "P999/co.acme.engineering"
    assert versions(world, "P999") == ["3.3.0"]
    schema = world.provider.effective("project:P999")
    assert schema.psets["valve_data"].find("seat_leak_class") is not None
    row = world.adoption("P999", PKG)
    assert row is not None
    assert (row.version, row.previous_version, row.worst_class, row.impact_sha256) == (
        "3.3.0",
        "3.2.0",
        "additive",
        None,
    )
    assert row.scope == "project:P999" and row.adopted_by == ADMIN


def test_another_project_keeps_its_own_version(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    adopt(world, "P999", "3.3.0")
    assert versions(world, "P998") == ["3.2.0"]
    assert [p.version for p in world.provider.effective("company").packages] == ["3.3.0"]


def test_a_project_whose_package_depends_on_another_version_cannot_pin(
    world: RegistryWorld,
) -> None:
    publish_version(world, "3.3.0")
    with pytest.raises(AdoptionError, match="pinned at both"):
        adopt(world, "P123", "3.3.0")


def test_a_constraining_version_needs_the_digest_of_the_impact_report(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0", add_required_property)
    with pytest.raises(ImpactReviewRequiredError, match="constraining"):
        adopt(world, "P999", "3.3.0")
    with pytest.raises(ImpactReviewRequiredError):
        adopt(world, "P999", "3.3.0", impact_sha256="0" * 64)
    with open_uow(world.db, readonly=True) as uow:
        report, _before, _after = analysis.project_impact(uow.conn(), "P999", PKG, "3.3.0")
    adopt(world, "P999", "3.3.0", impact_sha256=report.digest)
    row = world.adoption("P999", PKG)
    assert row is not None
    assert row.worst_class == "constraining" and row.impact_sha256 == report.digest
    assert versions(world, "P999") == ["3.3.0"]


def test_pinning_again_moves_the_one_adoption_record(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    publish_version(world, "3.4.0")
    first = adopt(world, "P999", "3.3.0")
    second = adopt(world, "P999", "3.4.0")
    assert second.stream_id == first.stream_id
    row = world.adoption("P999", PKG)
    assert row is not None and (row.version, row.previous_version) == ("3.4.0", "3.3.0")
    assert world.scalar("SELECT COUNT(*) FROM cur_schemareg_adoption") == 1
    with pytest.raises(AdoptionError, match="already pins"):
        adopt(world, "P999", "3.4.0")


def test_a_downgrade_needs_the_digest_too(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    adopt(world, "P999", "3.3.0")
    with pytest.raises(ImpactReviewRequiredError, match="downgrade"):
        adopt(world, "P999", "3.2.0")


def test_what_is_not_in_force_or_not_a_company_package_cannot_be_pinned(
    world: RegistryWorld,
) -> None:
    with pytest.raises(AdoptionError, match="not in force"):
        adopt(world, "P999", "9.9.9")
    with pytest.raises(AdoptionError, match="extension package"):
        world.do(AdoptSchemaPackage, ADMIN, project="P999", package="x.P123", version="1.4.0")
    with pytest.raises(AdoptionError, match="written in a form"):
        adopt(world, "bad project", "3.2.0")


def test_a_deprecated_version_is_not_adopted_and_a_pinned_one_is_not_retired(
    world: RegistryWorld,
) -> None:
    published = publish_version(world, "3.3.0")
    adopt(world, "P999", "3.3.0")
    world.do(DeprecateSchemaPackage, ADMIN, package_id=published.stream_id, reason="Replaced.")
    with pytest.raises(AdoptionError, match="still pinned by P999"):
        world.do(RetireSchemaPackage, ADMIN, package_id=published.stream_id, reason="Gone.")
    with pytest.raises(AdoptionError, match="Deprecated"):
        adopt(world, "P998", "3.3.0")


def test_publication_moves_the_projects_that_pin_the_version_below_when_it_is_additive(
    world: RegistryWorld,
) -> None:
    publish_version(world, "3.3.0")
    adopt(world, "P999", "3.3.0")
    adopt(world, "P998", "3.3.0")
    result = publish_version(world, "3.4.0", lambda data: _two(data), auto_adopt=True)
    published = next(e for e in result.events if e.event_type == "SchemaPackage.Published")
    assert published.payload["auto_adopted"] == ["P998", "P999"]
    assert versions(world, "P999") == ["3.4.0"] and versions(world, "P998") == ["3.4.0"]
    row = world.adoption("P999", PKG)
    assert row is not None and row.previous_version == "3.3.0"
    pins = [e for e in result.events if e.event_type == "Adoption.Pinned"]
    assert len(pins) == 2 and all(e.payload["auto"] is True for e in pins)


def _two(data: dict) -> None:  # type: ignore[type-arg]
    add_optional_property(data)
    data["psets"]["valve_data"]["properties"]["second"] = {
        "description": "A second optional property.",
        "range": "string",
    }


def test_publication_does_not_move_a_project_that_asked_for_nothing(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    adopt(world, "P999", "3.3.0")
    result = publish_version(world, "3.4.0", _two, auto_adopt=False)
    published = next(e for e in result.events if e.event_type == "SchemaPackage.Published")
    assert published.payload["auto_adopted"] == []
    assert versions(world, "P999") == ["3.3.0"]


def test_a_constraining_version_is_never_adopted_by_publication(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    adopt(world, "P999", "3.3.0")
    result = publish_version(world, "3.4.0", _required_two, auto_adopt=True)
    published = next(e for e in result.events if e.event_type == "SchemaPackage.Published")
    assert published.payload["auto_adopted"] == []
    assert versions(world, "P999") == ["3.3.0"]


def _required_two(data: dict) -> None:  # type: ignore[type-arg]
    add_optional_property(data)
    data["psets"]["valve_data"]["properties"]["second"] = {
        "description": "A second property, required.",
        "range": "string",
        "required_in_states": ["Design"],
    }
