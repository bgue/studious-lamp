"""Replay and rebuild-projections give the same rows in all twelve tables."""

from __future__ import annotations

import random

import acc_s2
import acc_s3
import pytest
from tl_adapters.db import rebuild_projections
from tl_mod_materials.handlers.movements import (
    IssueStock,
    ReserveStock,
    ReturnStock,
    TransferStock,
    handle_issue_stock,
    handle_reserve_stock,
    handle_return_stock,
    handle_transfer_stock,
)


def test_replay_decimal_and_zero_rows(world2: acc_s2.World) -> None:
    acc_s2.check_replay(world2)


def test_rebuild_reproduces_every_table(world2: acc_s2.World) -> None:
    acc_s2.check_rebuild(world2)


def test_rebuild_after_receipts_and_movements(world3: acc_s3.World) -> None:
    acc_s3.check_rebuild(world3)


@pytest.mark.parametrize("seed", range(6))
def test_seeded_random_movements_rebuild_to_the_live_rows(world3: acc_s3.World, seed: int) -> None:
    """A seeded loop of transfers, issues, returns and reserves (refused ones included): the rows
    rebuilt from the events equal the live rows in every table, and a refused step adds no event."""
    rng = random.Random(seed)
    w = world3
    s = acc_s3.Stocked(w)
    keys, places = [s.key1, s.key2], ["LA", "LB"]
    done = 0
    for _ in range(24):
        key, here = rng.choice(keys), rng.choice(["LA", "LA", "LB"])
        there = places[1 - places.index(here)]
        qty = f"{rng.randint(1, 2500) / 1000:.3f}"
        kind = rng.choice(["transfer", "issue", "return", "reserve"])
        if kind == "transfer":
            args = (
                handle_transfer_stock,
                TransferStock,
                [acc_s3.mv(key, qty, from_location=here, to_location=there)],
            )
        elif kind == "issue":
            args = (handle_issue_stock, IssueStock, [acc_s3.mv(key, qty, from_location=here)])
        elif kind == "return":
            args = (handle_return_stock, ReturnStock, [acc_s3.mv(key, qty, to_location=here)])
        else:
            args = (
                handle_reserve_stock,
                ReserveStock,
                [acc_s3.mv(key, qty, from_location=here, mto_line_id=s.line)],
            )
        before = w.events()
        try:
            w.run(args[0], args[1], movements=args[2])
        except Exception:
            assert w.events() == before, f"seed {seed}: a refused {kind} wrote events"
        else:
            done += 1
    assert done >= 2, f"seed {seed}: only {done} steps were admitted"
    live = acc_s3.snapshot(w)
    assert live["cur_materials_movement"]
    rebuild_projections(w.target)
    assert acc_s3.snapshot(w) == live, f"seed {seed}: the rebuilt rows differ from the live rows"
