"""Test support other packages share: a ledger, a schema provider that reads it, the commands.

``RegistryWorld`` wraps a ledger target and opens a unit of work per call, like a real command. It
installs a ``DirectorySchemaProvider`` (the committed fixture packages) with this ledger's registry
attached, for the length of a ``with world.installed():`` block. It is not registered anywhere and
never runs in production.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command, CommandResult
from tl_schema.registry import DEFAULT_SCHEMA_DIR

from tl_mod_schemareg import registry
from tl_mod_schemareg.commands import API_COMMANDS
from tl_mod_schemareg.source import LedgerRegistrySource

AUTHOR = "user:author"
REVIEWER = "user:reviewer"
ADMIN = "user:admin"
BASE: dict[str, Any] = {"source": "test", "scope": "company"}

_HANDLERS = {c.model.__name__: c.handler for c in API_COMMANDS}


def fixture_text(name: str) -> str:
    """The text of the committed fixture package ``name`` (``co.acme.engineering``)."""
    path = next(Path(DEFAULT_SCHEMA_DIR).glob(f"{name}@*.yaml"))
    return path.read_text(encoding="utf-8")


def next_version(
    name: str, version: str, edit: Callable[[dict[str, Any]], None] | None = None
) -> str:
    """The fixture package ``name`` as YAML text at ``version``, after ``edit`` changed its data."""
    data: dict[str, Any] = copy.deepcopy(yaml.safe_load(fixture_text(name)))
    data["version"] = version
    if edit is not None:
        edit(data)
    return yaml.safe_dump(data, sort_keys=False)


def add_optional_property(data: dict[str, Any]) -> None:
    """An additive change: a new optional property on ``valve_data``."""
    data["psets"]["valve_data"]["properties"]["seat_leak_class"] = {
        "description": "Seat leakage class of the valve.",
        "range": "string",
    }


def add_required_property(data: dict[str, Any]) -> None:
    """A constraining change: a new property that is required in the state Installed."""
    data["psets"]["valve_data"]["properties"]["seat_leak_class"] = {
        "description": "Seat leakage class of the valve.",
        "range": "string",
        "required_in_states": ["Installed"],
    }


def retype_property(data: dict[str, Any]) -> None:
    """A breaking change: the range of ``size_in`` changes."""
    data["psets"]["valve_data"]["properties"]["size_in"]["range"] = "int"


class RegistryWorld:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.provider = DirectorySchemaProvider()
        self.provider.attach_registry(LedgerRegistrySource(self._factory, ttl=0))

    def _factory(self, readonly: bool = False) -> Any:
        return open_uow(self.db, readonly=readonly)

    @contextmanager
    def installed(self) -> Generator[RegistryWorld]:
        """Make this world's provider the process provider for the block."""
        with use_provider(self.provider):
            yield self

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def run(self, command: Command) -> CommandResult:
        """Run ``command`` in its own unit of work and commit."""
        handler = _HANDLERS[type(command).__name__]
        with open_uow(self.db) as uow:
            return handler(uow, command)

    def do(self, model: type[Command], actor: str = AUTHOR, **fields: Any) -> CommandResult:
        """Build ``model`` as ``actor`` with ``fields`` and run it."""
        return self.run(model(**{**BASE, "actor": actor}, **fields))

    def package(self, package_id: str) -> registry.PackageRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.get_package(uow.conn(), package_id)
        assert found is not None
        return found

    def adoption(self, project: str, package: str) -> registry.AdoptionRow | None:
        with open_uow(self.db, readonly=True) as uow:
            return registry.get_adoption(uow.conn(), project, package)

    def waiver(self, waiver_id: str) -> registry.WaiverRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.get_waiver(uow.conn(), waiver_id)
        assert found is not None
        return found


def publish_version(
    world: RegistryWorld,
    version: str,
    edit: Callable[[dict[str, Any]], None] | None = add_optional_property,
    *,
    name: str = "co.acme.engineering",
    auto_adopt: bool = False,
) -> CommandResult:
    """Draft, analyse, submit, approve and publish ``name@version``; returns the publication."""
    from tl_mod_schemareg.handlers.packages import (
        AnalyseSchemaPackage,
        ApproveSchemaPackage,
        DraftSchemaPackage,
        PublishSchemaPackage,
        SubmitSchemaPackage,
    )

    package_id = world.do(DraftSchemaPackage, content=next_version(name, version, edit)).stream_id
    world.do(AnalyseSchemaPackage, package_id=package_id)
    world.do(SubmitSchemaPackage, package_id=package_id)
    world.do(ApproveSchemaPackage, ADMIN, package_id=package_id)
    return world.do(PublishSchemaPackage, ADMIN, package_id=package_id, auto_adopt=auto_adopt)
