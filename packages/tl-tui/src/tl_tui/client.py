"""The client interface every TUI screen uses (P0-I2 contract; brief 4, 10).

Screens never import tl_core services directly. The embedded implementation (P0-I2) calls tl_core in
process; the remote implementation (P0-I4) calls the API. Same methods, same return shapes.
"""

from __future__ import annotations

from typing import Any, Protocol

from tl_core.ledger import Event
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.psets import SetPsetValues
from tl_schema.forms import ConformanceReport, FormMetadata


class ClientInterface(Protocol):
    def list_records(
        self,
        scope: str,
        *,
        record_type: str | None = None,
        status: str | None = None,
        include_voided: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None: ...

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None: ...

    def history(self, record_id: str) -> list[Event]: ...

    def create_record(self, cmd: CreateRecord) -> CommandResult: ...

    def update_record(self, cmd: UpdateRecord) -> CommandResult: ...

    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult: ...

    def form_metadata(self, scope: str, record_type: str) -> FormMetadata: ...

    def conformance(self, record_id: str) -> ConformanceReport: ...
