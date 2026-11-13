"""Materials silver: movements append by seq, stock is replaced whole (P2-I6-S1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from builder import LedgerBuilder
from lakecheck import assert_lake_matches_ledger, do_sync
from tl_lake import LakeConfig
from tl_lake.duck import open_lake
from tl_lake.ingest import insert_rows

MOVEMENT = "cur_materials_movement"
STOCK = "cur_materials_stock"


@pytest.fixture
def inserted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[Any]]]:
    """``(table, keys)`` of every bulk insert the sync makes into the two materials tables."""
    log: list[tuple[str, list[Any]]] = []
    real: Callable[..., int] = insert_rows

    def spy(con: Any, table: str, columns: Any, rows: Any, tmp: Any, **more: Any) -> int:
        taken = list(rows)
        if table == MOVEMENT:
            log.append((table, [r["seq"] for r in taken]))
        elif table == STOCK:
            log.append((table, sorted(r["lot_id"] for r in taken)))
        return real(con, table, columns, taken, tmp, **more)

    monkeypatch.setattr("tl_lake.sync.insert_rows", spy)
    return log


def rows(lake: LakeConfig, sql: str) -> list[tuple[Any, ...]]:
    with open_lake(lake, write=False) as con:
        return con.execute(sql).fetchall()


def test_movements_append_by_seq_and_an_old_row_is_never_copied_again(
    ledger: LedgerBuilder, lake: LakeConfig, inserted: list[tuple[str, list[Any]]]
) -> None:
    lot = ledger.record("LOT-1")
    ledger.move(lot, "receive", "10", to_location_id="L1")
    ledger.move(lot, "scrap", "1", from_location_id="L1")
    do_sync(ledger, lake)
    first = [k for t, k in inserted if t == MOVEMENT]
    assert first == [[ledger.head() - 1, ledger.head()]]

    inserted.clear()
    ledger.move(lot, "receive", "5", to_location_id="L1")
    do_sync(ledger, lake)
    assert [k for t, k in inserted if t == MOVEMENT] == [[ledger.head()]]
    assert len(rows(lake, f"SELECT seq FROM {MOVEMENT}")) == 3
    assert rows(lake, f"SELECT count(DISTINCT seq) FROM {MOVEMENT}") == [(3,)]
    assert_lake_matches_ledger(ledger, lake)


def test_a_sync_with_no_new_movement_copies_none(
    ledger: LedgerBuilder, lake: LakeConfig, inserted: list[tuple[str, list[Any]]]
) -> None:
    lot = ledger.record("LOT-1")
    ledger.move(lot, "receive", "10", to_location_id="L1")
    do_sync(ledger, lake)
    inserted.clear()
    ledger.update(lot, title="renamed")
    do_sync(ledger, lake)
    assert [k for t, k in inserted if t == MOVEMENT] == []
    assert rows(lake, f"SELECT count(*) FROM {MOVEMENT}") == [(1,)]


def test_stock_is_replaced_whole_so_a_lot_that_reaches_zero_leaves_no_row(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    gone, kept = ledger.record("LOT-G"), ledger.record("LOT-K")
    ledger.move(gone, "receive", "5", to_location_id="L1")
    ledger.move(kept, "receive", "7", to_location_id="L1")
    do_sync(ledger, lake)
    assert rows(lake, f"SELECT lot_id, on_hand FROM {STOCK} ORDER BY on_hand") == [
        (gone, 5.0),
        (kept, 7.0),
    ]
    ledger.move(gone, "scrap", "5", from_location_id="L1")
    ledger.move(kept, "transfer", "2", from_location_id="L1", to_location_id="L2")
    do_sync(ledger, lake)
    assert rows(lake, f"SELECT lot_id, location_id, on_hand FROM {STOCK} ORDER BY location_id") == [
        (kept, "L1", 5.0),
        (kept, "L2", 2.0),
    ]
    assert_lake_matches_ledger(ledger, lake)


def test_both_tables_agree_with_the_ledger_row_for_row_after_many_syncs(
    ledger: LedgerBuilder, lake: LakeConfig, tmp_path: Any
) -> None:
    lots = [ledger.record(f"LOT-{n}") for n in range(3)]
    for n, lot in enumerate(lots):
        ledger.move(lot, "receive", str(10 + n), to_location_id="L1", cost_code_id=f"CC-{n}")
        do_sync(ledger, lake)
    ledger.move(lots[0], "adjust", "1", direction="in", to_location_id="L3")
    ledger.move(lots[1], "scrap", "11", from_location_id="L1")
    do_sync(ledger, lake)
    fresh = LakeConfig.at(tmp_path / "fresh")
    do_sync(ledger, fresh)
    assert_lake_matches_ledger(ledger, lake, fresh)
