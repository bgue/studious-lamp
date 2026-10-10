"""Helpers that compare a lake with its ledger, row for row (shared by the lake tests)."""

from __future__ import annotations

import json
from typing import Any

from builder import LedgerBuilder
from sqlalchemy import Engine, text
from tl_lake import LakeConfig, read_snapshot, sync_lake
from tl_lake.duck import open_lake
from tl_lake.ingest import to_json_value

TABLES = {
    "events": "events",
    "cur_core_record": "cur_core_record",
    "links": "cur_links",
    "pset_values": "cur_pset_values",
}


Dump = tuple[list[str], list[str], list[tuple[Any, ...]]]


def lake_dump(config: LakeConfig, table: str) -> Dump:
    """Column names, DuckDB types and all rows (ordered), columns sorted by name."""
    with open_lake(config, write=False) as con:
        described = dict(
            con.execute(
                "SELECT column_name, data_type FROM duckdb_columns() "
                f"WHERE database_name = 'lake' AND table_name = '{table}'"
            ).fetchall()
        )
        names = sorted(described)
        cols = ", ".join(f'"{n}"' for n in names)
        rows = con.execute(f"SELECT {cols} FROM {table} ORDER BY ALL").fetchall()
    return names, [str(described[n]) for n in names], rows


def normalised(kinds: list[str], rows: list[tuple[Any, ...]]) -> list[str]:
    """Rows as sorted JSON text, each value converted the way the loader converts it."""
    return sorted(
        json.dumps([to_json_value(k, v) for k, v in zip(kinds, row, strict=True)]) for row in rows
    )


def ledger_rows(engine: Engine, source: str, names: list[str]) -> list[tuple[Any, ...]]:
    cols = ", ".join(names)
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(f"SELECT {cols} FROM {source}")).fetchall()]


def do_sync(ledger: LedgerBuilder, config: LakeConfig) -> None:
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(config, conn)
    finally:
        engine.dispose()


def assert_lake_matches_ledger(
    ledger: LedgerBuilder, lake: LakeConfig, other: LakeConfig | None = None
) -> None:
    """Every lake table equals the ledger's table by content, and equals ``other`` if given."""
    engine = ledger.engine()
    try:
        for lake_table, source in TABLES.items():
            names, kinds, rows = lake_dump(lake, lake_table)
            if other is not None:
                assert (names, kinds, rows) == lake_dump(other, lake_table), lake_table
            expected = normalised(kinds, ledger_rows(engine, source, names))
            assert normalised(kinds, rows) == expected, lake_table
    finally:
        engine.dispose()
