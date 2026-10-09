"""A small ledger builder for lake tests: records, pset values, links, edits and voids on SQLite."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.uow import create_schema, open_uow, rebuild_projections
from tl_core.services.commands import CreateRecord, UpdateRecord, VoidRecord
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import (
    handle_create_record,
    handle_update_record,
    handle_void_record,
)

SCOPE = "project:P123"
OTHER_SCOPE = "project:P777"


@dataclass
class LedgerBuilder:
    """Appends to the SQLite ledger at ``db`` and remembers versions so tests stay short."""

    db: Path
    versions: dict[str, int] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(cls, db: Path) -> LedgerBuilder:
        create_schema(db)
        return cls(db)

    def engine(self) -> Engine:
        return make_engine(self.db)

    def record(self, key: str, *, title: str | None = None, scope: str = SCOPE) -> str:
        with open_uow(self.db) as uow:
            result = handle_create_record(
                uow,
                CreateRecord(
                    actor="user:u",
                    source="test",
                    scope=scope,
                    record_type="core.Record",
                    title=title or f"Record {key}",
                    key=key,
                ),
            )
        self.versions[result.stream_id] = result.version
        self.keys[key] = result.stream_id
        return result.stream_id

    def update(self, record_id: str, **changes: Any) -> None:
        with open_uow(self.db) as uow:
            result = handle_update_record(
                uow,
                UpdateRecord(
                    actor="user:u",
                    source="test",
                    scope=SCOPE,
                    stream_id=record_id,
                    expected_version=self.versions[record_id],
                    changes=changes,
                ),
            )
        self.versions[record_id] = result.version

    def void(self, record_id: str, reason: str = "duplicate") -> None:
        with open_uow(self.db) as uow:
            result = handle_void_record(
                uow,
                VoidRecord(
                    actor="user:u",
                    source="test",
                    scope=SCOPE,
                    stream_id=record_id,
                    expected_version=self.versions[record_id],
                    reason=reason,
                ),
            )
        self.versions[record_id] = result.version

    def values(self, record_id: str, pset: str, values: dict[str, Any]) -> None:
        with open_uow(self.db) as uow:
            result = handle_set_pset_values(
                uow,
                SetPsetValues(
                    actor="user:u",
                    source="test",
                    scope=SCOPE,
                    stream_id=record_id,
                    expected_version=self.versions[record_id],
                    pset=pset,
                    layer="standard",
                    values=values,
                ),
            )
        self.versions[record_id] = result.version

    def link(self, from_id: str, to_id: str, relation: str | None = None) -> str:
        with open_uow(self.db) as uow:
            result = handle_add_link(
                uow,
                AddLink(
                    actor="user:u",
                    source="test",
                    scope=SCOPE,
                    from_id=from_id,
                    to_id=to_id,
                    relation=relation,
                ),
            )
        return result.stream_id

    def retract(self, link_id: str, reason: str = "wrong") -> None:
        with open_uow(self.db) as uow:
            handle_retract_link(
                uow,
                RetractLink(
                    actor="user:u", source="test", scope=SCOPE, link_id=link_id, reason=reason
                ),
            )

    def rebuild_projections(self) -> None:
        rebuild_projections(self.db)

    def head(self) -> int:
        with open_uow(self.db, readonly=True) as uow:
            return uow.ledger.head_seq()
