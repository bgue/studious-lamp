"""The registry source: what the provider reads from the ledger (T01)."""

from __future__ import annotations

from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core.schema_provider import DirectorySchemaProvider
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_mod_schemareg.handlers.packages import DeprecateSchemaPackage, RetireSchemaPackage
from tl_mod_schemareg.source import LedgerRegistrySource
from tl_mod_schemareg.testing import ADMIN, RegistryWorld, publish_version


def source(world: RegistryWorld, ttl: float = 0) -> LedgerRegistrySource:
    return LedgerRegistrySource(world._factory, ttl=ttl)  # noqa: SLF001


def test_an_empty_ledger_gives_an_empty_state(world: RegistryWorld) -> None:
    state = source(world).snapshot()
    assert list(state.documents) == [] and dict(state.pins) == {} and dict(state.waivers) == {}
    assert state.projects() == set()


def test_published_and_deprecated_packages_are_in_the_state_and_retired_ones_are_not(
    world: RegistryWorld,
) -> None:
    first = publish_version(world, "3.3.0")
    publish_version(world, "3.4.0")
    keys = lambda: [d.key() for d in source(world).snapshot().documents]  # noqa: E731
    assert keys() == ["co.acme.engineering@3.3.0", "co.acme.engineering@3.4.0"]
    world.do(DeprecateSchemaPackage, ADMIN, package_id=first.stream_id, reason="Replaced.")
    assert "co.acme.engineering@3.3.0" in keys()
    world.do(RetireSchemaPackage, ADMIN, package_id=first.stream_id, reason="Gone.")
    assert keys() == ["co.acme.engineering@3.4.0"]


def test_a_drafted_package_is_not_in_the_state(world: RegistryWorld) -> None:
    from tl_mod_schemareg.handlers.packages import DraftSchemaPackage
    from tl_mod_schemareg.testing import add_optional_property, next_version

    world.do(
        DraftSchemaPackage,
        content=next_version("co.acme.engineering", "3.3.0", add_optional_property),
    )
    assert list(source(world).snapshot().documents) == []


def test_pins_come_from_the_adoption_records(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    world.do(
        AdoptSchemaPackage, ADMIN, project="P999", package="co.acme.engineering", version="3.3.0"
    )
    state = source(world).snapshot()
    assert state.pins == {"project:P999": {"co.acme.engineering": "3.3.0"}}
    assert state.projects() == {"P999"}


def test_the_token_changes_with_the_registry(world: RegistryWorld) -> None:
    src = source(world)
    first = src.token()
    publish_version(world, "3.3.0")
    second = src.token()
    assert second != first and src.token() == second


def test_a_cached_token_is_dropped_when_this_process_changes_the_registry(
    world: RegistryWorld,
) -> None:
    src = source(world, ttl=3600)
    first = src.token()
    publish_version(world, "3.3.0")  # bumps the change counter
    assert src.token() != first


def test_a_package_that_no_longer_parses_is_left_out(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_schemareg_schema_package SET content = 'package: [broken'")
        )
    assert list(source(world).snapshot().documents) == []
    # and the provider still serves the directory's packages
    world.provider.reload()
    assert [p.version for p in world.provider.effective("company").packages] == ["3.2.0"]


def test_a_ledger_without_the_tables_gives_an_empty_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from tl_adapters.db import create_schema

    target = tmp_path / "bare.db"
    create_schema(target)
    with open_uow(target) as uow:
        uow.conn().execute(text("DROP VIEW IF EXISTS v_schemareg_schema_package"))
        uow.conn().execute(text("DROP TABLE cur_schemareg_schema_package"))
    bare = LedgerRegistrySource(lambda readonly=False: open_uow(target, readonly=readonly), ttl=0)
    assert bare.token() == "none" and list(bare.snapshot().documents) == []
    provider = DirectorySchemaProvider()
    provider.attach_registry(bare)
    assert [p.version for p in provider.effective("company").packages] == ["3.2.0"]


def test_a_package_that_does_not_fit_is_left_out_of_the_schema(world: RegistryWorld) -> None:
    from tl_mod_schemareg.testing import fixture_text

    publish_version(world, "3.3.0", name="co.acme.engineering")
    # a project package that depends on a version nobody has
    text_ = (
        fixture_text("x.P123")
        .replace("version: 1.4.0", "version: 1.9.0")
        .replace("co.acme.engineering: 3.2.0", "co.acme.engineering: 8.8.8")
    )
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_schemareg_schema_package SET content = :c"), {"c": text_}
        )
    world.provider.reload()
    # the broken registry entry is skipped; the company schema is still served
    assert world.provider.registry().origin("x.P123", "1.9.0") is None
    assert world.provider.effective("company").hash
