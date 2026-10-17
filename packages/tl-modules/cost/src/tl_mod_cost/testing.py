"""Test support other packages share: a ledger and the cost commands, one call per test step.

``CostWorld`` wraps a ledger target and opens a unit of work per call, like a real command. It is
not registered anywhere and never runs in production.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import CommandResult

from tl_mod_cost import registry
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot, handle_import_cost_snapshot
from tl_mod_cost.imports.model import CostRow

PROJECT = "project:P123"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": PROJECT}


def row(
    code: str, description: str | None = None, parent: str | None = None, **more: Any
) -> CostRow:
    """A row of a cost file. Figures are keyword arguments (``hours_budget=100``); ``uom`` too."""
    uom = more.pop("uom", None)
    return CostRow(
        code=code,
        description=description,
        parent_code=parent,
        uom=uom,
        figures={k: float(v) for k, v in more.items()},
    )


class CostWorld:
    def __init__(self, db: DbTarget) -> None:
        self.db = db

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def code(self, code: str) -> registry.CostCodeRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.get_cost_code(uow.conn(), PROJECT, code)
        assert found is not None
        return found

    def snapshots(self) -> list[registry.CostSnapshotRow]:
        with open_uow(self.db, readonly=True) as uow:
            return registry.list_snapshots(uow.conn(), PROJECT)

    def history(self, code: str) -> list[registry.ValueRow]:
        found = self.code(code)
        with open_uow(self.db, readonly=True) as uow:
            return registry.code_history(uow.conn(), found.id)

    def import_snapshot(
        self,
        rows: list[CostRow],
        *,
        period: str = "2026-07",
        as_of: str = "2026-07-31",
        **more: Any,
    ) -> CommandResult:
        command = ImportCostSnapshot(**{**BASE, **more}, period=period, as_of=as_of, rows=rows)
        with open_uow(self.db) as uow:
            return handle_import_cost_snapshot(uow, command)
