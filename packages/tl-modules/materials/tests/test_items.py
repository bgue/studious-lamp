"""Item library: define, adopt, revise, retire (spec section 2)."""

from __future__ import annotations

import acc_s2


def test_define_adopt_revise_retire(world2: acc_s2.World) -> None:
    acc_s2.check_items(world2)


def test_module_registers_its_words_and_record_types(world2: acc_s2.World) -> None:
    acc_s2.check_module(world2)
