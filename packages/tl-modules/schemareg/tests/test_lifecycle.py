"""The life of a package: draft, analyse, submit, review, publish, deprecate, retire (T01)."""

from __future__ import annotations

import pytest
from tl_core.services.errors import ServiceError
from tl_mod_schemareg.errors import (
    DuplicateSchemaPackageError,
    InvalidSchemaPackageError,
    NotTheAuthorError,
    SchemaPackageStateError,
    SelfReviewError,
    StaleAnalysisError,
)
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DeprecateSchemaPackage,
    DraftSchemaPackage,
    PublishSchemaPackage,
    RequestSchemaChanges,
    RetireSchemaPackage,
    ReviseSchemaPackage,
    SubmitSchemaPackage,
)
from tl_mod_schemareg.testing import (
    ADMIN,
    AUTHOR,
    REVIEWER,
    RegistryWorld,
    add_optional_property,
    add_required_property,
    next_version,
    retype_property,
)


def draft(world: RegistryWorld, version: str = "3.3.0", edit=add_optional_property) -> str:  # type: ignore[no-untyped-def]
    content = next_version("co.acme.engineering", version, edit)
    return world.do(DraftSchemaPackage, content=content, changelog="Adds a leak class.").stream_id


def to_review(world: RegistryWorld, package_id: str) -> None:
    world.do(AnalyseSchemaPackage, package_id=package_id)
    world.do(SubmitSchemaPackage, package_id=package_id)


def test_a_draft_is_a_record_in_the_state_draft(world: RegistryWorld) -> None:
    package_id = draft(world)
    row = world.package(package_id)
    assert row.key == "co.acme.engineering@3.3.0"
    assert (row.state, row.scope, row.kind, row.project) == ("Draft", "company", "company", None)
    assert row.drafted_by == AUTHOR and row.changelog == "Adds a leak class."
    assert len(row.content_sha256) == 64 and row.classification is None


def test_a_project_package_is_drafted_in_the_scope_of_its_project(world: RegistryWorld) -> None:
    content = next_version("x.P123", "1.5.0")
    row = world.package(world.do(DraftSchemaPackage, content=content).stream_id)
    assert (row.scope, row.kind, row.project) == ("project:P123", "extension", "P123")


def test_a_version_that_exists_as_a_file_or_a_draft_cannot_be_drafted(world: RegistryWorld) -> None:
    with pytest.raises(DuplicateSchemaPackageError, match="in force"):
        world.do(DraftSchemaPackage, content=next_version("co.acme.engineering", "3.2.0"))
    draft(world)
    with pytest.raises(DuplicateSchemaPackageError, match="already drafted"):
        draft(world)


@pytest.mark.parametrize(
    "content", ["not: a package", ": : :", "- a list\n- not a mapping\n", "package: co.x\n"]
)
def test_content_that_is_not_a_package_is_refused(world: RegistryWorld, content: str) -> None:
    with pytest.raises(InvalidSchemaPackageError):
        world.do(DraftSchemaPackage, content=content)


def test_a_package_over_the_size_limit_is_refused(world: RegistryWorld) -> None:
    big = next_version("co.acme.engineering", "3.3.0") + "# " + "x" * 262_144
    with pytest.raises(InvalidSchemaPackageError, match="larger than"):
        world.do(DraftSchemaPackage, content=big)


def test_only_the_author_revises_and_the_identity_cannot_change(world: RegistryWorld) -> None:
    package_id = draft(world)
    changed = next_version("co.acme.engineering", "3.3.0", add_required_property)
    with pytest.raises(NotTheAuthorError):
        world.do(ReviseSchemaPackage, REVIEWER, package_id=package_id, content=changed)
    world.do(ReviseSchemaPackage, package_id=package_id, content=changed, changelog="Required.")
    row = world.package(package_id)
    assert "required_in_states" in row.content and row.changelog == "Required."
    other = next_version("co.acme.engineering", "3.4.0", add_required_property)
    with pytest.raises(InvalidSchemaPackageError, match="cannot change"):
        world.do(ReviseSchemaPackage, package_id=package_id, content=other)


