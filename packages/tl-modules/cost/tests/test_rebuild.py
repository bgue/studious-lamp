"""Replaying the ledger gives the tables the commands made (restore and rebuild, brief 24)."""

from __future__ import annotations

from typing import Any

from tl_adapters.db import rebuild_projections
from tl_mod_cost.testing import CostWorld, row

TABLES = (
    ("cur_cost_costcode", "id"),
    ("cur_cost_cost_snapshot", "id"),
    ("cur_cost_snapshot_value", "row_id"),
    ("cur_core_record", "id"),
)


def snapshot(world: CostWorld) -> dict[str, list[dict[str, Any]]]:
    return {t: world.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}


def test_a_rebuild_reproduces_every_cost_table(world: CostWorld) -> None:
    world.import_snapshot(
        [row("1", "Top", hours_budget=10), row("1-1", "Child", "1", uom="m", amount_budget=5.5)]
    )
    world.import_snapshot(
        [row("1", "Top, renamed", hours_budget=12), row("2", "New")],
        period="2026-08",
        as_of="2026-08-31",
    )
    world.import_snapshot([row("1", hours_budget=1)], period="2026-05", as_of="2026-05-31")
    before = snapshot(world)
    assert len(before["cur_cost_snapshot_value"]) == 5
    rebuild_projections(world.db)
    assert snapshot(world) == before
