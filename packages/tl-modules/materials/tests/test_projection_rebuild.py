"""Replay and rebuild-projections give the same rows in all twelve tables."""

from __future__ import annotations

import acc_s2
import acc_s3


def test_replay_decimal_and_zero_rows(world2: acc_s2.World) -> None:
    acc_s2.check_replay(world2)


def test_rebuild_reproduces_every_table(world2: acc_s2.World) -> None:
    acc_s2.check_rebuild(world2)


def test_rebuild_after_receipts_and_movements(world3: acc_s3.World) -> None:
    acc_s3.check_rebuild(world3)
