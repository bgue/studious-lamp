"""P6 schedule snapshots in the lake: bronze ``xer_*``, silver ``schedule_*`` and a mart.

The typed rows of a snapshot are operational tables (``sched_*``, ADR-0015 section 4): no event
produces them, so the seq-driven sync of :mod:`tl_lake.sync` cannot carry them. This second pass
runs after it (``tl lake sync`` calls both) and loads whole snapshots instead. A snapshot is
immutable once built, so it is loaded once and never changed, and only a snapshot that stops
being built (a Valid one that is voided) is taken out again. That keeps a rebuild equal to the
incremental result.

What goes where
---------------
* ``schedule_snapshot`` (silver): one row per built snapshot (Valid, Published, Superseded) with its
  schedule, state and counts. Small, and its state moves, so it is replaced as a whole whenever it
  differs.
* ``schedule_activity`` (silver): the typed activities of every built snapshot, with the schedule
  code, the snapshot number and data date, and floats in days of the activity's own calendar.
* ``xer_<table>`` (bronze): every table of the XER file verbatim, a row per row of the file, in
  the columns of the file as text, with ``_snapshot_id`` and ``_row_no``. They come from the raw
  bundle of the snapshot (a file), read through the ``raw_reader`` the caller passes; without one
  the bronze load waits (the snapshot is recorded as not yet loaded and the next sync with a reader
  does it).
* ``mart_float_trend`` (mart, :mod:`tl_lake.xer_marts`): rebuilt whenever a snapshot was loaded,
  dropped or changed state.
* ``_tl_xer`` (control): the snapshots the lake holds and whether their bronze tables are in;
  ``_tl_xer_state`` holds the signature of the last ``schedule_snapshot`` written.

A snapshot whose typed rows are not in the ledger (a restore before ``tl xer reconcile``) is left
for a later sync.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection, bindparam, text
from tl_xer.bundle import BundleError, read_bundle, verify_bundle

from tl_lake.config import LakeConfig
from tl_lake.duck import LOCK_TIMEOUT_S, Duck, ident, lake_tables, open_lake, table_ref
from tl_lake.errors import LakeSyncError
from tl_lake.ingest import CHUNK_ROWS, insert_rows
from tl_lake.schema import Column, generated_columns
from tl_lake.xer_marts import build_marts

SNAPSHOT_TABLE: Final = "schedule_snapshot"
ACTIVITY_TABLE: Final = "schedule_activity"
LOADED_TABLE: Final = "_tl_xer"
STATE_TABLE: Final = "_tl_xer_state"
BRONZE_PREFIX: Final = "xer_"

#: The states of a snapshot whose typed rows exist (``tl_mod_schedule.names.BUILT_STATES``).
BUILT_STATES: Final = ("Valid", "Published", "Superseded")
#: Hours in a day of a calendar P6 gave 0 or no hours for (``tl_mod_schedule.registry``).
DEFAULT_DAY_HOURS: Final = 8.0

#: ``(scope, file id, raw SHA-256 of the uncompressed text) -> the bytes of the raw bundle``.
RawReader = Callable[[str, str, str], bytes]

_SNAPSHOT_COLUMNS: Final = (
    Column("snapshot_id", "VARCHAR", True),
    Column("schedule_code", "VARCHAR", True),
    Column("number", "BIGINT", True),
    Column("state", "VARCHAR", True),
    Column("is_current", "BOOLEAN", True),
    Column("data_date", "TIMESTAMP"),
    Column("p6_version", "VARCHAR"),
    Column("p6_project", "VARCHAR"),
    Column("activity_count", "BIGINT"),
    Column("relationship_count", "BIGINT"),
    Column("wbs_count", "BIGINT"),
    Column("calendar_count", "BIGINT"),
    Column("code_count", "BIGINT"),
    Column("udf_count", "BIGINT"),
    Column("error_count", "BIGINT"),
    Column("warning_count", "BIGINT"),
    Column("source_name", "VARCHAR"),
    Column("source_sha256", "VARCHAR"),
    Column("source_size", "BIGINT"),
    Column("built_at", "VARCHAR"),
    Column("published_at", "VARCHAR"),
)
_LOADED_COLUMNS: Final = (
    Column("snapshot_id", "VARCHAR", True),
    Column("bronze", "BOOLEAN", True),
)
_STATE_COLUMNS: Final = (Column("signature", "VARCHAR", True),)
_DATE_COLUMNS: Final = frozenset(
    {
        "early_start",
        "early_finish",
        "late_start",
        "late_finish",
        "actual_start",
        "actual_finish",
        "target_start",
        "target_finish",
        "constraint_date",
    }
)
#: Columns of ``sched_activity`` the lake table leaves out (a surrogate key, the scope).
_LEFT_OUT: Final = frozenset({"row_id", "scope"})


def activity_columns() -> list[Column]:
    """The columns of ``schedule_activity``: the context of the snapshot, then the typed row."""
    context = [
        Column("snapshot_id", "VARCHAR", True),
        Column("schedule_code", "VARCHAR", True),
        Column("snapshot_number", "BIGINT", True),
        Column("data_date", "TIMESTAMP"),
    ]
    typed = [
        Column(c.name, "TIMESTAMP") if c.name in _DATE_COLUMNS else c
        for c in generated_columns("sched_activity")
        if c.name not in _LEFT_OUT and c.name != "snapshot_id"
    ]
    days = [Column("total_float_days", "DOUBLE"), Column("free_float_days", "DOUBLE")]
    return [*context, *typed, *days]


@dataclass(frozen=True)
class XerSyncResult:
    """What one pass did. ``snapshot_id`` is ``None`` when the lake was already up to date."""

    snapshot_id: int | None
    loaded: int  # snapshots whose silver rows were added
    dropped: int  # snapshots taken out because they stopped being built
    bronze: int  # snapshots whose bronze tables were added
    activity_rows: int
    bronze_rows: int
    waiting: int  # built snapshots whose typed rows are not in the ledger yet
    bronze_waiting: int = 0  # loaded snapshots whose bronze tables are not in (no raw reader)

    @property
    def up_to_date(self) -> bool:
        return self.snapshot_id is None


# --- the ledger side ---------------------------------------------------------------------------

_SNAPSHOTS_SQL = text(
    "SELECT t.id, t.scope, t.schedule_code, t.number, r.status AS state, "
    "(s.current_snapshot_id = t.id) AS is_current, t.data_date, t.p6_version, t.p6_project, "
    "t.activity_count, t.relationship_count, t.wbs_count, t.calendar_count, t.code_count, "
    "t.udf_count, t.error_count, t.warning_count, t.source_name, t.source_sha256, t.source_size, "
    "t.built_at, t.published_at, t.raw_file_id, t.raw_sha256 "
    "FROM cur_schedule_schedule_snapshot t JOIN cur_core_record r ON r.id = t.id "
    "JOIN cur_schedule_schedule s ON s.id = t.schedule_id "
    "WHERE r.status IN :states ORDER BY t.schedule_code, t.number"
).bindparams(bindparam("states", expanding=True))
_ROW_COUNTS_SQL = text("SELECT snapshot_id, COUNT(*) AS n FROM sched_activity GROUP BY snapshot_id")
_DAY_HOURS_SQL = text("SELECT calendar_id, day_hr FROM sched_calendar WHERE snapshot_id = :id")


@dataclass(frozen=True)
class LedgerSnapshot:
    id: str
    scope: str
    schedule_code: str
    number: int
    state: str
    is_current: bool
    data_date: str | None
    p6_version: str | None
    p6_project: str | None
    counts: tuple[int | None, ...]  # activities, relationships, wbs, calendars, codes, udfs
    error_count: int | None
    warning_count: int | None
    source_name: str | None
    source_sha256: str | None
    source_size: int | None
    built_at: str | None
    published_at: str | None
    raw_file_id: str | None
    raw_sha256: str | None

    def row(self) -> dict[str, Any]:
        activities, relationships, wbs, calendars, codes, udfs = self.counts
        return {
            "snapshot_id": self.id,
            "schedule_code": self.schedule_code,
            "number": self.number,
            "state": self.state,
            "is_current": self.is_current,
            "data_date": self.data_date,
            "p6_version": self.p6_version,
            "p6_project": self.p6_project,
            "activity_count": activities,
            "relationship_count": relationships,
            "wbs_count": wbs,
            "calendar_count": calendars,
            "code_count": codes,
            "udf_count": udfs,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "source_name": self.source_name,
            "source_sha256": self.source_sha256,
            "source_size": self.source_size,
            "built_at": self.built_at,
            "published_at": self.published_at,
        }


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _opt(value: Any) -> str | None:
    return None if value is None else str(value)


def _built_snapshots(ledger: Connection) -> list[LedgerSnapshot]:
    found = ledger.execute(_SNAPSHOTS_SQL, {"states": list(BUILT_STATES)}).all()
    return [
        LedgerSnapshot(
            id=str(r.id),
            scope=str(r.scope),
            schedule_code=str(r.schedule_code),
            number=int(r.number),
            state=str(r.state),
            is_current=bool(r.is_current),
            data_date=_opt(r.data_date),
            p6_version=_opt(r.p6_version),
            p6_project=_opt(r.p6_project),
            counts=tuple(
                _opt_int(getattr(r, name))
                for name in (
                    "activity_count",
                    "relationship_count",
                    "wbs_count",
                    "calendar_count",
                    "code_count",
                    "udf_count",
                )
            ),
            error_count=_opt_int(r.error_count),
            warning_count=_opt_int(r.warning_count),
            source_name=_opt(r.source_name),
            source_sha256=_opt(r.source_sha256),
            source_size=_opt_int(r.source_size),
            built_at=_opt(r.built_at),
            published_at=_opt(r.published_at),
            raw_file_id=_opt(r.raw_file_id),
            raw_sha256=_opt(r.raw_sha256),
        )
        for r in found
    ]


def _activity_rows(
    ledger: Connection, snapshot: LedgerSnapshot, columns: Sequence[Column], chunk: int
) -> Iterator[Mapping[str, Any]]:
    """The typed activities of one snapshot as lake rows, in file order."""
    hours = {
        str(r.calendar_id): float(r.day_hr)
        for r in ledger.execute(_DAY_HOURS_SQL, {"id": snapshot.id})
    }
    names = [c.name for c in columns if c.name in _TYPED_NAMES]
    statement = text(
        f"SELECT {', '.join(names)} FROM sched_activity WHERE snapshot_id = :id"
    ).bindparams(id=snapshot.id)
    result = ledger.execute(statement.execution_options(yield_per=chunk))
    try:
        for page in result.partitions(chunk):
            for row in page:
                typed = dict(row._mapping)
                per_day = hours.get(str(typed["calendar_id"])) or DEFAULT_DAY_HOURS
                yield {
                    **typed,
                    "snapshot_id": snapshot.id,
                    "schedule_code": snapshot.schedule_code,
                    "snapshot_number": snapshot.number,
                    "data_date": snapshot.data_date,
                    "total_float_days": _days(typed["total_float_hr"], per_day),
                    "free_float_days": _days(typed["free_float_hr"], per_day),
                }
    finally:
        result.close()


def _days(hours: Any, per_day: float) -> float | None:
    return None if hours is None else round(float(hours) / per_day, 2)


_TYPED_NAMES: Final = frozenset(
    c.name
    for c in generated_columns("sched_activity")
    if c.name not in _LEFT_OUT and c.name != "snapshot_id"
)


# --- the lake side -----------------------------------------------------------------------------


def _ensure_table(
    con: Duck, existing: Mapping[str, Any], name: str, columns: Sequence[Column]
) -> None:
    """Create ``name`` or add the columns it lacks."""
    have = existing.get(name)
    if have is None:
        defs = ", ".join(
            f"{ident(c.name)} {c.duck_type}{' NOT NULL' if c.not_null else ''}" for c in columns
        )
        con.execute(f"CREATE TABLE {table_ref(name)} ({defs})")
        return
    known = {column for column, _ in have}
    for column in columns:
        if column.name not in known:
            con.execute(
                f"ALTER TABLE {table_ref(name)} ADD COLUMN {ident(column.name)} {column.duck_type}"
            )


def _drop_snapshots(con: Duck, tables: Mapping[str, Any], ids: Sequence[str]) -> None:
    if not ids:
        return
    marks = ", ".join("?" for _ in ids)
    for name in tables:
        if name == ACTIVITY_TABLE or name.startswith(BRONZE_PREFIX):
            column = "snapshot_id" if name == ACTIVITY_TABLE else "_snapshot_id"
            con.execute(
                f"DELETE FROM {table_ref(name)} WHERE {ident(column)} IN ({marks})", list(ids)
            )
    con.execute(f"DELETE FROM {table_ref(LOADED_TABLE)} WHERE snapshot_id IN ({marks})", list(ids))


def _current_snapshot(con: Duck) -> int:
    row = con.execute("SELECT id FROM lake.current_snapshot()").fetchone()
    assert row is not None
    return int(row[0])


def _signature(rows: Sequence[Mapping[str, Any]]) -> str:
    blob = json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _bronze_name(table: str) -> str:
    return BRONZE_PREFIX + table.lower()


def _load_bronze(
    con: Duck,
    config: LakeConfig,
    snapshot: LedgerSnapshot,
    raw_reader: RawReader,
    chunk: int,
) -> int:
    """Add the tables of the snapshot's raw bundle; returns the rows added."""
    if snapshot.raw_file_id is None or snapshot.raw_sha256 is None:
        raise LakeSyncError(
            f"snapshot {snapshot.schedule_code}#{snapshot.number} has no raw bundle"
        )
    blob = raw_reader(snapshot.scope, snapshot.raw_file_id, snapshot.raw_sha256)
    try:
        verify_bundle(blob, snapshot.raw_sha256)
        _, tables = read_bundle(blob)
        total = 0
        for table in tables:
            fields = [name.lower() for name in table.columns]
            columns = [Column("_snapshot_id", "VARCHAR", True), Column("_row_no", "BIGINT", True)]
            columns += [Column(name, "VARCHAR") for name in fields]
            _ensure_table(con, lake_tables(con), _bronze_name(table.name), columns)
            rows = (
                {"_snapshot_id": snapshot.id, "_row_no": n, **dict(zip(fields, row, strict=True))}
                for n, row in enumerate(table.rows, start=1)
            )
            total += insert_rows(
                con, _bronze_name(table.name), columns, rows, config.tmp_dir, chunk=chunk
            )
        return total
    except (BundleError, ValueError) as exc:
        raise LakeSyncError(
            f"the raw bundle of {snapshot.schedule_code}#{snapshot.number}: {exc}"
        ) from exc


