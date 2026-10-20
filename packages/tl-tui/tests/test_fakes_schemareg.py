"""The fake schema workbench is a `ClientInterface` and answers like the embedded client (P1-I8)."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from fakes_schemareg import make_package
from tl_core.auth.errors import ForbiddenError
from tl_mod_schemareg.errors import SchemaPackageNotFoundError
from tl_mod_schemareg.handlers.packages import DraftSchemaPackage, PublishSchemaPackage
from tl_tui.client import ClientInterface


def test_the_fake_is_a_client_interface() -> None:
    as_protocol: ClientInterface = FakeClient()
    assert as_protocol is not None


def test_packages_are_listed_highest_first_and_filtered() -> None:
    client = FakeClient()
    client.seed_schema_package(make_package(version="3.3.0", state="Published"))
    client.seed_schema_package(make_package(version="3.10.0", state="Draft"))
    client.seed_schema_package(make_package("x.P123", "1.0.0", scope="project:P123"))
    assert [p.key for p in client.list_schema_packages(package="co.acme.engineering")] == [
        "co.acme.engineering@3.10.0",
        "co.acme.engineering@3.3.0",
    ]
    assert [p.version for p in client.list_schema_packages(state="Published")] == ["3.3.0"]
    assert [p.package for p in client.list_schema_packages(scope="project:P123")] == ["x.P123"]
    assert len(client.list_schema_packages(limit=1)) == 1


def test_a_package_is_found_by_id_or_key_and_a_missing_one_raises() -> None:
    client = FakeClient()
    detail = make_package()
    client.seed_schema_package(detail)
    assert client.get_schema_package(detail.id) == client.get_schema_package(detail.key) == detail
    with pytest.raises(SchemaPackageNotFoundError):
        client.get_schema_package("nope")
    with pytest.raises(SchemaPackageNotFoundError):
        client.sample_test_schema_package("nope")


def test_commands_are_recorded_and_an_admins_act_needs_the_admin() -> None:
    client = FakeClient()
    draft = DraftSchemaPackage(actor="user:dev", source="tui", scope="company", content="x")
    client.schemareg_command("DraftSchemaPackage", draft)
    publish = PublishSchemaPackage(actor="user:dev", source="tui", scope="company", package_id="P")
    client.schemareg_command("PublishSchemaPackage", publish)
    assert client.schemareg_commands == [draft, publish]
    client.is_admin = False
    with pytest.raises(ForbiddenError):
        client.schemareg_command("PublishSchemaPackage", publish)
    client.schemareg_command("DraftSchemaPackage", draft)
    with pytest.raises(ForbiddenError):
        client.schemareg_command("NoSuchCommand", draft)
    with pytest.raises(ForbiddenError):
        client.schemareg_command("PublishSchemaPackage", draft)


def test_reads_with_nothing_seeded_are_empty() -> None:
    client = FakeClient()
    assert client.list_schema_adoptions() == [] and client.list_schema_waivers() == []
    assert client.get_schema_drift("P1") == []
    assert client.get_project_schema_impact("P1", "a", "1.0.0").entries == ()
