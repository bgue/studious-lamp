"""After a restore: queue lost builds again, and write the typed rows from the source files.

A restore from the archive replays the ledger. That gives back the snapshot records, their states
and the hashes ``Built`` recorded, but not the operational tables: ``job_queue`` and the
``sched_*`` rows are not made by any event (ADR-0014, ADR-0015). Two operations close the gap:

* :func:`requeue_orphans` puts a build back in the queue for every snapshot whose build was
  queued or running and is not in ``job_queue``;
* :func:`reconcile_tables` reads the source file of every built snapshot whose typed rows are
  missing or incomplete, reads it again in the resource envelope, checks that the typed rows
  hash to the value the ledger recorded, and writes them. A file that no longer gives the recorded
  hash writes nothing and is reported (``mismatch``).

Both are safe to run twice, and ``tl xer reconcile`` runs both. Nothing here appends an event: the
facts are already in the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.queue import job_queue_for
from tl_core.files.service import FileService
from tl_core.util import utcnow
from tl_xer.result import XerLimitError
from tl_xer.run import read_xer_file
from tl_xer.typed import Options

from tl_mod_schedule import registry, typed_store
from tl_mod_schedule.handlers.snapshots import DEFAULT_MAX_ATTEMPTS
from tl_mod_schedule.names import (
    BUILT_STATES,
    JOB_KIND_BUILD,
    PROCESSING,
    SNAPSHOT_TABLE,
    UPLOADED,
)
from tl_mod_schedule.store import SnapshotFiles

#: Rows the ledger recorded for a built snapshot, by typed table (the keys of ``Snapshot.tables``).
_COUNT_FIELDS = {
    "activities": "activity_count",
    "relationships": "relationship_count",
    "wbs": "wbs_count",
    "calendars": "calendar_count",
    "codes": "code_count",
    "udfs": "udf_count",
}

_ORPHANS_SQL = text(
    "SELECT t.id, t.scope, r.status FROM " + SNAPSHOT_TABLE + " t "
    "JOIN cur_core_record r ON r.id = t.id "
    "LEFT JOIN job_queue q ON q.job_id = t.id "
    "WHERE t.source_file_id IS NOT NULL AND q.job_id IS NULL AND r.voided = :no "
    "AND (r.status IS NULL OR r.status IN (:uploaded, :processing)) ORDER BY t.id"
)
_BUILT_SQL = (
    "SELECT t.id FROM " + SNAPSHOT_TABLE + " t JOIN cur_core_record r ON r.id = t.id "
    "WHERE r.status IN (:a, :b, :c)"
)


@dataclass(frozen=True)
class Reconciled:
    """What reconcile did for one snapshot.

    ``outcome``: ``ok`` (its rows were complete), ``rebuilt`` (written from the file),
    ``mismatch`` (the file no longer gives the hash the ledger recorded; nothing written),
    ``unreadable`` (the file could not be read: missing, altered, or the envelope refused it).
    """

    key: str
    outcome: str
    detail: str


def requeue_orphans(conn: Connection) -> int:
    """Queue again the builds the ledger says are waiting or running that the queue lacks.

    A running build is queued with the attempts it used, so the retry limit still counts. Returns
    the number queued.
    """
    queue = job_queue_for(conn)
    found = conn.execute(
        _ORPHANS_SQL, {"no": False, "uploaded": UPLOADED, "processing": PROCESSING}
    ).all()
    for row in found:
        snapshot = registry.get_snapshot(conn, str(row.id))
        assert snapshot is not None
        queue.enqueue(
            conn,
            job_id=snapshot.id,
            kind=JOB_KIND_BUILD,
            scope=snapshot.scope,
            now=utcnow(),
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            attempt=max(0, snapshot.attempts - (1 if snapshot.state == PROCESSING else 0)),
        )
    return len(found)


def requeue(target: DbTarget) -> int:
    """:func:`requeue_orphans` in its own transaction (what ``tl xer reconcile`` calls)."""
    with open_uow(target) as uow:
        return requeue_orphans(uow.conn())


def rows_complete(conn: Connection, snapshot: registry.SnapshotRow) -> bool:
    """Whether every typed table holds as many rows as ``Built`` recorded."""
    counted = typed_store.count_rows(conn, snapshot.id)
    return all(
        counted[key] == (getattr(snapshot, field) or 0) for key, field in _COUNT_FIELDS.items()
    )


def reconcile_tables(
    target: DbTarget,
    files: FileService,
    *,
    scope: str | None = None,
    timeout_s: float | None = None,
    memory_limit_mb: int | None = None,
    reader: Any = read_xer_file,
) -> list[Reconciled]:
    """Check the typed rows of every built snapshot (of ``scope``, or all); write the missing."""
    limits: dict[str, Any] = {}
    if timeout_s is not None:
        limits["timeout_s"] = timeout_s
    if memory_limit_mb is not None:
        limits["memory_limit_mb"] = memory_limit_mb
    store = SnapshotFiles(files)
    params: dict[str, Any] = dict(zip("abc", BUILT_STATES, strict=True))
    sql = _BUILT_SQL
    if scope is not None:
        sql += " AND t.scope = :scope"
        params["scope"] = scope
    with open_uow(target, readonly=True) as uow:
        ids = [str(r.id) for r in uow.conn().execute(text(sql + " ORDER BY t.id"), params)]
    done: list[Reconciled] = []
    for snapshot_id in ids:
        done.append(_one(target, store, snapshot_id, reader, limits))
    return done


def _one(
    target: DbTarget, store: SnapshotFiles, snapshot_id: str, reader: Any, limits: dict[str, Any]
) -> Reconciled:
    with open_uow(target, readonly=True) as uow:
        snapshot = registry.get_snapshot(uow.conn(), snapshot_id)
        assert snapshot is not None
        if rows_complete(uow.conn(), snapshot):
            return Reconciled(snapshot.key, "ok", "the typed rows are complete")
        schedule = registry.get_schedule(uow.conn(), snapshot.schedule_id)
        if snapshot.source_file_id is None or snapshot.source_sha256 is None or schedule is None:
            return Reconciled(snapshot.key, "unreadable", "the ledger has no source file")
        try:
            data = store.read_source(
                uow, snapshot.scope, snapshot.source_file_id, snapshot.source_sha256
            )
        except Exception as exc:  # a missing, quarantined or altered file
            return Reconciled(snapshot.key, "unreadable", type(exc).__name__)
    project = snapshot.p6_project_option or schedule.p6_project
    try:
        outcome = reader(data, Options(project=project), **limits)
    except XerLimitError:
        return Reconciled(snapshot.key, "unreadable", "reading the file broke the resource limits")
    if (
        outcome.status != "valid"
        or outcome.snapshot is None
        or outcome.typed_sha256 != snapshot.typed_sha256
    ):
        return Reconciled(
            snapshot.key, "mismatch", "the file no longer gives the typed rows the ledger recorded"
        )
    with open_uow(target) as uow:
        typed_store.clear_snapshot(uow.conn(), snapshot.id)
        typed_store.write_snapshot(uow.conn(), snapshot.scope, snapshot.id, outcome.snapshot)
    return Reconciled(snapshot.key, "rebuilt", f"{snapshot.activity_count} activities written")


__all__ = ["Reconciled", "reconcile_tables", "requeue", "requeue_orphans", "rows_complete"]
