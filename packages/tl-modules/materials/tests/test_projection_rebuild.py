"""Replay and rebuild-projections give the same rows in all twelve tables."""

from __future__ import annotations

import random
from decimal import ROUND_DOWN, Decimal

import acc_s2
import acc_s3
import pytest
from tl_adapters.db import rebuild_projections
from tl_mod_materials.handlers.movements import (
    AdjustStock,
    IssueStock,
    ReserveStock,
    ReturnStock,
    TransferStock,
    handle_adjust_stock,
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


def test_seeded_25_valid_movements_rebuild_the_stock_and_movement_rows(
    world3: acc_s3.World,
) -> None:
    """Random.Random(7): 25 valid receipts, issues, transfers, returns and adjusts (each admitted,
    chosen from the stock it can act on). The stock and movement rows after a rebuild equal the
    rows before it."""
    rng = random.Random(7)
    w = world3
    s = acc_s3.Stocked(w)
    lots = [(s.key1, s.lot1), (s.key2, s.lot2)]
    issued = {s.key1: Decimal(0), s.key2: Decimal(0)}  # issued net per lot key, for returns
    places = ["LA", "LB"]

    def qty(limit: Decimal) -> str | None:
        want = Decimal(rng.randint(1, 2500)) / Decimal(1000)
        got = min(want, limit).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
        return f"{got:.3f}" if got > 0 else None

    for _ in range(25):
        kind = rng.choice(["receipt", "issue", "transfer", "return", "adjust"])
        here = rng.choice(places)
        avail = {}
        for key, lot_id in lots:
            for place in places:
                found = w.balance(lot_id, place)
                avail[(key, place)] = found[2] if found is not None else Decimal(0)
        pick = [k for k, v in avail.items() if v > 0]
        if (
            kind == "receipt"
            or (kind != "return" and not pick)
            or (kind == "return" and not any(v > 0 for v in issued.values()))
        ):
            kind = "receipt"
        if kind == "receipt":
            q = qty(Decimal(20))
            assert q is not None
            made = w.deliver(
                [{"item_code": w.code("FLG"), "qty": q, "heat_no": "H-7781"}],
                location=here,
                mtr=True,
            )
            lot_id = w.lot(made.stream_id)
            key = w.lot_key(lot_id)
            lots.append((key, lot_id))
            issued[key] = Decimal(0)
        elif kind == "issue":
            key, place = rng.choice(pick)
            q = qty(avail[(key, place)])
            assert q is not None
            w.run(
                handle_issue_stock, IssueStock, movements=[acc_s3.mv(key, q, from_location=place)]
            )
            issued[key] += Decimal(q)
        elif kind == "transfer":
            key, place = rng.choice(pick)
            q = qty(avail[(key, place)])
            assert q is not None
            dest = places[1 - places.index(place)]
            w.run(
                handle_transfer_stock,
                TransferStock,
                movements=[acc_s3.mv(key, q, from_location=place, to_location=dest)],
            )
        elif kind == "return":
            key = rng.choice([k for k, v in issued.items() if v > 0])
            q = qty(issued[key])
            assert q is not None
            w.run(
                handle_return_stock,
                ReturnStock,
                movements=[acc_s3.mv(key, q, to_location=here)],
            )
            issued[key] -= Decimal(q)
        else:  # adjust out of stock, by the superuser
            key, place = rng.choice(pick)
            q = qty(avail[(key, place)])
            assert q is not None
            w.run(
                handle_adjust_stock,
                AdjustStock,
                actor=acc_s3.SUPER,
                movements=[acc_s3.mv(key, q, direction="out", from_location=place, reason="count")],
            )
    before_stock = w.rows("SELECT * FROM cur_materials_stock ORDER BY lot_id, location_id")
    before_moves = w.rows("SELECT * FROM cur_materials_movement ORDER BY seq")
    assert len(before_moves) >= 25 and before_stock
    rebuild_projections(w.target)
    assert w.rows("SELECT * FROM cur_materials_stock ORDER BY lot_id, location_id") == before_stock
    assert w.rows("SELECT * FROM cur_materials_movement ORDER BY seq") == before_moves
