"""Record reads, queries and record commands over HTTP (T46).

STUB (P0-I4-T46): function bodies below raise ``NotImplementedError``. Names, signatures and
docstrings are final; implement the bodies, then delete this paragraph.

Same method names, parameters and return shapes as ``tl_tui.client.ClientInterface``: a record is
the envelope ``dict`` the embedded client returns, history is a list of ``Event``, commands return
``CommandResult``. ``get_record`` and ``get_record_by_id`` answer ``None`` and ``history`` answers
``[]`` for an unknown record, as the embedded client does; every other failure raises the same
exception class as an embedded call (see ``ApiClientBase``).
"""

from __future__ import annotations

from typing import Any, Literal

from tl_core.ledger import Event
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.edit import EditRecord
from tl_core.services.psets import SetPsetValues

from tl_api.client.base import ApiClientBase

OrderBy = list[tuple[str, Literal["asc", "desc"]]]


def format_order_by(order_by: OrderBy | None) -> str | None:
    """``[("title", "desc"), ("key", "asc")]`` to ``"title:desc,key:asc"``; empty gives ``None``."""
    raise NotImplementedError("STUB (P0-I4-T46)")


class RecordsApi(ApiClientBase):
    def list_records(
        self,
        scope: str,
        *,
        record_type: str | None = None,
        status: str | None = None,
        include_voided: bool = False,
        limit: int = 500,
        offset: int = 0,
        order_by: OrderBy | None = None,
    ) -> list[dict[str, Any]]:
        """Records of ``scope`` (``GET /records``), as envelope dicts."""
        raise NotImplementedError("STUB (P0-I4-T46)")

    def query_records(
        self,
        scope: str,
        q: str,
        *,
        limit: int = 500,
        offset: int = 0,
        order_by: OrderBy | None = None,
    ) -> list[dict[str, Any]]:
        """Records matching the query text ``q``; ``QuerySyntaxError`` carries the ``position``."""
        raise NotImplementedError("STUB (P0-I4-T46)")

    def count_records(self, scope: str, q: str) -> int:
        """How many records match ``q`` (``GET /records/count``)."""
        raise NotImplementedError("STUB (P0-I4-T46)")

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None:
        """The record with this key in ``scope``, or ``None``."""
        raise NotImplementedError("STUB (P0-I4-T46)")

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None:
        """The record with this id, or ``None``."""
        raise NotImplementedError("STUB (P0-I4-T46)")

    def history(self, record_id: str) -> list[Event]:
        """Every event of the record's stream, oldest first; ``[]`` for an unknown record."""
        raise NotImplementedError("STUB (P0-I4-T46)")

    def create_record(self, cmd: CreateRecord) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T46)")

    def update_record(self, cmd: UpdateRecord) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T46)")

    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T46)")

    def edit_record(self, cmd: EditRecord) -> CommandResult:
        """Field changes and pset edits as one atomic save: all of them are applied or none."""
        raise NotImplementedError("STUB (P0-I4-T46)")
