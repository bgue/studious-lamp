"""``tl lake sync``: copy the ledger into the lake, incrementally by ``seq`` (brief 28.3).

One sync is one DuckLake transaction, so it is one snapshot, and the ``_tl_sync`` row that names
the snapshot is written in that same transaction. The watermark is therefore never ahead of or
behind the data: a crash anywhere before COMMIT leaves the lake exactly as it was.

Order inside the transaction:

1. create the tables on the first sync; add the columns that appeared in the ledger since (new
   promoted pset columns), which makes the affected silver table reload in full, because the
   ledger back-fills a new column without touching ``last_seq``;
2. bronze: append the events after the watermark, and fail on a gap in ``seq``;
3. silver: for every ledger row whose ``last_seq`` is after the watermark, replace the lake row;
4. write the ``_tl_sync`` row, then COMMIT.

The caller passes a ledger connection inside a read transaction that sees one consistent snapshot
(see :func:`tl_lake.source.read_snapshot`). Events and current-state rows are then from the same
instant, so silver is exactly the state at ``head`` and ``_tl_sync.last_seq`` is honest. A row with
``last_seq`` past the head means the connection is not a snapshot, and the sync refuses.

Only one sync runs at a time (an exclusive file lock), so the snapshot id the row names, which is
the current snapshot plus one, is the one the commit produces. That is checked after COMMIT.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, MetaData, Table, func, select, text
from sqlalchemy.types import TypeEngine

from tl_lake.config import LakeConfig
from tl_lake.duck import (
    LOCK_TIMEOUT_S,
    Duck,
    ident,
    lake_tables,
    open_lake,
    table_ref,
)
from tl_lake.errors import LakeAheadError, LakeDivergedError, LakeSyncError
from tl_lake.ingest import CHUNK_ROWS, delete_keys, insert_rows
from tl_lake.schema import (
    EVENTS_COLUMNS,
    EVENTS_TABLE,
    RECORD_SOURCE,
    SILVER_TABLES,
    SYNC_COLUMNS,
    SYNC_TABLE,
    Column,
    SilverTable,
    silver_columns,
)

KEY_BATCH = 500
"""How many keys go into one ``IN (...)`` query against the ledger."""


@dataclass(frozen=True)
class SyncResult:
    """What one sync did. ``snapshot_id`` is ``None`` when the lake was already up to date."""

    snapshot_id: int | None
    first_seq: int | None
    last_seq: int
    events: int
    silver_rows: Mapping[str, int]

    @property
    def up_to_date(self) -> bool:
        return self.snapshot_id is None


def _pages(conn: Connection, statement: Any, size: int) -> Iterator[Sequence[Any]]:
    result = conn.execute(statement.execution_options(yield_per=size))
    try:
        yield from result.partitions(size)
    finally:
        result.close()


def _event_rows(conn: Connection, after: int, upto: int, size: int) -> Iterator[Mapping[str, Any]]:
    names = ", ".join(c.name for c in EVENTS_COLUMNS)
    statement = text(
        f"SELECT {names} FROM {EVENTS_TABLE} WHERE seq > :after AND seq <= :upto ORDER BY seq"
    ).bindparams(after=after, upto=upto)
    for page in _pages(conn, statement, size):
        for row in page:
            yield row._mapping


def _contiguous(
    rows: Iterator[Mapping[str, Any]], first: int, last: int
) -> Iterator[Mapping[str, Any]]:
    """Pass events through, failing on a gap or a stray seq: the ledger contract is gap-free."""
    expected = first
    for row in rows:
        if row["seq"] != expected:
            raise LakeSyncError(
                f"the ledger has a gap in seq: expected {expected}, found {row['seq']}"
            )
        expected += 1
        yield row
    if expected != last + 1:
        raise LakeSyncError(
            f"the ledger returned events up to seq {expected - 1}, but its head is {last}"
        )


def _reflect(conn: Connection, name: str) -> Table:
    return Table(name, MetaData(), autoload_with=conn)


def _ledger_columns(table: Table) -> list[tuple[str, TypeEngine[object]]]:
    return [(c.name, c.type) for c in table.columns]


def _changed_keys(conn: Connection, table: Table, key: str, watermark: int) -> list[str]:
    statement = (
        select(table.c[key]).where(table.c.last_seq > watermark).distinct().order_by(table.c[key])
    )
    return [str(k) for k in conn.execute(statement).scalars()]


def _silver_rows(
    conn: Connection, table: Table, key: str, keys: Sequence[str] | None, size: int
) -> Iterator[Mapping[str, Any]]:
    """Ledger rows of ``table``: all of them (``keys`` is ``None``) or those with these keys."""
    order = [table.c[key], *([table.c.path] if "path" in table.c else [])]
    if keys is None:
        for page in _pages(conn, select(table).order_by(*order), size):
            for row in page:
                yield row._mapping
        return
    for start in range(0, len(keys), KEY_BATCH):
        batch = keys[start : start + KEY_BATCH]
        statement = select(table).where(table.c[key].in_(batch)).order_by(*order)
        for page in _pages(conn, statement, size):
            for row in page:
                yield row._mapping


def _ensure_table(
    con: Duck, existing: Mapping[str, list[tuple[str, str]]], name: str, columns: Sequence[Column]
) -> bool:
    """Create ``name`` or add its missing columns. ``True`` when the table is new or grew."""
    have = existing.get(name)
    if have is None:
        defs = ", ".join(
            f"{ident(c.name)} {c.duck_type}{' NOT NULL' if c.not_null else ''}" for c in columns
        )
        con.execute(f"CREATE TABLE {table_ref(name)} ({defs})")
        return True
    known = {column for column, _ in have}
    new = [c for c in columns if c.name not in known]
    for column in new:
        con.execute(
            f"ALTER TABLE {table_ref(name)} ADD COLUMN {ident(column.name)} {column.duck_type}"
        )
    return bool(new)


def _current_snapshot(con: Duck) -> int:
    row = con.execute("SELECT id FROM lake.current_snapshot()").fetchone()
    assert row is not None
    return int(row[0])


def _watermark(con: Duck) -> int:
    row = con.execute(f"SELECT COALESCE(MAX(last_seq), 0) FROM {table_ref(SYNC_TABLE)}").fetchone()
    assert row is not None
    return int(row[0])


def _verify_tip(con: Duck, ledger: Connection, seq: int) -> None:
    """The event at ``seq`` must be the same event in the lake and in the ledger."""
    mine = ledger.execute(
        text(f"SELECT hash FROM {EVENTS_TABLE} WHERE seq = :seq"), {"seq": seq}
    ).scalar()
    row = con.execute(
        f"SELECT hash FROM {table_ref(EVENTS_TABLE)} WHERE seq = {int(seq)}"
    ).fetchone()
    theirs = None if row is None else row[0]
    if mine != theirs:
        raise LakeDivergedError(
            f"the lake and the ledger disagree about the event at seq {seq}: "
            f"ledger hash {mine}, lake hash {theirs}. This is not the ledger the lake was built "
            "from; run `tl lake rebuild`."
        )


def sync_lake(
    config: LakeConfig,
    ledger: Connection,
    *,
    now: Callable[[], datetime] | None = None,
    lock_timeout_s: float = LOCK_TIMEOUT_S,
    chunk: int = CHUNK_ROWS,
    rebuild: bool = False,
) -> SyncResult:
    """Bring the lake up to the ledger's head in one snapshot.

    ``ledger`` must be a connection in a read transaction that sees one consistent snapshot.
    ``rebuild=True`` first deletes the lake's catalog and data, so the sync reloads everything.
    """
    with open_lake(config, write=True, timeout_s=lock_timeout_s, wipe=rebuild) as con:
        return _sync(con, config, ledger, now or (lambda: datetime.now(UTC)), chunk)


def _sync(
    con: Duck,
    config: LakeConfig,
    ledger: Connection,
    now: Callable[[], datetime],
    chunk: int,
) -> SyncResult:
    head = int(
        ledger.execute(text(f"SELECT COALESCE(MAX(seq), 0) FROM {EVENTS_TABLE}")).scalar_one()
    )
    tables = lake_tables(con)
    watermark = _watermark(con) if SYNC_TABLE in tables else 0
    if watermark > head:
        raise LakeAheadError(
            f"the lake is at seq {watermark} but the ledger head is {head}: this is not the "
            "ledger the lake was built from; run `tl lake rebuild`."
        )
    if watermark > 0:
        _verify_tip(con, ledger, watermark)
    if watermark == head:
        return SyncResult(None, None, head, 0, {})

    sources = {t.source: _reflect(ledger, t.source) for t in SILVER_TABLES}
    for source in sources.values():
        newest = ledger.execute(select(func.max(source.c.last_seq))).scalar()
        if newest is not None and newest > head:
            raise LakeSyncError(
                f"{source.name} has a row at seq {newest}, past the events head {head}: the "
                "ledger connection is not a consistent snapshot"
            )

    tmp = config.tmp_dir
    tmp.mkdir(parents=True, exist_ok=True)
    silver_rows: dict[str, int] = {}
    con.execute("BEGIN")
    try:
        predicted = _current_snapshot(con) + 1
        _ensure_table(con, tables, EVENTS_TABLE, EVENTS_COLUMNS)
        _ensure_table(con, tables, SYNC_TABLE, SYNC_COLUMNS)

        first = watermark + 1
        events = insert_rows(
            con,
            EVENTS_TABLE,
            EVENTS_COLUMNS,
            _contiguous(_event_rows(ledger, watermark, head, chunk), first, head),
            tmp,
            chunk=chunk,
        )

        record_keys = _changed_keys(ledger, sources[RECORD_SOURCE], "id", watermark)
        for silver in SILVER_TABLES:
            silver_rows[silver.name] = _sync_silver(
                con,
                ledger,
                silver,
                sources[silver.source],
                tables,
                watermark,
                record_keys,
                tmp,
                chunk,
            )

        con.execute(
            f"INSERT INTO {table_ref(SYNC_TABLE)} VALUES (?, ?, ?, ?)",
            [predicted, first, head, now().astimezone(UTC).replace(tzinfo=None)],
        )
        con.execute("COMMIT")
    except BaseException:
        try:
            con.execute("ROLLBACK")
        except Exception:  # noqa: BLE001 - the original error is the one worth reporting
            pass
        raise

    actual = _current_snapshot(con)
    if actual != predicted:
        raise LakeSyncError(
            f"the sync committed snapshot {actual} but recorded {predicted} in {SYNC_TABLE}: "
            "another process wrote to the lake outside the lake lock"
        )
    return SyncResult(actual, first, head, events, silver_rows)


def _sync_silver(
    con: Duck,
    ledger: Connection,
    silver: SilverTable,
    source: Table,
    existing: Mapping[str, list[tuple[str, str]]],
    watermark: int,
    record_keys: list[str],
    tmp: Path,
    chunk: int,
) -> int:
    columns = silver_columns(silver, _ledger_columns(source))
    reload_all = _ensure_table(con, existing, silver.name, columns) or watermark == 0
    if reload_all:
        if silver.name in existing:
            con.execute(f"DELETE FROM {table_ref(silver.name)}")
        keys = None
    else:
        if silver.driver is None:
            keys = _changed_keys(ledger, source, silver.key, watermark)
        else:
            keys = record_keys
        if not keys:
            return 0
        delete_keys(con, silver.name, silver.key, keys, tmp, chunk=chunk)
    return insert_rows(
        con,
        silver.name,
        columns,
        _silver_rows(ledger, source, silver.key, keys, chunk),
        tmp,
        chunk=chunk,
    )
