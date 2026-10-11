"""A small world for the extension type tests: a ledger, an object store and a type root.

``World`` copies the example packages (``schema/fixtures/types``) into a temporary root, so a test
can edit them, builds a ledger on the adapter under test, and attaches the registry to a fresh
``DirectorySchemaProvider`` (installed process-wide by the ``world`` fixture and removed after).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, make_uow_factory
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.extypes import body, registry
from tl_core.extypes.lock import write_lock
from tl_core.extypes.provider import LedgerExtensionSource, attach
from tl_core.extypes.types import TypeView
from tl_core.ledger import Event
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.records import handle_create_record

REPO = Path(__file__).resolve().parents[2]
FIXTURE_TYPES = REPO / "schema" / "fixtures" / "types"
SCOPE = "project:P1"
ALICE = "user:alice"
LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"
LIFT_PSET = "co_acme_lift_plan"
OBSERVATION_PSET = "co_acme_safety_observation"

LIFT_BODY: dict[str, Any] = {
    "crane": "CR-12",
    "crew": ["A. Okafor", "B. Lindqvist"],
    "exclusion_zone_m": 8.5,
    "lift_date": "2026-11-03",
    "load_tonnes": 42.5,
    "method_statement": "Lift the skid to the pad.",
    "risk_class": "medium",
}
OBSERVATION_VALUES: dict[str, Any] = {
    "observed_on": "2026-10-02",
    "category": "near_miss",
    "severity": "high",
    "location": "Unit 3 pipe rack",
}


@dataclass
class World:
    db: DbTarget
    factory: Any
    store: FsObjectStore
    root: Path
    source: LedgerExtensionSource
    seen: list[str] = field(default_factory=list[str])

    # --- registry ------------------------------------------------------------------------------

    def sync(self, actor: str = ALICE) -> list[TypeView]:
        return registry.sync(self.factory, self.root, actor=actor, source="test")

    def package(self, type_name: str = LIFT, version: str = "1.0.0") -> Path:
        namespace, name = type_name.rsplit(".", 1)
        return self.root / namespace / name / version

    def relock(self, path: Path) -> None:
        write_lock(path)

    def edit(self, path: Path, relative: str, old: str, new: str, *, relock: bool = True) -> None:
        """Replace text in a package file and (by default) rewrite ``type.lock``."""
        file = path / relative
        content = file.read_text(encoding="utf-8")
        assert old in content, f"{old!r} not in {relative}"
        file.write_text(content.replace(old, new), encoding="utf-8")
        if relock:
            write_lock(path)

    def types(self, status: str | None = None) -> list[TypeView]:
        with self.factory(readonly=True) as uow:
            return registry.list_types(uow.conn(), status=status)  # type: ignore[arg-type]

    def type_events(self) -> list[Event]:
        with self.factory(readonly=True) as uow:
            return [
                e
                for e in uow.ledger.read_after(0, limit=10_000)
                if e.event_type.startswith("TypeRegistration.")
            ]

    def head(self) -> int:
        with self.factory(readonly=True) as uow:
            return int(uow.ledger.head_seq())

    # --- records -------------------------------------------------------------------------------

    def create_observation(self, key: str = "SO-1", **values: Any) -> CommandResult:
        merged = {**OBSERVATION_VALUES, **values}
        cmd = CreateRecord(
            actor=ALICE,
            source="test",
            scope=SCOPE,
            record_type=OBSERVATION,
            title=f"Observation {key}",
            key=key,
            psets={OBSERVATION_PSET: merged},
        )
        with self.factory() as uow:
            return handle_create_record(uow, cmd)

    def create_lift(
        self, key: str = "LP-1", lift_body: dict[str, Any] | None = None
    ) -> CommandResult:
        cmd = CreateRecord(
            actor=ALICE,
            source="test",
            scope=SCOPE,
            record_type=LIFT,
            title=f"Lift {key}",
            key=key,
        )
        with self.factory() as uow:
            return body.create_extension_record(
                uow, self.store, cmd, dict(LIFT_BODY if lift_body is None else lift_body)
            )

    def row(self, record_id: str) -> dict[str, Any]:
        with self.factory(readonly=True) as uow:
            found = (
                uow.conn()
                .execute(text("SELECT * FROM cur_core_record WHERE id = :id"), {"id": record_id})
                .mappings()
                .one()
            )
            return dict(found)

    def stream(self, record_id: str) -> list[Event]:
        with self.factory(readonly=True) as uow:
            return uow.ledger.read_stream(record_id)

    def object_path(self, record_id: str) -> Path:
        with self.factory(readonly=True) as uow:
            pointer = body.body_pointer(uow.conn(), record_id)
        assert pointer is not None
        return self.store.path_for(pointer.uri)


def build_world(db: DbTarget, tmp_path: Path) -> World:
    create_schema(db)
    factory = make_uow_factory(db)
    root = tmp_path / "types"
    shutil.copytree(FIXTURE_TYPES, root)
    source = attach(factory, ttl=0.0)
    assert source is not None
    return World(
        db=db,
        factory=factory,
        store=FsObjectStore(tmp_path / "objects", secret=b"test-secret"),
        root=root,
        source=source,
    )
