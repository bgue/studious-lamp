"""Location tree: depth 5, a single root, retire guarded by stock."""

from __future__ import annotations

import acc_s2


def test_depth_root_and_retire(world2: acc_s2.World) -> None:
    acc_s2.check_locations(world2)


def test_po_lines_adopt_and_check_quantity(world2: acc_s2.World) -> None:
    acc_s2.check_po_lines(world2)
