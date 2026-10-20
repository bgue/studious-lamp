"""The embedded client's schema workbench calls, and the fake held to them (P1-I8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeClient
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.auth.errors import ForbiddenError
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_schemareg.errors import SchemaPackageNotFoundError
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DraftSchemaPackage,
    PublishSchemaPackage,
)
from tl_mod_schemareg.source import LedgerRegistrySource
from tl_mod_schemareg.testing import add_optional_property, next_version
from tl_tui.embedded import EmbeddedClient

PKG = "co.acme.engineering"


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    path = tmp_path / "tl.db"
    create_schema(path)
    factory = SqliteUowFactory(path)
    provider = DirectorySchemaProvider()
    provider.attach_registry(LedgerRegistrySource(factory, ttl=0))
    with use_provider(provider):
        yield EmbeddedClient(factory, actor="user:kim")


def command(client: EmbeddedClient, name: str, model, **fields):  # type: ignore[no-untyped-def]
    return client.schemareg_command(
        name, model(actor="user:kim", source="tui", scope="company", **fields)
    )


def test_a_draft_is_made_read_and_analysed_through_the_client(client: EmbeddedClient) -> None:
    content = next_version(PKG, "3.3.0", add_optional_property)
    made = command(client, "DraftSchemaPackage", DraftSchemaPackage, content=content)
    summaries = client.list_schema_packages()
    assert [(s.key, s.state) for s in summaries] == [(f"{PKG}@3.3.0", "Draft")]
    command(client, "AnalyseSchemaPackage", AnalyseSchemaPackage, package_id=made.stream_id)
    detail = client.get_schema_package(f"{PKG}@3.3.0")
    assert detail.analysed and detail.classification is not None
    assert client.sample_test_schema_package(made.stream_id, 5).checked >= 0
    with pytest.raises(SchemaPackageNotFoundError):
        client.get_schema_package("nope")


def test_an_admins_act_is_refused_for_a_person_who_is_not_one(client: EmbeddedClient) -> None:
    content = next_version(PKG, "3.3.0", add_optional_property)
    made = command(client, "DraftSchemaPackage", DraftSchemaPackage, content=content)
    with pytest.raises(ForbiddenError):
        command(client, "ApproveSchemaPackage", ApproveSchemaPackage, package_id=made.stream_id)
    with pytest.raises(ForbiddenError):
        command(client, "PublishSchemaPackage", PublishSchemaPackage, package_id=made.stream_id)


def test_the_command_must_name_the_signed_in_person_and_a_known_command(
    client: EmbeddedClient,
) -> None:
    other = DraftSchemaPackage(actor="user:mallory", source="tui", scope="company", content="x")
    with pytest.raises(ForbiddenError):
        client.schemareg_command("DraftSchemaPackage", other)
    with pytest.raises(ForbiddenError):
        client.schemareg_command("CreateRecord", other)


def test_the_reads_with_nothing_adopted_are_empty_or_the_company_default(
    client: EmbeddedClient,
) -> None:
    assert client.list_schema_adoptions() == [] and client.list_schema_waivers() == []
    assert [d.package for d in client.get_schema_drift("P999")] == [PKG]
    fake = FakeClient()
    assert fake.list_schema_adoptions() == client.list_schema_adoptions()
