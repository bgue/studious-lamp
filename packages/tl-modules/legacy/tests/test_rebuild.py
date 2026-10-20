"""Replaying the ledger gives the load run table the stages made (restore and rebuild, brief 24)."""

from __future__ import annotations

from typing import Any

from tl_adapters.db import rebuild_projections
from tl_mod_legacy.testing import ADMIN, PROJECT, LegacyWorld, tag_csv

TABLES = (("cur_legacy_load_run", "id"), ("cur_core_record", "id"))


def snapshot(world: LegacyWorld) -> dict[str, list[dict[str, Any]]]:
    return {t: world.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}


def test_a_rebuild_reproduces_the_run_table_in_every_state(world: LegacyWorld) -> None:
    done = world.loaded("test-tags", "a.csv", tag_csv(4))
    world.service.reconcile(PROJECT, done.key, actor=ADMIN)
    world.service.bronze(PROJECT, done.key, actor=ADMIN)
    undone = world.loaded("test-tags", "b.csv", tag_csv(3, start=10))
    world.service.compensate(PROJECT, undone.key, actor=ADMIN, reason="wrong file")
    voided = world.open("test-tags", "c.csv", tag_csv(2))
    world.service.void(PROJECT, voided.key, actor=ADMIN, reason="wrong file")
    world.open("test-tags", "d.csv", tag_csv(2))  # left Opened
    before = snapshot(world)
    states = {r["source_name"]: r for r in world.rows("SELECT * FROM v_legacy_load_run")}
    assert len(states) == 4
    rebuild_projections(world.db)
    assert snapshot(world) == before
