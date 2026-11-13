"""Acceptance for P2-I6-S1: materials silver, the gold runner and its three model tables.
Exit 0, one ``PASS <check>`` line per check, then ``S1 ok``. SQLite only; no network.

Run: ``uv run python dev/accept/P2-I6/S1.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from tl_adapters.db import create_schema, make_engine, open_uow
from tl_core.ledger import NewEvent
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record
from tl_lake import LakeConfig, lake_query, read_snapshot, sync_lake
from tl_lake.duck import lake_tables, open_lake
from tl_lake.gold import GOLD_MODELS, build_gold_marts

ROOT = Path(__file__).resolve().parents[3]
SCOPE = "project:P123"


def passed(name: str) -> None:
    print(f"PASS {name}")


def main() -> int:
    with (
        tempfile.TemporaryDirectory() as tmp,
        use_provider(DirectorySchemaProvider(ROOT / "schema" / "fixtures")),
    ):
        db = Path(tmp) / "tl.db"
        create_schema(db)
        with open_uow(db) as uow:
            lot = handle_create_record(
                uow,
                CreateRecord(
                    actor="user:u",
                    source="accept",
                    scope=SCOPE,
                    record_type="core.Record",
                    title="Lot",
                    key="LOT-1",
                ),
            ).stream_id
        version = 1
        for kind, qty, where in (
            ("receive", "10", {"to_location_id": "L1"}),
            ("scrap", "2", {"from_location_id": "L1"}),
            ("receive", "5", {"to_location_id": "L2"}),
        ):
            with open_uow(db) as uow:
                done = uow.append(
                    stream_id=lot,
                    stream_type="materials.StockLot",
                    scope=SCOPE,
                    expected_version=version,
                    events=[
                        NewEvent(
                            event_type="StockLot.Moved",
                            payload={"kind": kind, "qty": qty, "uom": "EA", **where},
                        )
                    ],
                    actor="user:u",
                    source="accept",
                    correlation_id=f"c-{version}",
                )
            version = done.events[-1].stream_version

        lake = LakeConfig.at(Path(tmp) / "lake")
        engine = make_engine(db)
        try:
            with read_snapshot(engine) as conn:
                sync_lake(lake, conn)
        finally:
            engine.dispose()
        with open_lake(lake, write=False) as con:
            tables = lake_tables(con)
            moved = con.execute("SELECT count(*) FROM cur_materials_movement").fetchone()
            stocked = con.execute("SELECT count(*) FROM cur_materials_stock").fetchone()
        assert "cur_materials_movement" in tables and "cur_materials_stock" in tables
        assert moved == (3,) and stocked == (2,), (moved, stocked)
        passed("silver tables present after a sync of a ledger with 3 movements")

        with open_lake(lake, write=True) as con:
            con.execute("BEGIN")
            # what the schedule pass leaves (a ledger with no schedule: nothing)
            con.execute(
                "CREATE TABLE lake.main.mart_schedule_history (scope VARCHAR, "
                "schedule_code VARCHAR, "
                "snapshot_number BIGINT, data_date TIMESTAMP, latest_early_finish TIMESTAMP, "
                "finish_slip_days BIGINT)"
            )
            build_gold_marts(con)
            con.execute("COMMIT")
            built = [m.name for m in GOLD_MODELS if m.name in lake_tables(con)]
        assert built == [m.name for m in GOLD_MODELS], built
        passed("build_gold_marts creates the three tables in order")

        result = lake_query("SELECT * FROM mart_materials", lake_dir=str(lake.lake_dir))
        assert result.as_of_seq == 4, result.as_of_seq  # the lot and its three movements
        assert "as of seq" in result.as_of_line()
        passed("lake_query answers SELECT * FROM mart_materials with as_of_seq")
    print("S1 ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
