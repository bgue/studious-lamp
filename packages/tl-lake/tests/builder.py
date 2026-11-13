"""A small ledger builder for lake tests: records, pset values, links, edits and voids on SQLite."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from tl_adapters.db import create_schema, make_engine, open_uow, rebuild_projections
from tl_core.ledger import NewEvent
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

    db: str | Path  # a SQLite file or a postgresql:// URL (tl_adapters.db picks the adapter)
    versions: dict[str, int] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)
    scopes: dict[str, str] = field(default_factory=dict)  # record or link id to its scope

    @classmethod
    def create(cls, db: str | Path) -> LedgerBuilder:
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
        self.scopes[result.stream_id] = scope
        return result.stream_id

    def update(self, record_id: str, **changes: Any) -> None:
        with open_uow(self.db) as uow:
            result = handle_update_record(
                uow,
                UpdateRecord(
                    actor="user:u",
                    source="test",
                    scope=self.scopes[record_id],
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
                    scope=self.scopes[record_id],
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
                    scope=self.scopes[record_id],
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
                    scope=self.scopes[from_id],
                    from_id=from_id,
                    to_id=to_id,
                    relation=relation,
                ),
            )
        self.scopes[result.stream_id] = self.scopes[from_id]
        return result.stream_id

    def retract(self, link_id: str, reason: str = "wrong") -> None:
        with open_uow(self.db) as uow:
            handle_retract_link(
                uow,
                RetractLink(
                    actor="user:u",
                    source="test",
                    scope=self.scopes[link_id],
                    link_id=link_id,
                    reason=reason,
                ),
            )

    def rebuild_projections(self) -> None:
        rebuild_projections(self.db)

    def head(self) -> int:
        with open_uow(self.db, readonly=True) as uow:
            return uow.ledger.head_seq()

    def raw(
        self, record_id: str, stream_type: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        """Append one module event to the stream of an existing record, through the real
        projectors (the record is a ``core.Record`` standing in for an IWP or a stock lot)."""
        with open_uow(self.db) as uow:
            done = uow.append(
                stream_id=record_id,
                stream_type=stream_type,
                scope=self.scopes[record_id],
                expected_version=self.versions[record_id],
                events=[NewEvent(event_type=event_type, payload=payload)],
                actor="user:u",
                source="test",
                correlation_id=f"corr-{record_id}-{self.versions[record_id]}",
            )
        self.versions[record_id] = done.events[-1].stream_version

    def evaluate(
        self,
        iwp_id: str,
        *,
        today: str,
        ready: bool,
        checks: list[dict[str, Any]],
    ) -> None:
        """An ``IWP.ReadinessEvaluated`` on the stream of ``iwp_id``."""
        self.raw(
            iwp_id,
            "awp.IWP",
            "IWP.ReadinessEvaluated",
            {
                "iwp_id": iwp_id,
                "evaluated_at": f"{today}T08:00:00Z",
                "today": today,
                "ready": ready,
                "checks": checks,
                "facts_hash": "0" * 64,
                "feed_policy": "none",
            },
        )

    def move(self, lot_id: str, kind: str, qty: str, **more: Any) -> None:
        """A ``StockLot.Moved`` on the stream of ``lot_id`` (receive and issue are enough here)."""
        payload: dict[str, Any] = {"kind": kind, "qty": qty, "uom": "EA", **more}
        self.raw(lot_id, "materials.StockLot", "StockLot.Moved", payload)
