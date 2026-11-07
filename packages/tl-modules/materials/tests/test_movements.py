"""Movements: issue, transfer, return, adjust, scrap, reserve; bounds; concurrent issues."""

from __future__ import annotations

import acc_s3


def test_issue_transfer_return_refusals(world3: acc_s3.World) -> None:
    acc_s3.check_issue_and_transfer(world3)


def test_adjust_scrap_reserve_bounds(world3: acc_s3.World) -> None:
    acc_s3.check_adjust_scrap_reserve(world3)


def test_batches_and_quantities(world3: acc_s3.World) -> None:
    acc_s3.check_batches_and_quantities(world3)


def test_two_concurrent_issues_one_wins_one_refused(world3: acc_s3.World) -> None:
    acc_s3.check_concurrent_issues(world3)
