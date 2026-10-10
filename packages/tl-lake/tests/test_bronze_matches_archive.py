"""Bronze `events` and an archive segment's `events.parquet` are the same table (brief 28.2).

WS-A seals the ledger into Parquet written by DuckDB; the lake loads the same ledger rows. Their
column names, order and types must agree and every cell must be equal, so a lake can be compared
with (and later loaded from) the archive without conversion.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from builder import LedgerBuilder
from lakecheck import do_sync
from tl_adapters.archivestore.fs import FsArchiveStore
from tl_adapters.db import read_tx
from tl_core.archive import seal_segment
from tl_core.archive.segments import PARQUET, SEGMENTS_PREFIX
from tl_core.archive.signing import generate_signer
from tl_lake import LakeConfig
from tl_lake.duck import open_lake


def test_the_lake_events_table_equals_the_sealed_parquet(
    ledger: LedgerBuilder, lake: LakeConfig, tmp_path: Path
) -> None:
    a = ledger.record("A-1")
    b = ledger.record("B-1")
    ledger.values(a, "valve_data", {"size_in": 4, "manufacturer": "Acme"})
    ledger.link(a, b)
    ledger.update(b, title="Renamed é — ünïcode")
    do_sync(ledger, lake)

    store = FsArchiveStore(tmp_path / "archive")
    engine = ledger.engine()
    try:
        with read_tx(engine) as conn:
            manifest = seal_segment(conn, store, generate_signer(), max_events=100)
    finally:
        engine.dispose()
    assert manifest is not None and manifest.last_seq == ledger.head()

    [key] = [k for k in store.list_keys(SEGMENTS_PREFIX) if k.endswith("/" + PARQUET)]
    parquet = tmp_path / "events.parquet"
    parquet.write_bytes(store.get_bytes(key))

    probe = duckdb.connect(":memory:")
    archived_types = probe.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()
    archived = probe.execute(f"SELECT * FROM read_parquet('{parquet}') ORDER BY seq").fetchall()
    with open_lake(lake, write=False) as con:
        bronze_types = con.execute("DESCRIBE SELECT * FROM events").fetchall()
        bronze = con.execute("SELECT * FROM events ORDER BY seq").fetchall()
    assert [(r[0], r[1]) for r in bronze_types] == [(r[0], r[1]) for r in archived_types]
    assert bronze == archived
    assert len(bronze) == ledger.head()
