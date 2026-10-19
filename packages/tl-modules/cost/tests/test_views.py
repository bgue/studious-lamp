"""The reads of the cost module: codes, their history and the snapshots (P1-I4)."""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_mod_cost import views
from tl_mod_cost.errors import CostCodeNotFoundError
from tl_mod_cost.testing import PROJECT, CostWorld, row


@pytest.fixture
def filled(world: CostWorld) -> CostWorld:
    world.import_snapshot(
        [
            row("4210", "Piping", hours_budget=1000, hours_actual=400),
            row("4210-PIP", "Pipe installation", "4210", hours_budget=600, uom="in-dia"),
            row("4210-WLD", "Welding", "4210", hours_budget=400),
            row("5100", "Electrical", amount_budget=90000),
        ],
        period="2026-06",
        as_of="2026-06-30",
    )
    world.import_snapshot(
        [row("4210-PIP", hours_budget=600, hours_actual=150)], period="2026-07", as_of="2026-07-31"
    )
    return world


def read(world: CostWorld, function, *args, **kwargs):  # noqa: ANN001, ANN201
    with open_uow(world.db, readonly=True) as uow:
        return function(uow.conn(), PROJECT, *args, **kwargs)


def test_codes_come_by_code_with_the_latest_figures_stated(filled: CostWorld) -> None:
    codes = read(filled, views.cost_codes)
    assert [c.code for c in codes] == ["4210", "4210-PIP", "4210-WLD", "5100"]
    pip = codes[1]
    assert (pip.title, pip.parent_code, pip.level, pip.uom) == (
        "Pipe installation", "4210", 2, "in-dia",
    )  # fmt: skip
    assert (pip.period, pip.as_of) == ("2026-07", "2026-07-31")
    assert pip.figures["hours_actual"] == 150 and pip.figures["amount_budget"] is None
    assert codes[0].period == "2026-06"  # not in the second file: its figures are the first's


def test_codes_are_filtered_by_parent_and_by_text(filled: CostWorld) -> None:
    assert [c.code for c in read(filled, views.cost_codes, parent="4210")] == [
        "4210-PIP",
        "4210-WLD",
    ]
    assert [c.code for c in read(filled, views.cost_codes, search="WELD")] == ["4210-WLD"]
    assert [c.code for c in read(filled, views.cost_codes, search="4210-p")] == ["4210-PIP"]
    assert read(filled, views.cost_codes, search="nothing") == []
    assert [c.code for c in read(filled, views.cost_codes, limit=2)] == ["4210", "4210-PIP"]
    assert len(read(filled, views.cost_codes, limit=0)) == 1


def test_one_code_comes_with_its_children_and_every_snapshot_that_stated_it(
    filled: CostWorld,
) -> None:
    detail = read(filled, views.cost_code_detail, "4210-PIP")
    assert detail.children == []
    assert [(h.period, h.revision, h.as_of) for h in detail.history] == [
        ("2026-06", 1, "2026-06-30"),
        ("2026-07", 1, "2026-07-31"),
    ]
    assert [h.figures["hours_actual"] for h in detail.history] == [None, 150.0]
    parent = read(filled, views.cost_code_detail, "4210")
    assert parent.children == ["4210-PIP", "4210-WLD"]
    with pytest.raises(CostCodeNotFoundError):
        read(filled, views.cost_code_detail, "9999")


def test_snapshots_come_newest_first_with_what_they_did(filled: CostWorld) -> None:
    snapshots = read(filled, views.cost_snapshots)
    assert [(s.key, s.row_count, s.new_code_count) for s in snapshots] == [
        ("2026-07@1", 1, 0),
        ("2026-06@1", 4, 4),
    ]
    assert snapshots[0].as_of == "2026-07-31"
