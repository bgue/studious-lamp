"""The schema registry over HTTP and the client: commands with their roles, reads (P1-I8)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from harness import Harness
from test_api_schedule import Cast
from tl_api.client import ApiClient
from tl_core.auth.errors import ForbiddenError
from tl_core.util import utcnow
from tl_mod_schemareg.errors import (
    InvalidSchemaPackageError,
    SchemaPackageNotFoundError,
    SelfReviewError,
)
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DraftSchemaPackage,
    PublishSchemaPackage,
    SubmitSchemaPackage,
)
from tl_mod_schemareg.handlers.waivers import ApproveWaiver, RequestWaiver
from tl_mod_schemareg.testing import add_optional_property, next_version

PKG = "co.acme.engineering"
BASE: dict[str, Any] = {"source": "test", "scope": "company"}


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def command(api: ApiClient, model: type, **fields: Any) -> Any:  # type: ignore[type-arg]
    return api.schemareg_command(model.__name__, model(actor="user:x", **BASE, **fields))


def draft(api: ApiClient, version: str = "3.3.0") -> str:
    content = next_version(PKG, version, add_optional_property)
    return command(api, DraftSchemaPackage, content=content).stream_id


def test_the_whole_life_runs_over_http_with_the_roles_the_table_gives(cast: Cast) -> None:
    bob, boss = cast.api("bob"), cast.api("boss")
    package_id = draft(bob)
    command(bob, AnalyseSchemaPackage, package_id=package_id)
    command(bob, SubmitSchemaPackage, package_id=package_id)
    with pytest.raises(ForbiddenError):
        command(bob, ApproveSchemaPackage, package_id=package_id)
    command(boss, ApproveSchemaPackage, package_id=package_id)
    with pytest.raises(ForbiddenError):
        command(bob, PublishSchemaPackage, package_id=package_id)
    command(boss, PublishSchemaPackage, package_id=package_id)
    detail = bob.get_schema_package(f"{PKG}@3.3.0")
    assert detail.state == "Published" and detail.classification is not None
    assert [p.version for p in bob.list_schema_packages(state="Published")] == ["3.3.0"]


def test_the_actor_of_a_command_is_the_signed_in_person(cast: Cast) -> None:
    bob = cast.api("bob")
    package_id = draft(bob)
    assert bob.get_schema_package(package_id).drafted_by == "user:bob"


def test_a_person_cannot_approve_what_they_wrote_even_as_an_admin(cast: Cast) -> None:
    boss = cast.api("boss")
    package_id = draft(boss)
    command(boss, AnalyseSchemaPackage, package_id=package_id)
    command(boss, SubmitSchemaPackage, package_id=package_id)
    with pytest.raises(SelfReviewError):
        command(boss, ApproveSchemaPackage, package_id=package_id)


def test_a_bad_package_is_a_422_with_the_modules_code(cast: Cast) -> None:
    body = {"scope": "company", "content": "not: a package"}
    response = cast.clients["bob"].post("/commands/DraftSchemaPackage", json=body)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_schema_package")
    with pytest.raises(InvalidSchemaPackageError):
        command(cast.api("bob"), DraftSchemaPackage, content="not: a package")


def test_an_agent_cannot_run_a_registry_command(cast: Cast) -> None:
    content = next_version(PKG, "3.3.0", add_optional_property)
    response = cast.agent.post(
        "/commands/DraftSchemaPackage", json={"scope": "company", "content": content}
    )
    assert response.status_code in (401, 403)
    assert cast.anonymous.post("/commands/DraftSchemaPackage", json={}).status_code == 401


def test_adoption_and_waivers_are_the_admins(cast: Cast) -> None:
    bob, boss = cast.api("bob"), cast.api("boss")
    package_id = draft(bob)
    for model in (AnalyseSchemaPackage, SubmitSchemaPackage):
        command(bob, model, package_id=package_id)
    command(boss, ApproveSchemaPackage, package_id=package_id)
    command(boss, PublishSchemaPackage, package_id=package_id)
    with pytest.raises(ForbiddenError):
        command(bob, AdoptSchemaPackage, project="P999", package=PKG, version="3.3.0")
    command(boss, AdoptSchemaPackage, project="P999", package=PKG, version="3.3.0")
    assert [(a.project, a.version) for a in bob.list_schema_adoptions("P999")] == [
        ("P999", "3.3.0")
    ]
    expires = (utcnow().date() + timedelta(days=30)).isoformat()
    waiver = command(
        bob,
        RequestWaiver,
        project="P999",
        path="psets.valve_data.size_in",
        reason="Legacy.",
        expires=expires,
    )
    with pytest.raises(ForbiddenError):
        command(bob, ApproveWaiver, waiver_id=waiver.stream_id)
    command(boss, ApproveWaiver, waiver_id=waiver.stream_id)
    assert [w.state for w in bob.list_schema_waivers("P999")] == ["Approved"]
    assert bob.get_schema_drift("P999")[0].pinned


def test_reads_need_a_sign_in_and_agents_may_read(cast: Cast) -> None:
    paths = (
        "/schema/packages",
        "/schema/adoptions",
        "/schema/waivers",
        "/projects/P999/schema/drift",
    )
    for path in paths:
        assert cast.clients["bob"].get(path).status_code == 200, path
        assert cast.agent.get(path).status_code == 200, path
        assert cast.anonymous.get(path).status_code == 401, path


def test_a_package_that_is_not_there_is_a_404(cast: Cast) -> None:
    response = cast.clients["bob"].get("/schema/packages/nope")
    assert (response.status_code, response.json()["error"]) == (404, "schema_package_not_found")
    with pytest.raises(SchemaPackageNotFoundError):
        cast.api("bob").get_schema_package(f"{PKG}@9.9.9")


def test_impact_and_the_sample_test_are_reads(cast: Cast) -> None:
    bob, boss = cast.api("bob"), cast.api("boss")
    package_id = draft(bob)
    sample = bob.sample_test_schema_package(package_id, 10)
    assert sample.newly_nonconformant == 0 and sample.package == f"{PKG}@3.3.0"
    for model in (AnalyseSchemaPackage, SubmitSchemaPackage):
        command(bob, model, package_id=package_id)
    command(boss, ApproveSchemaPackage, package_id=package_id)
    command(boss, PublishSchemaPackage, package_id=package_id)
    report = bob.get_project_schema_impact("P999", PKG, "3.3.0")
    assert report.scope == "project:P999" and len(report.digest) == 64
    bad = cast.clients["bob"].get(
        "/projects/P999/schema/impact", params={"package": PKG, "version": "9.9.9"}
    )
    assert bad.status_code == 422
