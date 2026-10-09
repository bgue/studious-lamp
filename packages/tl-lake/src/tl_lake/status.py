"""What the lake currently holds and which ledger seq it reflects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tl_lake.config import LakeConfig
from tl_lake.duck import Duck, lake_tables, open_lake, table_ref
from tl_lake.errors import LakeNotInitialisedError
from tl_lake.schema import SYNC_TABLE


@dataclass(frozen=True)
class LakeStatus:
    """``as_of_seq`` is the last ledger seq the lake reflects (0 when nothing was synced)."""

    initialised: bool
    as_of_seq: int = 0
    snapshot_id: int | None = None
    synced_at: datetime | None = None
    syncs: int = 0
    tables: dict[str, int] = field(default_factory=dict)


def as_of(con: Duck) -> tuple[int, int | None]:
    """``(last_seq, snapshot_id)`` of the newest sync, or ``(0, None)``."""
    if SYNC_TABLE not in lake_tables(con):
        return 0, None
    row = con.execute(
        f"SELECT last_seq, snapshot_id FROM {table_ref(SYNC_TABLE)} ORDER BY last_seq DESC LIMIT 1"
    ).fetchone()
    return (0, None) if row is None else (int(row[0]), int(row[1]))


def lake_status(config: LakeConfig) -> LakeStatus:
    """Read the watermark and row counts. A lake that was never synced is not an error."""
    try:
        with open_lake(config, write=False) as con:
            tables = lake_tables(con)
            seq, snapshot = as_of(con)
            if snapshot is None:
                return LakeStatus(initialised=True, tables={})
            row = con.execute(
                f"SELECT CAST(synced_at AS VARCHAR), "
                f"(SELECT count(*) FROM {table_ref(SYNC_TABLE)}) "
                f"FROM {table_ref(SYNC_TABLE)} WHERE snapshot_id = {snapshot}"
            ).fetchone()
            assert row is not None
            counts = {
                name: int(con.execute(f"SELECT count(*) FROM {table_ref(name)}").fetchone()[0])  # type: ignore[index]
                for name in sorted(tables)
                if name != SYNC_TABLE
            }
            return LakeStatus(
                initialised=True,
                as_of_seq=seq,
                snapshot_id=snapshot,
                synced_at=datetime.fromisoformat(row[0]),
                syncs=int(row[1]),
                tables=counts,
            )
    except LakeNotInitialisedError:
        return LakeStatus(initialised=False)


def describe_lake(config: LakeConfig) -> dict[str, list[tuple[str, str]]]:
    """Table name to ``(column, type)`` pairs for every lake table, in column order.

    Raises :class:`LakeNotInitialisedError` when nothing was synced yet.
    """
    with open_lake(config, write=False) as con:
        return lake_tables(con)
