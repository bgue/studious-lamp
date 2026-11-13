"""``mart_materials``: movements by scope, month and kind, with today's stock (P2-I6 T02).

Copy this file to ``packages/tl-lake/tests/test_mart_materials.py``. It builds the silver rows the
model may read (``cur_materials_movement``: ``seq``, ``scope``, ``lot_id``, ``kind``, ``qty``,
``cost_code_id``, ``recorded_at``; ``cur_materials_stock``: ``scope``, ``lot_id``, ``on_hand``) in
a temporary lake by direct INSERT, runs ``build_gold_marts`` and pins ``SELECT *``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_lake import LakeConfig
from tl_lake.duck import Duck, open_lake
from tl_lake.gold import build_gold_marts

P1, P2 = "project:P1", "project:P2"
MART = "mart_materials"
COLUMNS = [
    "scope", "period", "kind", "movements", "lots", "qty", "cost_codes", "on_hand_now",
    "lots_in_stock_now",
]  # fmt: skip


@pytest.fixture
def con(tmp_path: Path) -> Iterator[Duck]:
    with open_lake(LakeConfig.at(tmp_path / "lake"), write=True) as opened:
        opened.execute(
            "CREATE TABLE lake.main.cur_materials_movement (seq BIGINT, scope VARCHAR, "
            "lot_id VARCHAR, kind VARCHAR, qty DOUBLE, cost_code_id VARCHAR, recorded_at VARCHAR)"
        )
        opened.execute(
            "CREATE TABLE lake.main.cur_materials_stock (scope VARCHAR, lot_id VARCHAR, "
            "location_id VARCHAR, on_hand DOUBLE, reserved DOUBLE, available DOUBLE)"
        )
        yield opened


def move(
    con: Duck, seq: int, kind: str, lot: str, qty: float, at: str,
    scope: str = P1, cost_code: str | None = None,
) -> None:  # fmt: skip
    con.execute(
        "INSERT INTO lake.main.cur_materials_movement VALUES (?, ?, ?, ?, ?, ?, ?)",
        [seq, scope, lot, kind, qty, cost_code, at],
    )


def stock(con: Duck, lot: str, on_hand: float, scope: str = P1, location: str = "L1") -> None:
    con.execute(
        "INSERT INTO lake.main.cur_materials_stock VALUES (?, ?, ?, ?, 0, ?)",
        [scope, lot, location, on_hand, on_hand],
    )


def rows(con: Duck) -> list[tuple[Any, ...]]:
    build_gold_marts(con)
    return con.execute(f"SELECT * FROM lake.main.{MART} ORDER BY scope, period, kind").fetchall()


def test_no_movement_leaves_an_empty_table_with_the_contract_columns(con: Duck) -> None:
    stock(con, "LOT-1", 5)
    assert rows(con) == []
    described = con.execute(f"SELECT * FROM lake.main.{MART}").description
    assert [d[0] for d in described] == COLUMNS


def test_one_row_per_scope_period_and_kind_with_distinct_lots_and_cost_codes(con: Duck) -> None:
    at = "2026-10-05T09:00:00.000000+00:00"
    move(con, 1, "receive", "LOT-1", 10, at)
    move(con, 2, "receive", "LOT-2", 4.5, at)
    move(con, 3, "issue", "LOT-1", 3, at, cost_code="CC-1")
    move(con, 4, "issue", "LOT-1", 2, at, cost_code="CC-1")
    move(con, 5, "issue", "LOT-2", 1, at, cost_code="CC-2")
    move(con, 6, "issue", "LOT-2", 1, at)  # no cost code: not counted as one
    stock(con, "LOT-1", 5)
    stock(con, "LOT-2", 2.5)
    assert rows(con) == [
        (P1, "2026-10", "issue", 4, 2, 7.0, 2, 7.5, 2),
        (P1, "2026-10", "receive", 2, 2, 14.5, 0, 7.5, 2),
    ]


def test_a_movement_at_the_end_of_a_month_belongs_to_that_month(con: Duck) -> None:
    move(con, 1, "receive", "LOT-1", 1, "2026-09-30T23:59:59.999999+00:00")
    move(con, 2, "receive", "LOT-1", 2, "2026-10-01T00:00:00.000000+00:00")
    move(con, 3, "receive", "LOT-1", 4, "2027-01-31T12:00:00.000000+00:00")
    assert [(r[1], r[2], r[3], r[5]) for r in rows(con)] == [
        ("2026-09", "receive", 1, 1.0),
        ("2026-10", "receive", 1, 2.0),
        ("2027-01", "receive", 1, 4.0),
    ]


def test_scopes_are_split_and_each_takes_its_own_stock_totals(con: Duck) -> None:
    at = "2026-10-05T09:00:00.000000+00:00"
    move(con, 1, "receive", "A-1", 10, at, scope=P1)
    move(con, 2, "receive", "B-1", 7, at, scope=P2)
    move(con, 3, "issue", "B-1", 2, at, scope=P2, cost_code="CC-9")
    stock(con, "A-1", 10, scope=P1)
    stock(con, "A-1", 3, scope=P1, location="L2")  # one lot at two locations
    stock(con, "B-1", 5, scope=P2)
    assert rows(con) == [
        (P1, "2026-10", "receive", 1, 1, 10.0, 0, 13.0, 1),
        (P2, "2026-10", "issue", 1, 1, 2.0, 1, 5.0, 1),
        (P2, "2026-10", "receive", 1, 1, 7.0, 0, 5.0, 1),
    ]


def test_a_scope_with_movements_and_no_stock_shows_zero(con: Duck) -> None:
    move(con, 1, "scrap", "LOT-1", 2, "2026-10-05T09:00:00.000000+00:00")
    assert rows(con) == [(P1, "2026-10", "scrap", 1, 1, 2.0, 0, 0.0, 0)]
