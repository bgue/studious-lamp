"""Receipts: create, revise, inspect, the MTR guard, accept into lots, no void after accept."""

from __future__ import annotations

import acc_s3


def test_receipt_life_and_the_mtr_guard(world3: acc_s3.World) -> None:
    acc_s3.check_receipts(world3)


def test_views_take_off_shortages_reservations(world3: acc_s3.World) -> None:
    acc_s3.check_views(world3)
