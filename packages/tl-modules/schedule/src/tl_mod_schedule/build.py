"""The ``schedule.build`` job kind: read a snapshot's XER file, check it, write its typed rows.

The generic worker loop (``tl_core.jobs.JobRunner``) claims a job and calls this in three steps
(ADR-0014); the job id is the snapshot's id, and the snapshot is also the job record:

* ``started`` appends ``ScheduleSnapshot.BuildStarted`` and moves Uploaded to Processing, in the
  claim's transaction;
* ``prepare`` (read-only) reads the snapshot and the bytes of the file; ``run`` (no transaction)
  reads them in the resource envelope (``tl_xer.run``: a child process with limits on memory, CPU
  and wall clock, no pickle, every answer checked);
* ``settle`` (write, only if the claim is still the worker's) stores the report and the raw tables
  as files, writes the typed rows, appends ``Built`` or ``Rejected`` and moves the snapshot to
  Valid or Invalid.

A file that is merely bad (not an XER, fails the document schema) is not a failed job: the snapshot
is Invalid and its report says why, where the person who uploaded it will look. A breach of the
envelope fails the job for good (FANOUT D9): the snapshot is Invalid, with a ``BuildFailed`` event.

The typed rows are written by ``settle`` in the same transaction as the events. The worker's
transaction holds the writer lock while it writes: at the limits of the XER reader (60 000
activities) that is a few seconds on SQLite and tens of seconds on Postgres (the report records the
measure).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tl_core.files.service import FileService
from tl_core.jobs import Claim, Expired, JobFailure
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_xer.result import XerLimitError, XerResult
from tl_xer.run import read_xer_file
from tl_xer.typed import Options

from tl_mod_schedule import registry, typed_store
from tl_mod_schedule.common import append, transition
from tl_mod_schedule.names import (
    BUILD_FAILED,
    BUILD_STARTED,
    JOB_KIND_BUILD,
    PROCESSING,
    SCHEDULE_SNAPSHOT,
    SLOT_RAW,
    SLOT_REPORT,
    SNAPSHOT_BUILT,
    SNAPSHOT_REJECTED,
    UPLOADED,
)
from tl_mod_schedule.store import ACTOR, SOURCE, SnapshotFiles

LIMIT_MESSAGE = "reading the XER file broke the resource limits"


@dataclass(frozen=True)
class Work:
    """What ``prepare`` read for ``run``: plain data, so ``run`` needs no connection."""

    snapshot: registry.SnapshotRow
    data: bytes
    options: Options


def _command(scope: str, correlation_id: str | None = None) -> Command:
    """The identity every event of the worker carries (the worker is a service)."""
    return Command(
        actor=ACTOR, source=SOURCE, scope=scope, correlation_id=correlation_id or new_ulid()
    )


def report_bytes(report: dict[str, Any], snapshot: registry.SnapshotRow) -> bytes:
    """The stored report: the reader's report and what it was a report of."""
    document = {
        "snapshot": snapshot.key,
        "source_name": snapshot.source_name,
        "source_sha256": snapshot.source_sha256,
        **report,
    }
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


