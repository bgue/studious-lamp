"""DuckDB and DuckLake bootstrap: load the extension, take the lake lock, attach the catalog.

The DuckLake extension cannot be INSTALLed in the build environment (ADR-0002 addendum, L-P0-I5-O2).
It ships in the ``duckdb-extension-ducklake`` wheel, and ``duckdb_extensions.import_extension``
places it where ``LOAD`` finds it. This module never calls ``INSTALL`` and turns off autoinstall
and autoload, so no code path in the lake reaches for the network.

A DuckDB catalog file admits one writing process or many reading ones, never both. Every process
here goes through :func:`open_lake`, which takes a lock file first: shared for readers, exclusive
for the sync. The catalog is open only for the length of one sync or one query.
"""

from __future__ import annotations

import fcntl
import shutil
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import duckdb
import duckdb_extensions

from tl_lake.config import LakeConfig
from tl_lake.errors import LakeLockTimeout, LakeNotInitialisedError

CATALOG = "lake"
"""The attached catalog's name, and the schema-qualified prefix of every lake table."""
LOCK_TIMEOUT_S = 60.0

Duck = duckdb.DuckDBPyConnection

_extension_ready = False


def sql_str(value: str) -> str:
    """A SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def ident(name: str) -> str:
    """A quoted SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def table_ref(name: str) -> str:
    """The fully qualified, quoted reference to a lake table."""
    return f"{CATALOG}.main.{ident(name)}"


def connect() -> Duck:
    """A fresh in-memory DuckDB connection with DuckLake loaded and extension autoload off."""
    global _extension_ready
    if not _extension_ready:
        duckdb_extensions.import_extension("ducklake")
        _extension_ready = True
    con = duckdb.connect(
        ":memory:",
        config={"autoinstall_known_extensions": False, "autoload_known_extensions": False},
    )
    con.execute("LOAD ducklake")
    con.execute("SET TimeZone = 'UTC'")
    return con


def attach(con: Duck, config: LakeConfig, *, read_only: bool) -> None:
    """ATTACH the lake catalog as ``lake`` and make it the default catalog.

    ``OVERRIDE_DATA_PATH`` makes a lake directory that was moved still work: the data path the
    catalog stored is replaced by the one under the current ``lake_dir``.
    """
    options = [f"DATA_PATH {sql_str(str(config.data_path) + '/')}", "OVERRIDE_DATA_PATH true"]
    if read_only:
        options.append("READ_ONLY")
    else:
        options.append("DATA_INLINING_ROW_LIMIT 0")  # every row goes to Parquet, none inlined
    con.execute(
        f"ATTACH {sql_str('ducklake:' + str(config.catalog_path))} AS {CATALOG} "
        f"({', '.join(options)})"
    )
    con.execute(f"USE {CATALOG}")


@contextmanager
def lake_lock(
    config: LakeConfig, *, exclusive: bool, timeout_s: float = LOCK_TIMEOUT_S
) -> Generator[None]:
    """Hold the lake's lock file (shared or exclusive), waiting up to ``timeout_s``."""
    if exclusive:
        config.lake_dir.mkdir(parents=True, exist_ok=True)
    elif not config.lake_dir.exists():
        raise LakeNotInitialisedError(f"no lake at {config.lake_dir}: run `tl lake sync` first")
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    deadline = time.monotonic() + timeout_s
    with config.lock_path.open("a") as handle:
        while True:
            try:
                fcntl.flock(handle, mode | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    kind = "sync" if exclusive else "query"
                    raise LakeLockTimeout(
                        f"the lake is busy: could not take the {kind} lock in {timeout_s:g} s"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _wipe(config: LakeConfig) -> None:
    for path in (
        config.catalog_path,
        config.catalog_path.with_name(config.catalog_path.name + ".wal"),
    ):
        path.unlink(missing_ok=True)
    shutil.rmtree(config.data_path, ignore_errors=True)
    shutil.rmtree(config.tmp_dir, ignore_errors=True)


@contextmanager
def open_lake(
    config: LakeConfig, *, write: bool, timeout_s: float = LOCK_TIMEOUT_S, wipe: bool = False
) -> Generator[Duck]:
    """Lock the lake, attach the catalog, and yield the connection. Closes everything on exit.

    ``write=True`` takes the exclusive lock and creates the directories and an empty catalog if
    they are missing. ``write=False`` takes the shared lock, attaches READ_ONLY, and raises
    :class:`LakeNotInitialisedError` if the lake has never been synced. ``wipe=True`` (writers
    only) first deletes the catalog and the data files, leaving the audit log alone.
    """
    with lake_lock(config, exclusive=write, timeout_s=timeout_s):
        if write:
            if wipe:
                _wipe(config)
            config.data_path.mkdir(parents=True, exist_ok=True)
            config.tmp_dir.mkdir(parents=True, exist_ok=True)
        elif not config.catalog_path.exists():
            raise LakeNotInitialisedError(f"no lake at {config.lake_dir}: run `tl lake sync` first")
        con = connect()
        try:
            attach(con, config, read_only=not write)
            yield con
        finally:
            con.close()


def lake_tables(con: Duck) -> dict[str, list[tuple[str, str]]]:
    """Every table in the attached lake: name to ``(column, type)`` pairs in column order."""
    rows: list[Any] = con.execute(
        "SELECT table_name, column_name, data_type FROM duckdb_columns() "
        f"WHERE database_name = {sql_str(CATALOG)} AND schema_name = 'main' "
        "ORDER BY table_name, column_index"
    ).fetchall()
    tables: dict[str, list[tuple[str, str]]] = {}
    for table, column, data_type in rows:
        tables.setdefault(str(table), []).append((str(column), str(data_type)))
    return tables
