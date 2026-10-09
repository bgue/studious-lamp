"""Embedded `ClientInterface`: calls `tl_core` services in process (brief 4, local mode).

Each call opens one unit of work (read-only for queries), runs one service function, and closes
it. There is no logic here beyond that; the remote client (P0-I4) is the same interface over HTTP.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Literal

from tl_core.ledger import Event
from tl_core.services import psets, queries
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.psets import SetPsetValues
from tl_core.services.records import handle_create_record, handle_update_record
from tl_core.uow import UnitOfWork
from tl_schema.forms import ConformanceReport, FormMetadata

# A callable that opens a unit of work: `factory(readonly)` returns a context manager yielding it.
UowFactory = Callable[[bool], AbstractContextManager[UnitOfWork]]


def sqlite_uow_factory(path: str | Path) -> UowFactory:
    """A factory over the SQLite dev ledger at ``path`` (one engine per unit of work)."""
    from tl_adapters.sqlite.uow import open_uow

    db = Path(path)

    def factory(readonly: bool) -> AbstractContextManager[UnitOfWork]:
        return open_uow(db, readonly=readonly)

    return factory


class EmbeddedClient:
    """`ClientInterface` over in-process services. Errors from the services propagate unchanged."""

    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow = uow_factory

    @classmethod
    def for_sqlite(cls, path: str | Path) -> EmbeddedClient:
        return cls(sqlite_uow_factory(path))

    def list_records(
        self,
        scope: str,
        *,
        record_type: str | None = None,
        status: str | None = None,
        include_voided: bool = False,
        limit: int = 500,
        offset: int = 0,
        order_by: list[tuple[str, Literal["asc", "desc"]]] | None = None,
    ) -> list[dict[str, Any]]:
        with self._uow(True) as uow:
            return queries.list_records(
                uow,
                scope,
                status=status,
                include_voided=include_voided,
                record_type=record_type,
                limit=limit,
                offset=offset,
                order_by=order_by,
            )

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None:
        with self._uow(True) as uow:
            return queries.get_record(uow, scope, key)

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None:
        with self._uow(True) as uow:
            return queries.get_record_by_id(uow, record_id)

    def history(self, record_id: str) -> list[Event]:
        with self._uow(True) as uow:
            return queries.record_history(uow, record_id)

    def create_record(self, cmd: CreateRecord) -> CommandResult:
        with self._uow(False) as uow:
            return handle_create_record(uow, cmd)

    def update_record(self, cmd: UpdateRecord) -> CommandResult:
        with self._uow(False) as uow:
            return handle_update_record(uow, cmd)

    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult:
        with self._uow(False) as uow:
            return psets.handle_set_pset_values(uow, cmd)

    def form_metadata(self, scope: str, record_type: str) -> FormMetadata:
        with self._uow(True) as uow:
            return psets.form_metadata(uow, scope, record_type)

    def conformance(self, record_id: str) -> ConformanceReport:
        with self._uow(True) as uow:
            return psets.conformance(uow, record_id)
