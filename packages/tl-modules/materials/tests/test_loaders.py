"""The three materials loaders run on the sample files (T01b)."""

from __future__ import annotations

from pathlib import Path

import acc_t01b
from tl_adapters.db import as_target, create_schema
from tl_lake import LakeConfig
from tl_mod_legacy.testing import LegacyWorld


def test_three_loaders_load_and_reconcile(tmp_path: Path) -> None:
    target = as_target(tmp_path / "ledger.db")
    create_schema(target)
    world = LegacyWorld(target, tmp_path / "objects", lake=LakeConfig.at(tmp_path / "lake"))
    state: dict = {}
    for check in (
        acc_t01b.check_loaders_found,
        acc_t01b.check_items_plan,
        acc_t01b.check_items_load,
        acc_t01b.check_items_reconcile,
        acc_t01b.check_items_second_run,
        acc_t01b.check_locations_load,
        acc_t01b.check_po_lines_load,
        acc_t01b.check_items_refused_in_project,
    ):
        check(world, state)