def sync_xer(
    config: LakeConfig,
    ledger: Connection,
    raw_reader: RawReader | None = None,
    *,
    lock_timeout_s: float = LOCK_TIMEOUT_S,
    chunk: int = CHUNK_ROWS,
) -> XerSyncResult:
    """Bring the lake's schedule tables up to the ledger's built snapshots in one snapshot.

    ``ledger`` is a connection in a read transaction (``tl_lake.source.read_snapshot``), as for
    :func:`tl_lake.sync.sync_lake`, which should have run first. ``raw_reader`` supplies the bytes
    of a snapshot's raw bundle; without it the bronze tables are not loaded.
    """
    with open_lake(config, write=True, timeout_s=lock_timeout_s) as con:
        return _sync(con, config, ledger, raw_reader, chunk)


def _sync(
    con: Duck,
    config: LakeConfig,
    ledger: Connection,
    raw_reader: RawReader | None,
    chunk: int,
) -> XerSyncResult:
    built = _built_snapshots(ledger)
    counts = {str(r.snapshot_id): int(r.n) for r in ledger.execute(_ROW_COUNTS_SQL)}
    ready = [s for s in built if s.counts[0] is not None and counts.get(s.id, 0) == s.counts[0]]
    waiting = len(built) - len(ready)
    columns = activity_columns()

    tables = lake_tables(con)
    if not ready and LOADED_TABLE not in tables:
        # nothing to load and nothing loaded before: a lake of a ledger with no schedules stays as
        # it is, with none of the schedule tables
        return XerSyncResult(None, 0, 0, 0, 0, 0, waiting)
    con.execute("BEGIN")
    try:
        _ensure_table(con, tables, LOADED_TABLE, _LOADED_COLUMNS)
        _ensure_table(con, tables, STATE_TABLE, _STATE_COLUMNS)
        _ensure_table(con, tables, SNAPSHOT_TABLE, _SNAPSHOT_COLUMNS)
        _ensure_table(con, tables, ACTIVITY_TABLE, columns)
        tables = lake_tables(con)
        held: dict[str, bool] = {
            str(r[0]): bool(r[1])
            for r in con.execute(
                f"SELECT snapshot_id, bronze FROM {table_ref(LOADED_TABLE)}"
            ).fetchall()
        }
        wanted = {s.id: s for s in ready}
        gone = sorted(set(held) - set(wanted))
        _drop_snapshots(con, tables, gone)

        activity_rows = 0
        loaded = 0
        for snapshot in ready:
            if snapshot.id in held:
                continue
            activity_rows += insert_rows(
                con,
                ACTIVITY_TABLE,
                columns,
                _activity_rows(ledger, snapshot, columns, chunk),
                config.tmp_dir,
                chunk=chunk,
            )
            con.execute(
                f"INSERT INTO {table_ref(LOADED_TABLE)} VALUES (?, ?)", [snapshot.id, False]
            )
            held[snapshot.id] = False
            loaded += 1

        bronze = 0
        bronze_rows = 0
        if raw_reader is not None:
            for snapshot in ready:
                if held[snapshot.id]:
                    continue
                bronze_rows += _load_bronze(con, config, snapshot, raw_reader, chunk)
                con.execute(
                    f"UPDATE {table_ref(LOADED_TABLE)} SET bronze = TRUE WHERE snapshot_id = ?",
                    [snapshot.id],
                )
                held[snapshot.id] = True
                bronze += 1

        rows = [s.row() for s in ready]
        signature = _signature(rows)
        known = con.execute(f"SELECT signature FROM {table_ref(STATE_TABLE)}").fetchall()
        changed_meta = [r[0] for r in known] != [signature]
        if changed_meta:
            con.execute(f"DELETE FROM {table_ref(SNAPSHOT_TABLE)}")
            insert_rows(con, SNAPSHOT_TABLE, _SNAPSHOT_COLUMNS, rows, config.tmp_dir, chunk=chunk)
            con.execute(f"DELETE FROM {table_ref(STATE_TABLE)}")
            con.execute(f"INSERT INTO {table_ref(STATE_TABLE)} VALUES (?)", [signature])
        if changed_meta or bronze:  # (a snapshot loaded or dropped changes the rows of the first)
            build_marts(con)
            con.execute("COMMIT")
            return XerSyncResult(
                _current_snapshot(con),
                loaded,
                len(gone),
                bronze,
                activity_rows,
                bronze_rows,
                waiting,
                sum(1 for s in ready if not held[s.id]),
            )
        con.execute("ROLLBACK")
        return XerSyncResult(None, 0, 0, 0, 0, 0, waiting, sum(1 for s in ready if not held[s.id]))
    except BaseException:
        try:
            con.execute("ROLLBACK")
        except Exception:  # noqa: BLE001 - the original error is the one worth reporting
            pass
        raise