def test_analysis_stores_the_classification_and_the_base(world: RegistryWorld) -> None:
    package_id = draft(world)
    world.do(AnalyseSchemaPackage, package_id=package_id)
    row = world.package(package_id)
    assert row.base_ref == "co.acme.engineering@3.2.0"
    assert row.worst_class == "additive" and row.classification is not None
    assert row.classification["auto_adoptable"] is True
    assert row.analysed_sha256 == row.content_sha256 and row.impact_sha256 is not None


def test_a_revision_voids_the_analysis_and_a_submit_needs_a_new_one(world: RegistryWorld) -> None:
    package_id = draft(world)
    world.do(AnalyseSchemaPackage, package_id=package_id)
    changed = next_version("co.acme.engineering", "3.3.0", add_required_property)
    world.do(ReviseSchemaPackage, package_id=package_id, content=changed)
    assert world.package(package_id).classification is None
    with pytest.raises(StaleAnalysisError, match="analyse it first"):
        world.do(SubmitSchemaPackage, package_id=package_id)
    world.do(AnalyseSchemaPackage, package_id=package_id)
    assert world.package(package_id).worst_class == "constraining"
    world.do(SubmitSchemaPackage, package_id=package_id)
    assert world.package(package_id).state == "InReview"


def test_a_breaking_change_cannot_be_submitted(world: RegistryWorld) -> None:
    package_id = draft(world, edit=retype_property)
    world.do(AnalyseSchemaPackage, package_id=package_id)
    assert world.package(package_id).worst_class == "breaking"
    with pytest.raises(InvalidSchemaPackageError, match="not allowed in place"):
        world.do(SubmitSchemaPackage, package_id=package_id)
    assert world.package(package_id).state == "Draft"


def test_only_the_author_analyses_and_submits(world: RegistryWorld) -> None:
    package_id = draft(world)
    with pytest.raises(NotTheAuthorError):
        world.do(AnalyseSchemaPackage, REVIEWER, package_id=package_id)
    world.do(AnalyseSchemaPackage, package_id=package_id)
    with pytest.raises(NotTheAuthorError):
        world.do(SubmitSchemaPackage, REVIEWER, package_id=package_id)


def test_a_version_that_is_not_higher_cannot_be_analysed(world: RegistryWorld) -> None:
    package_id = draft(world, "3.1.0")
    with pytest.raises(InvalidSchemaPackageError, match="higher version"):
        world.do(AnalyseSchemaPackage, package_id=package_id)


def test_the_author_and_the_submitter_cannot_approve(world: RegistryWorld) -> None:
    package_id = draft(world)
    to_review(world, package_id)
    with pytest.raises(SelfReviewError):
        world.do(ApproveSchemaPackage, AUTHOR, package_id=package_id)
    world.do(ApproveSchemaPackage, ADMIN, package_id=package_id, comment="Fine.")
    row = world.package(package_id)
    assert (row.state, row.approved_by) == ("Approved", ADMIN)
    assert row.approved_digest == row.classification_digest


def test_changes_requested_send_the_package_back_to_draft(world: RegistryWorld) -> None:
    package_id = draft(world)
    to_review(world, package_id)
    world.do(RequestSchemaChanges, ADMIN, package_id=package_id, reason="Explain the class.")
    row = world.package(package_id)
    assert row.state == "Draft" and row.approved_by is None
    # still analysed for the same content: it can go straight back to review
    world.do(SubmitSchemaPackage, package_id=package_id)
    assert world.package(package_id).state == "InReview"


def test_publishing_needs_an_approved_package(world: RegistryWorld) -> None:
    package_id = draft(world)
    to_review(world, package_id)
    with pytest.raises(SchemaPackageStateError, match="Approved"):
        world.do(PublishSchemaPackage, ADMIN, package_id=package_id)


