"""The gold pass: models become tables, a model with a missing need is dropped (P2-I6-S1)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from builder import LedgerBuilder
from lakecheck import do_sync, lake_table_names
from tl_lake import LakeConfig, lake_query
from tl_lake.duck import Duck, lake_tables, open_lake
from tl_lake.gold import GOLD_MODELS, build_gold_marts, model_sql


@pytest.fixture
def con(tmp_path: Path) -> Iterator[Duck]:
    with open_lake(LakeConfig.at(tmp_path / "lake"), write=True) as opened:
        yield opened


def make_events(con: Duck) -> None:
    con.execute(
        "CREATE TABLE lake.main.events (seq BIGINT, scope VARCHAR, event_type VARCHAR, "
        "payload VARCHAR)"
    )


def make_records(con: Duck) -> None:
    con.execute("CREATE TABLE lake.main.cur_core_record (id VARCHAR)")


def make_materials(con: Duck) -> None:
    con.execute(
        "CREATE TABLE lake.main.cur_materials_movement (seq BIGINT, scope VARCHAR, "
        "lot_id VARCHAR, kind VARCHAR, qty DOUBLE, cost_code_id VARCHAR, recorded_at VARCHAR)"
    )
    con.execute(
        "CREATE TABLE lake.main.cur_materials_stock (scope VARCHAR, lot_id VARCHAR, on_hand DOUBLE)"
    )


def marts(con: Duck) -> list[str]:
    return sorted(t for t in lake_tables(con) if t.startswith("mart_"))


def test_the_models_are_in_build_order_with_their_needs() -> None:
    assert [(m.name, m.needs) for m in GOLD_MODELS] == [
        ("mart_iwp_readiness_history", ("events", "cur_core_record")),
        ("mart_materials", ("cur_materials_movement", "cur_materials_stock")),
        (
            "mart_schedule_vs_readiness",
            ("mart_schedule_history", "mart_iwp_readiness_history"),
        ),
    ]


@pytest.mark.parametrize("model", GOLD_MODELS, ids=lambda m: m.name)
def test_every_model_has_a_file_that_is_one_select(model: object) -> None:
    name = model.name  # type: ignore[attr-defined]
    assert name.startswith("mart_")
    sql = model_sql(name)
    assert sql and not sql.endswith(";")
    statements = duckdb.extract_statements(sql)
    assert len(statements) == 1
    assert statements[0].type == duckdb.StatementType.SELECT


def test_a_model_whose_needs_are_missing_is_skipped(con: Duck) -> None:
    make_events(con)
    build_gold_marts(con)
    assert marts(con) == []  # the readiness model also needs the record table
    make_records(con)
    build_gold_marts(con)
    assert marts(con) == ["mart_iwp_readiness_history"]  # materials and schedule: no need met


def test_a_chained_model_is_built_once_its_inputs_exist_in_order(con: Duck) -> None:
    make_events(con)
    make_records(con)
    make_materials(con)
    con.execute(
        "CREATE TABLE lake.main.mart_schedule_history (scope VARCHAR, schedule_code VARCHAR, "
        "snapshot_number BIGINT, data_date TIMESTAMP, latest_early_finish TIMESTAMP, "
        "finish_slip_days BIGINT)"
    )
    build_gold_marts(con)
    assert marts(con) == [
        "mart_iwp_readiness_history",
        "mart_materials",
        "mart_schedule_history",
        "mart_schedule_vs_readiness",
    ]


def test_a_stale_mart_is_dropped_when_its_need_disappears(con: Duck) -> None:
    make_events(con)
    make_records(con)
    make_materials(con)
    build_gold_marts(con)
    assert "mart_materials" in marts(con)
    con.execute("DROP TABLE lake.main.cur_materials_stock")
    build_gold_marts(con)
    assert marts(con) == ["mart_iwp_readiness_history"]
    con.execute("CREATE TABLE lake.main.mart_materials (x BIGINT)")  # a leftover, no longer built
    build_gold_marts(con)
    assert "mart_materials" not in marts(con)


def test_a_ledger_with_no_materials_rows_keeps_the_tables_empty(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    ledger.record("A-1")
    do_sync(ledger, lake)
    names = lake_table_names(lake)
    for name in (
        "cur_materials_movement",
        "cur_materials_stock",
        "mart_materials",
        "mart_iwp_readiness_history",
    ):
        assert name in names, name
        with open_lake(lake, write=False) as con:
            assert con.execute(f"SELECT count(*) FROM {name}").fetchone() == (0,)
    assert "mart_schedule_vs_readiness" not in names  # no schedule pass yet


def test_lake_query_reads_the_gold_tables(ledger: LedgerBuilder, lake: LakeConfig) -> None:
    lot = ledger.record("LOT-1")
    ledger.move(lot, "receive", "4", to_location_id="L1")
    do_sync(ledger, lake)
    for name in ("mart_materials", "mart_iwp_readiness_history"):
        result = lake_query(f"SELECT * FROM {name}", lake_dir=str(lake.lake_dir))
        assert result.as_of_seq == ledger.head()
    result = lake_query(
        "SELECT lot_id, on_hand FROM cur_materials_stock", lake_dir=str(lake.lake_dir)
    )
    assert result.rows == [[lot, 4.0]]
