"""Record reads, queries and record commands over HTTP (T46).

Same method names, parameters and return shapes as ``tl_tui.client.ClientInterface``: a record is
the envelope ``dict`` the embedded client returns, history is a list of ``Event``, commands return
``CommandResult``. ``get_record`` and ``get_record_by_id`` answer ``None`` and ``history`` answers
``[]`` for an unknown record, as the embedded client does; every other failure raises the same
exception class as an embedded call (see ``ApiClientBase``).
"""

from __future__ import annotations

from typing import Any, Literal

from tl_core.actions import RecordActions
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import Event
from tl_core.services.commands import Command, CommandResult, CreateRecord, UpdateRecord
from tl_core.services.edit import EditRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.psets import SetPsetValues
from tl_mod_documents.commands import API_COMMANDS as DOCUMENT_COMMANDS
from tl_mod_engineering.commands import API_COMMANDS as ENGINEERING_COMMANDS

from tl_api.client.base import ApiClientBase, quote

OrderBy = list[tuple[str, Literal["asc", "desc"]]]


def format_order_by(order_by: OrderBy | None) -> str | None:
    """``[("title", "desc"), ("key", "asc")]`` to ``"title:desc,key:asc"``; empty gives ``None``."""
    if not order_by:
        return None
    return ",".join(f"{column}:{direction}" for column, direction in order_by)


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
        return self._get_json(
            "/records",
            {
                "scope": scope,
                "record_type": record_type,
                "status": status,
                "include_voided": include_voided,
                "limit": limit,
                "offset": offset,
                "order_by": format_order_by(order_by),
            },
        )

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
        return self._get_json(
            "/records",
            {
                "scope": scope,
                "q": q,
                "limit": limit,
                "offset": offset,
                "order_by": format_order_by(order_by),
            },
        )

    def count_records(self, scope: str, q: str) -> int:
        """How many records match ``q`` (``GET /records/count``)."""
        return int(self._get_json("/records/count", {"scope": scope, "q": q})["count"])

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None:
        """The record with this key in ``scope``, or ``None``."""
        try:
            return self._get_json("/records/lookup", {"scope": scope, "key": key})
        except RecordNotFoundError:
            return None

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None:
        """The record with this id, or ``None``."""
        try:
            return self._get_json(f"/records/{quote(record_id)}")
        except RecordNotFoundError:
            return None

    def history(self, record_id: str) -> list[Event]:
        """Every event of the record's stream, oldest first; ``[]`` for an unknown record."""
        try:
            return self._models(Event, self._get_json(f"/records/{quote(record_id)}/history"))
        except RecordNotFoundError:
            return []

    def create_record(self, cmd: CreateRecord) -> CommandResult:
        return self._command("CreateRecord", cmd)

    def update_record(self, cmd: UpdateRecord) -> CommandResult:
        return self._command("UpdateRecord", cmd)

    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult:
        return self._command("SetPsetValues", cmd)

    def edit_record(self, cmd: EditRecord) -> CommandResult:
        """Field changes and pset edits as one atomic save: all of them are applied or none."""
        return self._command("EditRecord", cmd)

    def allowed_actions(self, record_id: str) -> RecordActions:
        """What the caller may do on the record now (``GET /records/{id}/actions``).

        Raises ``RecordNotFoundError`` for a record that is missing or that the caller may not
        read, as the embedded client does. An agent token is offered nothing.
        """
        return self._model(RecordActions, self._get_json(f"/records/{quote(record_id)}/actions"))

    def document_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a documents command by name (``POST /commands/{name}``); the token's actor is used.

        A name that is not in the documents module's command table is refused here, as the
        embedded client refuses it (``ForbiddenError``); the server then checks the access.
        """
        _require_listed(name, cmd, DOCUMENT_COMMANDS, "documents")
        return self._command(name, cmd)

    def engineering_command(self, name: str, cmd: Command) -> CommandResult:
        """Run an engineering command by name; the same rules as :meth:`document_command`."""
        _require_listed(name, cmd, ENGINEERING_COMMANDS, "engineering")
        return self._command(name, cmd)


def _require_listed(name: str, cmd: Command, table: Any, module: str) -> None:
    """Refuse a command that is not a row of the module's table, or whose class is not the row's."""
    spec = next((row for row in table if row.model.__name__ == name), None)
    if spec is None or type(cmd) is not spec.model:
        raise ForbiddenError(f"{name} is not a {module} command")
