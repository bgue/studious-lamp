"""Schema.EffectiveChanged and the reload hook (P0-I2-T10). Copied into place; do not edit."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.bus import InProcessBus
from tl_core.ledger import NewEvent
from tl_core.schema_provider import DirectorySchemaProvider
from tl_core.services.schema_events import (
    EVENT_TYPE,
    record_effective_schema,
    reload_and_record,
    schema_reload_subscriber,
    schema_stream_id,
)
from tl_core.util import new_ulid

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"


@pytest.fixture
def packages(tmp_path: Path) -> Path:
    target = tmp_path / "pkgs"
    shutil.copytree(FIXTURES, target)
    return target


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


def edit(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text().replace(old, new))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


def schema_events(db: Path, scope: str) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [
            {"version": e.stream_version, "scope": e.scope, "payload": e.payload}
            for e in uow.ledger.read_stream(schema_stream_id(scope))
        ]


def test_stream_ids() -> None:
    assert schema_stream_id("company") == "schema:company"
    assert schema_stream_id("project:P123") == "schema:project:P123"


def test_the_first_reload_records_every_scope(db: Path, packages: Path) -> None:
    provider = DirectorySchemaProvider(packages)
    with open_uow(db) as uow:
        events = reload_and_record(uow, provider)
    assert [e.event_type for e in events] == [EVENT_TYPE, EVENT_TYPE]
    assert sorted(e.scope for e in events) == ["company", "project:P123"]
    by_scope = {e.scope: e for e in events}
    project = by_scope["project:P123"]
    assert project.stream_id == "schema:project:P123"
    assert project.stream_type == "schema"
    assert project.stream_version == 1
    assert project.actor == "svc:schema" and project.source == "schema-reload"
    assert project.payload == {
        "scope": "project:P123",
        "effective_schema_hash": provider.effective("project:P123").hash,
        "previous_hash": None,
        "packages": ["co.acme.engineering@3.2.0", "prj.P123@1.0.0", "x.P123@1.4.0"],
    }
    assert by_scope["company"].payload["packages"] == ["co.acme.engineering@3.2.0"]


def test_recording_is_idempotent(db: Path, packages: Path) -> None:
    provider = DirectorySchemaProvider(packages)
    with open_uow(db) as uow:
        reload_and_record(uow, provider)
    with open_uow(db) as uow:
        assert reload_and_record(uow, provider) == []
        assert record_effective_schema(uow, provider.effective("company")) is None
    assert len(schema_events(db, "company")) == 1


def test_a_project_edit_records_only_that_scope(db: Path, packages: Path) -> None:
    provider = DirectorySchemaProvider(packages)
    with open_uow(db) as uow:
        reload_and_record(uow, provider)
    first = schema_events(db, "project:P123")[0]["payload"]
    edit(packages / "x.P123@1.4.0.yaml", "Shutdown window reference", "Shutdown window ref")
    with open_uow(db) as uow:
        events = reload_and_record(uow, provider)
    assert [e.scope for e in events] == ["project:P123"]
    second = events[0]
    assert second.stream_version == 2
    assert second.payload["previous_hash"] == first["effective_schema_hash"]  # type: ignore[index]
    assert second.payload["effective_schema_hash"] != first["effective_schema_hash"]  # type: ignore[index]
    assert len(schema_events(db, "company")) == 1


def test_a_company_edit_records_both_scopes(db: Path, packages: Path) -> None:
    provider = DirectorySchemaProvider(packages)
    with open_uow(db) as uow:
        reload_and_record(uow, provider)
    edit(packages / "co.acme.engineering@3.2.0.yaml", "Nominal pipe size", "Nominal size")
    with open_uow(db) as uow:
        events = reload_and_record(uow, provider)
    assert sorted(e.scope for e in events) == ["company", "project:P123"]
    assert {e.stream_version for e in events} == {2}


def test_an_event_in_a_rolled_back_unit_of_work_is_not_kept(db: Path, packages: Path) -> None:
    provider = DirectorySchemaProvider(packages)
    with pytest.raises(RuntimeError), open_uow(db) as uow:
        reload_and_record(uow, provider)
        raise RuntimeError("abort")
    assert schema_events(db, "company") == []
    with open_uow(db) as uow:
        assert len(reload_and_record(uow, provider)) == 2


def test_the_bus_hook_reloads_on_package_publication(db: Path, packages: Path) -> None:
    provider = DirectorySchemaProvider(packages)
    bus = InProcessBus()
    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e.event_type), event_types=[EVENT_TYPE])
    hook = schema_reload_subscriber(provider, lambda: open_uow(db, bus=bus))
    bus.subscribe(hook, event_types=["SchemaPackage.Published"])

    def publish(package: str) -> None:
        with open_uow(db, bus=bus) as uow:
            uow.append(
                stream_id=f"pkg:{package}",
                stream_type="schema_package",
                scope="company",
                expected_version=uow.ledger.stream_version(f"pkg:{package}"),
                events=[
                    NewEvent(
                        event_type="SchemaPackage.Published",
                        payload={"package": package, "version": "3.2.0"},
                    )
                ],
                actor="user:steward",
                source="test",
                correlation_id=new_ulid(),
            )

    publish("co.acme.engineering")
    assert seen == [EVENT_TYPE, EVENT_TYPE]
    assert len(schema_events(db, "company")) == 1
    edit(packages / "x.P123@1.4.0.yaml", "Shutdown window reference", "Shutdown window ref")
    publish("x.P123")
    assert seen == [EVENT_TYPE] * 3
    assert len(schema_events(db, "project:P123")) == 2


def test_other_events_do_not_trigger_a_reload(db: Path, packages: Path) -> None:
    provider = DirectorySchemaProvider(packages)
    bus = InProcessBus()
    bus.subscribe(schema_reload_subscriber(provider, lambda: open_uow(db, bus=bus)))
    with open_uow(db, bus=bus) as uow:
        uow.append(
            stream_id="other",
            stream_type="thing",
            scope="company",
            expected_version=0,
            events=[NewEvent(event_type="Thing.Happened", payload={})],
            actor="user:u",
            source="test",
            correlation_id=new_ulid(),
        )
    assert schema_events(db, "company") == []
