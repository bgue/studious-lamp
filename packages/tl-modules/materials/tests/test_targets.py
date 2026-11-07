"""Load targets for items, locations and PO lines; the class filter on a hidden lot."""

from __future__ import annotations

import acc_s2


def test_load_targets_plan_apply_compare_reverse(world2: acc_s2.World) -> None:
    acc_s2.check_targets(world2)


def test_lowest_clearance_reads_nothing_of_a_hidden_lot(world2: acc_s2.World) -> None:
    acc_s2.check_class_filter(world2)