class BuildKind:
    kind = JOB_KIND_BUILD

    def __init__(
        self,
        files: FileService,
        *,
        timeout_s: float | None = None,
        memory_limit_mb: int | None = None,
        reader: Any = read_xer_file,
    ) -> None:
        self._store = SnapshotFiles(files)
        self._limits: dict[str, Any] = {}
        if timeout_s is not None:
            self._limits["timeout_s"] = timeout_s
        if memory_limit_mb is not None:
            self._limits["memory_limit_mb"] = memory_limit_mb
        self._reader = reader

    # --- the events every kind shares -------------------------------------------------------

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        snapshot = self._snapshot(uow, claim.job_id)
        cmd = _command(snapshot.scope)
        if snapshot.state == UPLOADED:
            transition(uow, cmd, snapshot.id, "start")
        elif snapshot.state != PROCESSING:
            raise JobFailure(
                "snapshot_state",
                f"the snapshot is {snapshot.state}, not Uploaded or Processing",
                retryable=False,
            )
        append(
            uow,
            cmd,
            snapshot.id,
            SCHEDULE_SNAPSHOT,
            [
                NewEvent(
                    event_type=BUILD_STARTED,
                    payload={
                        "attempt": claim.attempt,
                        "worker": claim.owner,
                        "lease_until": claim.lease_until,
                    },
                )
            ],
        )

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        snapshot = self._snapshot(uow, claim.job_id)
        cmd = _command(snapshot.scope)
        append(
            uow,
            cmd,
            snapshot.id,
            SCHEDULE_SNAPSHOT,
            [
                NewEvent(
                    event_type=BUILD_FAILED,
                    payload={
                        "attempt": claim.attempt,
                        "error_code": failure.code,
                        "error_message": failure.message,
                        "final": final,
                        "retry_at": retry_at,
                    },
                )
            ],
        )
        if final:
            self._release(uow, cmd, snapshot)

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        snapshot = self._snapshot(uow, item.job_id)
        cmd = _command(snapshot.scope)
        append(
            uow,
            cmd,
            snapshot.id,
            SCHEDULE_SNAPSHOT,
            [
                NewEvent(
                    event_type=BUILD_FAILED,
                    payload={
                        "attempt": item.attempt,
                        "error_code": "lease_expired",
                        "error_message": "the worker did not finish in time and no attempt is left",
                        "final": True,
                        "retry_at": None,
                    },
                )
            ],
        )
        self._release(uow, cmd, snapshot)

    # --- the work ---------------------------------------------------------------------------

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Work:
        snapshot = self._snapshot(uow, claim.job_id)
        if snapshot.state != PROCESSING or snapshot.source_file_id is None:
            raise JobFailure(
                "snapshot_state", "the snapshot is not waiting to be built", retryable=False
            )
        schedule = registry.get_schedule(uow.conn(), snapshot.schedule_id)
        if schedule is None:
            raise JobFailure("schedule_missing", "the schedule does not exist", retryable=False)
        assert snapshot.source_sha256 is not None
        try:
            data = self._store.read_source(
                uow, snapshot.scope, snapshot.source_file_id, snapshot.source_sha256
            )
        except Exception as exc:  # a quarantined, rejected or altered file
            raise JobFailure("source_unreadable", type(exc).__name__, retryable=False) from None
        project = snapshot.p6_project_option or schedule.p6_project
        return Work(snapshot, data, Options(project=project))

    def run(self, work: Work) -> XerResult:
        try:
            return self._reader(work.data, work.options, **self._limits)
        except XerLimitError:
            raise JobFailure("xer_limit", LIMIT_MESSAGE, retryable=False) from None

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: XerResult) -> None:
        snapshot = self._snapshot(uow, claim.job_id)
        cmd = _command(snapshot.scope)
        conn = uow.conn()
        stored_report = self._store.write(
            uow,
            scope=snapshot.scope,
            record_id=snapshot.id,
            slot=SLOT_REPORT,
            filename=f"report-{snapshot.number:04d}.json",
            data=report_bytes(outcome.report, snapshot),
            correlation_id=cmd.correlation_id or new_ulid(),
        )
        report = outcome.report
        if outcome.status == "valid":
            assert outcome.snapshot is not None and outcome.raw_gz is not None
            assert outcome.typed_sha256 is not None and outcome.raw_sha256 is not None
            stored_raw = self._store.write(
                uow,
                scope=snapshot.scope,
                record_id=snapshot.id,
                slot=SLOT_RAW,
                filename=f"raw-{snapshot.number:04d}.jsonl.gz",
                data=outcome.raw_gz,
                correlation_id=cmd.correlation_id or new_ulid(),
            )
            typed_store.write_snapshot(conn, snapshot.scope, snapshot.id, outcome.snapshot)
            project = outcome.snapshot.project
            append(
                uow,
                cmd,
                snapshot.id,
                SCHEDULE_SNAPSHOT,
                [
                    NewEvent(
                        event_type=SNAPSHOT_BUILT,
                        payload={
                            "data_date": project["data_date"],
                            "p6_version": project["export_version"],
                            "p6_project": project["short_name"],
                            "counts": outcome.snapshot.counts(),
                            "warning_count": report["warning_count"],
                            "typed_sha256": outcome.typed_sha256,
                            "raw_sha256": outcome.raw_sha256,
                            "report_file_id": stored_report.file_id,
                            "raw_file_id": stored_raw.file_id,
                        },
                    )
                ],
            )
            transition(uow, cmd, snapshot.id, "finish_valid")
            return
        append(
            uow,
            cmd,
            snapshot.id,
            SCHEDULE_SNAPSHOT,
            [
                NewEvent(
                    event_type=SNAPSHOT_REJECTED,
                    payload={
                        "outcome": outcome.status,
                        "error_count": report["error_count"],
                        "warning_count": report["warning_count"],
                        "first_codes": [
                            p["code"] for p in report["problems"] if p["severity"] == "error"
                        ][:5],
                        "report_file_id": stored_report.file_id,
                    },
                )
            ],
        )
        transition(uow, cmd, snapshot.id, "finish_invalid")

    # --- helpers ----------------------------------------------------------------------------

    @staticmethod
    def _snapshot(uow: UnitOfWork, job_id: str) -> registry.SnapshotRow:
        found = registry.get_snapshot(uow.conn(), job_id)
        if found is None:
            raise JobFailure("job_missing", "the snapshot record does not exist", retryable=False)
        return found

    @staticmethod
    def _release(uow: UnitOfWork, cmd: Command, snapshot: registry.SnapshotRow) -> None:
        """A build that failed for good leaves the snapshot Invalid (nothing was written)."""
        if snapshot.state == PROCESSING:
            transition(uow, cmd, snapshot.id, "finish_invalid")


def make_kinds(
    files: FileService, *, timeout_s: float | None = None, memory_limit_mb: int | None = None
) -> list[BuildKind]:
    return [BuildKind(files, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb)]


__all__ = ["BuildKind", "make_kinds", "report_bytes"]