def test_publishing_puts_the_version_into_the_company_schema_but_not_into_a_project(
    world: RegistryWorld,
) -> None:
    package_id = draft(world)
    to_review(world, package_id)
    world.do(ApproveSchemaPackage, ADMIN, package_id=package_id)
    before = world.provider.effective("company").hash
    world.do(PublishSchemaPackage, ADMIN, package_id=package_id)
    row = world.package(package_id)
    assert row.state == "Published" and row.published_at is not None
    company = world.provider.effective("company")
    assert company.hash != before
    assert "co.acme.engineering@3.3.0" in [f"{p.name}@{p.version}" for p in company.packages]
    assert company.psets["valve_data"].find("seat_leak_class") is not None
    project = world.provider.effective("project:P123")
    assert "co.acme.engineering@3.2.0" in [f"{p.name}@{p.version}" for p in project.packages]
    assert project.psets["valve_data"].find("seat_leak_class") is None


def test_the_published_event_carries_the_record_and_the_class(world: RegistryWorld) -> None:
    package_id = draft(world)
    to_review(world, package_id)
    world.do(ApproveSchemaPackage, ADMIN, package_id=package_id)
    result = world.do(PublishSchemaPackage, ADMIN, package_id=package_id)
    published = [e for e in result.events if e.event_type == "SchemaPackage.Published"]
    assert len(published) == 1
    payload = published[0].payload
    assert payload["package"] == "co.acme.engineering" and payload["version"] == "3.3.0"
    assert payload["record_id"] == package_id and payload["worst_class"] == "additive"
    assert payload["auto_adopted"] == []


def test_a_published_package_is_immutable(world: RegistryWorld) -> None:
    package_id = draft(world)
    to_review(world, package_id)
    world.do(ApproveSchemaPackage, ADMIN, package_id=package_id)
    world.do(PublishSchemaPackage, ADMIN, package_id=package_id)
    changed = next_version("co.acme.engineering", "3.3.0", add_required_property)
    with pytest.raises(SchemaPackageStateError):
        world.do(ReviseSchemaPackage, package_id=package_id, content=changed)
    with pytest.raises(SchemaPackageStateError):
        world.do(AnalyseSchemaPackage, package_id=package_id)
    with pytest.raises(SchemaPackageStateError):
        world.do(PublishSchemaPackage, ADMIN, package_id=package_id)


def test_publishing_is_refused_when_a_version_below_it_appeared_since_the_analysis(
    world: RegistryWorld,
) -> None:
    first = draft(world, "3.3.0")
    second = draft(world, "3.4.0", edit=add_optional_property)
    for package_id in (first, second):
        to_review(world, package_id)
        world.do(ApproveSchemaPackage, ADMIN, package_id=package_id)
    world.do(PublishSchemaPackage, ADMIN, package_id=first)
    with pytest.raises(StaleAnalysisError, match="analyse it again"):
        world.do(PublishSchemaPackage, ADMIN, package_id=second)


def test_deprecate_then_retire_takes_the_version_out_of_the_company_schema(
    world: RegistryWorld,
) -> None:
    package_id = draft(world)
    to_review(world, package_id)
    world.do(ApproveSchemaPackage, ADMIN, package_id=package_id)
    world.do(PublishSchemaPackage, ADMIN, package_id=package_id)
    with pytest.raises(SchemaPackageStateError):
        world.do(RetireSchemaPackage, ADMIN, package_id=package_id, reason="Too soon.")
    world.do(DeprecateSchemaPackage, ADMIN, package_id=package_id, reason="Superseded.")
    assert world.package(package_id).state == "Deprecated"
    assert any(p.version == "3.3.0" for p in world.provider.effective("company").packages)
    world.do(RetireSchemaPackage, ADMIN, package_id=package_id, reason="Not pinned.")
    row = world.package(package_id)
    assert row.state == "Retired" and row.retired_at is not None
    assert all(p.version != "3.3.0" for p in world.provider.effective("company").packages)


def test_every_failure_of_the_module_is_a_service_error() -> None:
    assert issubclass(StaleAnalysisError, ServiceError)
