"""Bronze: the rows of a file, untouched, in the lake (brief 29.6, 28.2).

The table is ``legacy_<system>_<table>``.

One lake table per system and table, text columns only, with ``_run_id`` and ``_row_no``. Column
names come from a file, so they are folded to ``[a-z0-9_]``, made unique and capped (a file cannot
make the lake grow a column per invented name: 200 columns at most, the reader's bound). A table
that exists keeps its columns and gains the ones a later file brings. Writing a run replaces its
rows, so a bronze step can be run again.

The bronze table is **not** in the ledger. A ``tl lake rebuild`` drops it; ``tl load bronze`` writes
a run's rows again from the stored extract.
"""

from __future__ import annotations

import re

from tl_lake import LakeConfig
from tl_lake.duck import Duck, ident, lake_tables, open_lake, table_ref
from tl_lake.ingest import insert_rows
from tl_lake.schema import Column

from tl_mod_legacy.limits import MAX_BRONZE_COLUMNS, MAX_SYSTEM
from tl_mod_legacy.model import Grid

NAME = re.compile(rf"[a-z][a-z0-9_]{{0,{MAX_SYSTEM - 1}}}")
_MAX_COLUMN_NAME = 40


def table_name(system: str, table: str) -> str:
    """``legacy_dms_register``. Raises ``ValueError`` for a name that is not an allowed one."""
    if NAME.fullmatch(system) is None or NAME.fullmatch(table) is None:
        raise ValueError("a system and a table are lower case letters, digits and '_'")
    return f"legacy_{system}_{table}"


def column_names(headers: list[str]) -> list[str]:
    """Safe, unique lake column names for ``headers``, in order (``TAG NO`` becomes ``tag_no``)."""
    if len(headers) > MAX_BRONZE_COLUMNS:
        raise ValueError(f"more than {MAX_BRONZE_COLUMNS} columns")
    used: set[str] = set()
    names: list[str] = []
    for header in headers:
        base = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")[:_MAX_COLUMN_NAME]
        if not base or not base[0].isalpha():
            base = f"c_{base}" if base else "c"
        name, n = base, 2
        while name in used:
            name = f"{base}_{n}"[: _MAX_COLUMN_NAME + 4]
            n += 1
        used.add(name)
        names.append(name)
    return names


def write_bronze(config: LakeConfig, system: str, table: str, run_id: str, grid: Grid) -> int:
    """Write the rows of one run; returns how many. Replaces rows of the same run."""
    lake_table = table_name(system, table)
    names = column_names(grid.columns)
    with open_lake(config, write=True) as con:
        _write(con, config, lake_table, run_id, names, grid)
    return len(grid.rows)


def _write(
    con: Duck, config: LakeConfig, lake_table: str, run_id: str, names: list[str], grid: Grid
) -> None:
    config.tmp_dir.mkdir(parents=True, exist_ok=True)
    existing = lake_tables(con).get(lake_table)
    columns = [Column("_run_id", "VARCHAR", True), Column("_row_no", "BIGINT", True)]
    columns += [Column(name, "VARCHAR") for name in names]
    con.execute("BEGIN")
    try:
        if existing is None:
            defs = ", ".join(f"{ident(c.name)} {c.duck_type}" for c in columns)
            con.execute(f"CREATE TABLE {table_ref(lake_table)} ({defs})")
        else:
            have = {name for name, _ in existing}
            for column in columns:
                if column.name not in have:
                    con.execute(
                        f"ALTER TABLE {table_ref(lake_table)} ADD COLUMN "
                        f"{ident(column.name)} {column.duck_type}"
                    )
            con.execute(f"DELETE FROM {table_ref(lake_table)} WHERE _run_id = ?", [run_id])
        stored = {c.name: c for c in columns}
        # a column the table has and this file lacks stays NULL; insert only what this file has
        rows = (
            {"_run_id": run_id, "_row_no": number, **dict(zip(names, row, strict=True))}
            for number, row in enumerate(grid.rows, start=1)
        )
        insert_rows(con, lake_table, list(stored.values()), rows, config.tmp_dir)
        con.execute("COMMIT")
    except BaseException:
        try:
            con.execute("ROLLBACK")
        except Exception:  # noqa: BLE001 - the first error is the one to report
            pass
        raise
