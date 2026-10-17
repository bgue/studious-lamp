"""The job kinds of the derivation pipeline: ``extract`` and ``validate`` (ADR-0014).

The generic worker loop (``tl_core.jobs.JobRunner``) claims a job and calls these in three steps:

* ``started`` appends ``ProcessingJob.Started`` in the claim's transaction;
* ``prepare`` (read-only) reads the job, the schema and the bytes of the file; ``run`` (no
  transaction) runs the extractor in a child process under a wall-clock limit
  (``tl_core.derivation.isolated``) and validates what it read;
* ``settle`` (write, only if the claim is still the worker's) stores the rows and the report as
  files, appends the content, validation and job events and moves the derived document on.

A failure of an attempt appends ``ProcessingJob.Failed``; when it is the last the derived document
returns to the state its latest validation names (the job lost nothing). An extractor that times
out or is killed fails the job (a timeout for good, a crash may be retried); a file the extractor
reads badly (not UTF-8, ragged rows) is not a failed job but a content revision whose report says
what is wrong, so the person sees it where they fix it.

``reconcile_orphans`` re-queues jobs whose record says queued or running but that have no queue row,
which is what a restore from the ledger archive leaves (the queue is operational, not a projection).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_adapters.queue import job_queue_for
from tl_core.derivation.isolated import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIMEOUT_S,
    ExtractorSelectionError,
    run_isolated,
)
from tl_core.derivation.types import MAX_SOURCE_BYTES, ExtractionResult
from tl_core.files.queries import get_file
from tl_core.files.service import FileService
from tl_core.jobs import Claim, Expired, JobFailure
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command
from tl_core.services.errors import ServiceError
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_documents.derivation import rows
from tl_mod_documents.derivation.derived import finish_transition, source_file_of
from tl_mod_documents.derivation.store import ACTOR, SOURCE, ResultFiles
from tl_mod_documents.derivation.validation import ValidationReport
from tl_mod_documents.derivation.validation_isolated import validate_isolated
from tl_mod_documents.errors import ValidationFailedError
from tl_mod_documents.handlers.common import append, version_of
from tl_mod_documents.names import (
    DD_PROCESSING,
    DERIVED_CONTENT_RECORDED,
    DERIVED_DOCUMENT,
    DERIVED_VALIDATED,
    JOB_FAILED,
    JOB_KIND_EXTRACT,
    JOB_KIND_VALIDATE,
    JOB_STARTED,
    JOB_SUCCEEDED,
    PROCESSING_JOB,
    SLOT_EXTRACTED,
    SLOT_REPORT,
)

#: Problem codes of the child-process wrapper that fail the job instead of recording a pass.
#: ``extraction_limit`` (FANOUT D9: time, memory, CPU, a crash of the child) and a result that
#: breaks the contract are final; a failure inside the plugin may be tried again.
JOB_FAILING_CODES = {
    "extraction_limit": False,
    "contract_violation": False,
    "extractor_crashed": True,
}  # code to "may be retried"


@dataclass(frozen=True)
class Work:
    """What ``prepare`` read for ``run``: plain data, so ``run`` needs no connection."""

    job: rows.JobRow
    derived: rows.DerivedRow
    schema: rows.SchemaRow
    source: Any  # SourceFile (extract jobs)
    data: bytes  # the bytes of the file to read, or of the stored result (validate jobs)
    source_kind: str
    content_rev: int  # validate jobs: the pass being checked


@dataclass(frozen=True)
class Outcome:
    job: rows.JobRow
    derived_id: str
    schema: rows.SchemaRow
    source_kind: str
    source_file_id: str | None
    result: ExtractionResult | None
    result_bytes: bytes | None
    report: ValidationReport | None
    content_rev: int  # validate jobs: the pass checked


def _canonical(model: Any) -> bytes:
    return model.model_dump_json().encode("utf-8")


def _command(job: rows.JobRow, correlation_id: str | None = None) -> Command:
    """The identity every event of the worker carries (the worker is a service)."""
    return Command(
        actor=ACTOR,
        source=SOURCE,
        scope=job.scope,
        correlation_id=correlation_id or new_ulid(),
    )


def _read_file(
    files: ResultFiles, uow: UnitOfWork, scope: str, file_id: str, limit: int
) -> tuple[bytes, Any]:
    info = get_file(uow, scope, file_id)
    if info.status == "rejected":
        raise JobFailure("source_rejected", "the file was rejected by the scan", retryable=False)
    if info.status != "available":
        raise JobFailure("source_not_available", "the file is still in quarantine")
    if info.size > limit:
        raise JobFailure(
            "source_too_large",
            f"the file is {info.size} bytes; the limit is {limit}",
            retryable=False,
        )
    return files.read(uow, scope, file_id), info


class _Base:
    kind = ""

    def __init__(self, files: FileService) -> None:
        self._files = files
        self._results = ResultFiles(files)

    # --- the events every kind shares ----------------------------------------------------

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        job = self._job(uow, claim.job_id)
        append(
            uow,
            _command(job),
            job.id,
            PROCESSING_JOB,
            [
                NewEvent(
                    event_type=JOB_STARTED,
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
        job = self._job(uow, claim.job_id)
        cmd = _command(job)
        append(
            uow,
            cmd,
            job.id,
            PROCESSING_JOB,
            [
                NewEvent(
                    event_type=JOB_FAILED,
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
            self._release_derived(uow, cmd, job)

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        job = self._job(uow, item.job_id)
        cmd = _command(job)
        append(
            uow,
            cmd,
            job.id,
            PROCESSING_JOB,
            [
                NewEvent(
                    event_type=JOB_FAILED,
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
        self._release_derived(uow, cmd, job)

    # --- helpers --------------------------------------------------------------------------

    @staticmethod
    def _job(uow: UnitOfWork, job_id: str) -> rows.JobRow:
        job = rows.get_job(uow.conn(), job_id)
        if job is None:
            raise JobFailure("job_missing", "the job record does not exist", retryable=False)
        return job

    @staticmethod
    def _release_derived(uow: UnitOfWork, cmd: Command, job: rows.JobRow) -> None:
        """Move the derived document out of Processing once its job has ended for good."""
        derived = rows.get_derived(uow.conn(), job.derived_id)
        if derived is not None and derived.state == DD_PROCESSING:
            _move(uow, cmd, derived)

    def _load(
        self, uow: UnitOfWork, claim: Claim
    ) -> tuple[rows.JobRow, rows.DerivedRow, rows.SchemaRow]:
        job = self._job(uow, claim.job_id)
        derived = rows.get_derived(uow.conn(), job.derived_id)
        schema = rows.get_schema(uow.conn(), job.schema_id)
        if derived is None or derived.voided:
            raise JobFailure("derived_closed", "the derived document is void", retryable=False)
        if schema is None:
            raise JobFailure(
                "schema_missing", "the document schema does not exist", retryable=False
            )
        return job, derived, schema

    def _store_report(
        self, uow: UnitOfWork, cmd: Command, derived_id: str, rev: int, report: ValidationReport
    ) -> tuple[str, str]:
        stored = self._results.write(
            uow,
            scope=cmd.scope,
            record_id=derived_id,
            slot=SLOT_REPORT,
            filename=f"report-{rev:04d}.json",
            data=_canonical(report),
            correlation_id=cmd.correlation_id or new_ulid(),
        )
        return stored.file_id, stored.sha256

    def _validated_event(
        self,
        schema: rows.SchemaRow,
        report: ValidationReport,
        rev: int,
        file_id: str,
        sha256: str,
        job_id: str,
    ) -> NewEvent:
        return NewEvent(
            event_type=DERIVED_VALIDATED,
            payload={
                "content_rev": rev,
                "schema_id": schema.id,
                "schema_code": schema.code,
                "schema_version": schema.semver,
                "validation_status": report.status,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "report_file_id": file_id,
                "report_sha256": sha256,
                "job_id": job_id,
            },
        )

    def _succeeded(self, claim: Claim, summary: dict[str, Any]) -> NewEvent:
        return NewEvent(
            event_type=JOB_SUCCEEDED, payload={"attempt": claim.attempt, "result": summary}
        )


def _move(uow: UnitOfWork, cmd: Command, derived: rows.DerivedRow, name: str | None = None) -> None:
    handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            stream_id=derived.id,
            expected_version=version_of(uow, derived.id),
            transition=name or finish_transition(derived),
        ),
        by_module=True,
    )


def _validated(
    schema: rows.SchemaRow,
    result: ExtractionResult,
    timeout_s: float,
    memory_limit_mb: int | None,
) -> ValidationReport:
    """Validate in a child process; a breach or an unusable schema fails the job for good."""
    try:
        return validate_isolated(
            schema.json_schema,
            result.columns,
            result.rows,
            schema_code=schema.code,
            schema_version=schema.semver,
            key_column=schema.key_column,
            problems=result.problems,
            timeout_s=timeout_s,
            memory_limit_mb=memory_limit_mb,
        )
    except ValidationFailedError as exc:
        raise JobFailure(exc.code, str(exc), retryable=False) from exc


class ExtractKind(_Base):
    """Read a file with an extractor, store the rows and check them against the schema."""

    kind = JOB_KIND_EXTRACT

    def __init__(
        self,
        files: FileService,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
        factory: str | None = None,
    ) -> None:
        super().__init__(files)
        self._timeout_s = timeout_s
        self._memory_limit_mb = memory_limit_mb
        self._factory = factory

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Work:
        job, derived, schema = self._load(uow, claim)
        if job.source_file_id is None:
            raise JobFailure("no_source", "the job names no file", retryable=False)
        data, info = _read_file(self._results, uow, job.scope, job.source_file_id, MAX_SOURCE_BYTES)
        kind = "upload" if info.record_id == derived.id else "rendition"
        return Work(job, derived, schema, source_file_of(info, derived.source_ref), data, kind, 0)

    def run(self, work: Work) -> Outcome:
        try:
            result = run_isolated(
                work.source,
                work.data,
                name=work.job.extractor,
                options=work.job.options,
                timeout_s=self._timeout_s,
                memory_limit_mb=self._memory_limit_mb,
                factory=self._factory,
            )
        except ExtractorSelectionError as exc:
            raise JobFailure("no_extractor", str(exc)[:300], retryable=False) from exc
        for problem in result.problems:
            if result.status == "failed" and problem.code in JOB_FAILING_CODES:
                raise JobFailure(
                    problem.code, problem.message, retryable=JOB_FAILING_CODES[problem.code]
                )
        report: ValidationReport | None = None
        if result.status in ("ok", "failed", "unsupported"):
            report = _validated(work.schema, result, self._timeout_s, self._memory_limit_mb)
        return Outcome(
            work.job,
            work.derived.id,
            work.schema,
            work.source_kind,
            work.source.file_id,
            result,
            _canonical(result),
            report,
            0,
        )

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Outcome) -> None:
        job = outcome.job
        cmd = _command(job)
        derived = rows.get_derived(uow.conn(), outcome.derived_id)
        if derived is None or derived.voided or derived.state != DD_PROCESSING:
            raise ServiceError(f"{job.derived_key} is no longer waiting for this job")
        assert outcome.result is not None and outcome.result_bytes is not None
        result = outcome.result
        rev = derived.content_rev + 1
        stored = self._results.write(
            uow,
            scope=job.scope,
            record_id=derived.id,
            slot=SLOT_EXTRACTED,
            filename=f"extracted-{rev:04d}.json",
            data=outcome.result_bytes,
            correlation_id=cmd.correlation_id or new_ulid(),
        )
        method = _method_after(
            derived.method, outcome.source_kind, had_content=derived.content_rev > 0
        )
        meta = result.metadata
        append(
            uow,
            cmd,
            derived.id,
            DERIVED_DOCUMENT,
            [
                NewEvent(
                    event_type=DERIVED_CONTENT_RECORDED,
                    payload={
                        "content_rev": rev,
                        "job_id": job.id,
                        "source_kind": outcome.source_kind,
                        "source_file_id": outcome.source_file_id,
                        "extractor": result.extractor,
                        "extractor_version": result.extractor_version,
                        "extraction_status": result.status,
                        "result_file_id": stored.file_id,
                        "result_sha256": stored.sha256,
                        "row_count": len(result.rows),
                        "column_count": len(result.columns),
                        "problem_count": len(result.problems),
                        "file_metadata": None if meta is None else meta.model_dump(mode="json"),
                        "extractor_notes": result.notes,
                        "method": method,
                    },
                )
            ],
        )
        validation = None
        if outcome.report is not None:
            report_id, report_sha = self._store_report(uow, cmd, derived.id, rev, outcome.report)
            append(
                uow,
                cmd,
                derived.id,
                DERIVED_DOCUMENT,
                [
                    self._validated_event(
                        outcome.schema, outcome.report, rev, report_id, report_sha, job.id
                    )
                ],
            )
            validation = outcome.report.status
        _move(
            uow,
            cmd,
            derived,
            {"valid": "finish_valid", "invalid": "finish_invalid"}.get(
                validation or "", "finish_pending"
            ),
        )
        append(
            uow,
            cmd,
            job.id,
            PROCESSING_JOB,
            [
                self._succeeded(
                    claim,
                    {
                        "content_rev": rev,
                        "extraction_status": result.status,
                        "rows": len(result.rows),
                        "validation_status": validation,
                    },
                )
            ],
        )


def _method_after(current: str, source_kind: str, *, had_content: bool) -> str:
    """manual, automated or hybrid after a pass from a rendition or an upload."""
    now = "automated" if source_kind == "rendition" else "manual"
    if not had_content or current == now:
        return now
    return "hybrid"


class ValidateKind(_Base):
    """Check the stored rows of one pass against a schema version."""

    kind = JOB_KIND_VALIDATE

    def __init__(
        self,
        files: FileService,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
    ) -> None:
        super().__init__(files)
        self._timeout_s = timeout_s
        self._memory_limit_mb = memory_limit_mb

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Work:
        job, derived, schema = self._load(uow, claim)
        rev = int(job.options.get("content_rev") or derived.content_rev)
        content = rows.get_content(uow.conn(), derived.id, rev)
        if content is None or content.result_file_id is None:
            raise JobFailure("no_rows", "the pass has no stored rows", retryable=False)
        data = self._results.read(
            uow, job.scope, content.result_file_id, expect_sha256=content.result_sha256
        )
        return Work(job, derived, schema, None, data, "stored", rev)

    def run(self, work: Work) -> Outcome:
        result = ExtractionResult.model_validate_json(work.data)
        report = _validated(work.schema, result, self._timeout_s, self._memory_limit_mb)
        return Outcome(
            work.job,
            work.derived.id,
            work.schema,
            "stored",
            None,
            None,
            None,
            report,
            work.content_rev,
        )

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Outcome) -> None:
        job = outcome.job
        cmd = _command(job)
        derived = rows.get_derived(uow.conn(), outcome.derived_id)
        if derived is None or derived.voided or derived.state != DD_PROCESSING:
            raise ServiceError(f"{job.derived_key} is no longer waiting for this job")
        assert outcome.report is not None
        report_id, report_sha = self._store_report(
            uow, cmd, derived.id, outcome.content_rev, outcome.report
        )
        append(
            uow,
            cmd,
            derived.id,
            DERIVED_DOCUMENT,
            [
                self._validated_event(
                    outcome.schema,
                    outcome.report,
                    outcome.content_rev,
                    report_id,
                    report_sha,
                    job.id,
                )
            ],
        )
        refreshed = rows.get_derived(uow.conn(), derived.id)
        assert refreshed is not None
        _move(uow, cmd, refreshed)
        append(
            uow,
            cmd,
            job.id,
            PROCESSING_JOB,
            [
                self._succeeded(
                    claim,
                    {
                        "content_rev": outcome.content_rev,
                        "validation_status": outcome.report.status,
                    },
                )
            ],
        )


def make_kinds(
    files: FileService,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
    factory: str | None = None,
) -> list[ExtractKind | ValidateKind]:
    """The job kinds a worker serves."""
    return [
        ExtractKind(files, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, factory=factory),
        ValidateKind(files, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb),
    ]


_ORPHANS_SQL = text(
    "SELECT j.id, j.scope, j.kind, j.state, j.attempt, j.max_attempts "
    "FROM v_documents_processing_job j LEFT JOIN job_queue q ON q.job_id = j.id "
    "WHERE j.state IN ('queued', 'running') AND q.job_id IS NULL ORDER BY j.created_seq"
)


def reconcile_orphans(conn: Connection) -> int:
    """Queue again the jobs the ledger says are waiting or running that the queue does not hold.

    A restore from the archive rebuilds the job records but not ``job_queue`` (it is operational).
    A running job is queued with the attempts it used, so the retry limit still counts.
    Returns the number queued.
    """
    queue = job_queue_for(conn)
    found = conn.execute(_ORPHANS_SQL).all()
    for row in found:
        queue.enqueue(
            conn,
            job_id=row.id,
            kind=row.kind,
            scope=row.scope,
            now=utcnow(),
            max_attempts=int(row.max_attempts),
            attempt=int(row.attempt) - (1 if row.state == "running" else 0),
        )
    return len(found)
