"""In-memory derivation for `FakeClient` (P1-I3): the derivation methods of `ClientInterface`.

It holds `DerivedView`s, `JobView`s, row pages, reports, diffs and publish plans by project and
answers the reads the way the embedded client does: by id or key, the module's errors for an
unknown name or a stage not yet reached. The commands change the stored state the way the pipeline
would after a worker ran (a started extraction leaves a queued job and a Processing document;
cancelling ends it; publishing needs `is_admin` or `is_controller`) and record every command in
`derivation_commands`. `test_fakes_derivation.py` checks the fake, and the T07 screens use it.
"""

from __future__ import annotations

from typing import Any, cast

from tl_core.auth.errors import ForbiddenError
from tl_core.derivation.types import Cell
from tl_core.services.commands import CommandResult
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.derived import (
    CancelJob,
    OpenDerivedDocument,
    StartExtraction,
    ValidateDerived,
    VoidDerivedDocument,
)
from tl_mod_documents.derivation.diff import DerivedDiff, FieldChange, RowChange
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    CompensationItem,
    CompensationPlan,
    PlanRow,
    PublishDerivedDocuments,
    PublishDerivedTags,
    PublishPlan,
)
from tl_mod_documents.derivation.validation import Issue, ValidationReport
from tl_mod_documents.errors import (
    DerivedNotFoundError,
    DerivedStateError,
    JobNotFoundError,
    JobStateError,
    PublishRefusedError,
)

COLUMNS = ["tag", "service", "type", "size_in"]


def _row(*cells: str) -> dict[str, Cell]:
    return dict(zip(COLUMNS, cells, strict=True))


class FakeDerivationSupport:
    """Mixin for `FakeClient`: call `_init_derivation()` from its `__init__`."""

    def _init_derivation(self) -> None:
        self._dv_derived: dict[str, dict[str, views.DerivedView]] = {}
        self._dv_jobs: dict[str, dict[str, views.JobView]] = {}
        self._dv_pages: dict[tuple[str, int], views.RowsPage] = {}
        self._dv_reports: dict[tuple[str, int], ValidationReport] = {}
        self._derivation_diffs: dict[str, DerivedDiff] = {}
        self._dv_plans: dict[str, PublishPlan] = {}
        self._dv_compensations: dict[str, CompensationPlan] = {}
        self.derivation_commands: list[object] = []
        self.is_admin = True  # False: publishing tags and compensating raise ForbiddenError
        self._derivation_seq = 0

    # --- seeding -------------------------------------------------------------------------------

    def seed_derivation(self, project: str = "P123") -> None:
        """Three derived documents and their jobs, for the T07 screens' tests.

        ``ISD-001@A/instrument-index`` is Valid (3 rows, a clean report, a create-only plan and a
        diff against its previous pass). ``ISD-002@A/...`` is Invalid (2 errors and a warning).
        ``ISD-003@A/...`` is Processing with a running job. Jobs: one succeeded, one failed, one
        running; a queued one appears once a test starts an extraction.
        """
        good = self._add_derived(project, "ISD-001", "Valid", rev=2, errors=0, rows=3)
        bad = self._add_derived(project, "ISD-002", "Invalid", rev=1, errors=2, rows=2)
        busy = self._add_derived(project, "ISD-003", "Processing", rev=0, errors=None, rows=None)
        self._add_job(project, good.id, good.key, "succeeded")
        self._add_job(project, bad.id, bad.key, "failed", error="extractor timed out")
        running = self._add_job(project, busy.id, busy.key, "running")
        self._dv_derived[project][busy.id] = busy.model_copy(update={"active_job": running})
        rows = [
            _row("47-FV-1001", "Feed", "CV", "4"),
            _row("47-FV-1002", "Return", "HV", "6"),
            _row("47-HV-2001", "Vent", "PSV", "2"),
        ]
        for rev in (1, 2):
            self._dv_pages[(good.id, rev)] = self._dv_page(good.id, rev, rows)
            self._dv_reports[(good.id, rev)] = self._dv_report("valid", 3, [])
        bad_rows = [_row("47-FV-1001", "Feed", "CV", "4"), _row("47-HV-2001", "Vent", "XX", "2")]
        self._dv_pages[(bad.id, 1)] = self._dv_page(bad.id, 1, bad_rows)
        self._dv_reports[(bad.id, 1)] = self._dv_report(
            "invalid",
            2,
            [
                Issue(
                    level="error", code="enum", message="'XX' is not one of CV, HV, PSV",
                    row=2, column="type", value="XX",
                ),
                Issue(
                    level="error", code="required", message="'size_in' is required",
                    row=2, column="size_in", value=None,
                ),
                Issue(level="warning", code="unknown_column", message="column 'note' is ignored"),
            ],
        )  # fmt: skip
        self._derivation_diffs[good.id] = DerivedDiff(
            key_column="tag",
            added=["47-HV-2001"],
            removed=[],
            changed=[
                RowChange(
                    key="47-FV-1002", fields=[FieldChange(column="size_in", old="8", new="6")]
                )
            ],
            added_count=1,
            removed_count=0,
            changed_count=1,
            unchanged_count=1,
            columns_added=[],
            columns_removed=[],
            duplicate_keys=[],
            blank_key_rows=0,
            truncated=False,
        )
        self._dv_plans[good.id] = PublishPlan(
            derived_id=good.id,
            derived_key=good.key,
            content_rev=2,
            target="tags",
            schema_key="instrument-index@1.0.0",
            source_ref="src.doc.ISD-001@A",
            mapping_hash="m" * 64,
            result_sha256="r" * 64,
            counts={"create": 2, "exists": 1, "differs": 0, "invalid": 0},
            rows=[
                PlanRow(row=1, key="47-FV-1001", action="create", values={"class": "ControlValve"}),
                PlanRow(row=2, key="47-FV-1002", action="create", values={"class": "ManualValve"}),
                PlanRow(row=3, key="47-HV-2001", action="exists"),
            ],
            problems=[],
            can_publish=True,
            needs_skip_existing=True,
            truncated=False,
        )

    def _dv_id(self, prefix: str) -> str:
        self._derivation_seq += 1
        return f"{prefix}{self._derivation_seq:023d}"

    def _add_derived(
        self,
        project: str,
        number: str,
        state: str,
        *,
        rev: int,
        errors: int | None,
        rows: int | None,
    ) -> views.DerivedView:
        key = f"{number}@A/instrument-index"
        derived = views.DerivedView(
            id=self._dv_id("DRV"),
            scope=f"project:{project}",
            key=key,
            title=f"Instrument index of {number}",
            state=state,
            version=3,
            source_document_id=f"DOC-{number}",
            source_revision_id=f"REV-{number}-A",
            source_document_number=number,
            source_revision_code="A",
            source_ref=f"src.doc.{number}@A",
            schema_id="SCH1",
            schema_code="instrument-index",
            schema_version="1.0.0",
            method="automated" if rev else "manual",
            previous_derived_id=None,
            content_rev=rev,
            published_rev=None,
            validation_status="none" if errors is None else ("valid" if errors == 0 else "invalid"),
            row_count=rows,
            error_count=errors,
            published_correlation_id=None,
            published_at=None,
            published_count=None,
            last_job_id=None,
            created_at="2026-10-01T09:00:00Z",
            updated_at="2026-10-01T09:05:00Z",
            contents=[
                views.ContentView(
                    content_rev=n, job_id=None, source_kind="upload", source_file_id=f"FILE{n}",
                    extractor="tabular", extractor_version="1", extraction_status="ok",
                    result_file_id=f"RES{n}", row_count=rows or 0, column_count=4, problem_count=0,
                    file_metadata=None, extractor_notes=[], schema_version="1.0.0",
                    validation_status="valid" if errors == 0 else "invalid",
                    error_count=errors or 0, warning_count=0, report_file_id=f"REP{n}",
                    published=False, created_at="2026-10-01T09:01:00Z",
                )
                for n in range(1, rev + 1)
            ],
        )  # fmt: skip
        self._dv_derived.setdefault(project, {})[derived.id] = derived
        return derived

    def _add_job(
        self,
        project: str,
        derived_id: str,
        derived_key: str,
        state: str,
        *,
        error: str | None = None,
    ) -> views.JobView:
        job = views.JobView(
            id=self._dv_id("JOB"), scope=f"project:{project}", key=f"JOB-{self._derivation_seq}",
            kind="extract", derived_id=derived_id, derived_key=derived_key,
            source_ref=derived_key.split("/")[0], source_file_id="FILE1", extractor="tabular",
            options={}, schema_id="SCH1", requested_by="user:alice", state=state,
            attempt=0 if state == "queued" else 1, max_attempts=3, worker=None,
            started_at=None if state == "queued" else "2026-10-01T09:00:10Z",
            finished_at=None if state in ("queued", "running") else "2026-10-01T09:00:20Z",
            error_code="timeout" if error else None, error_message=error, result=None,
            created_at="2026-10-01T09:00:00Z",
        )  # fmt: skip
        self._dv_jobs.setdefault(project, {})[job.id] = job
        return job

    @staticmethod
    def _dv_page(derived_id: str, rev: int, rows: list[dict[str, Cell]]) -> views.RowsPage:
        return views.RowsPage(
            derived_id=derived_id, content_rev=rev, extractor="tabular", columns=COLUMNS,
            total=len(rows), offset=0, rows=rows, problems=[], notes=[],
        )  # fmt: skip

    @staticmethod
    def _dv_report(status: str, rows: int, issues: list[Issue]) -> ValidationReport:
        errors = [i for i in issues if i.level == "error"]
        return ValidationReport(
            schema_code="instrument-index", schema_version="1.0.0",
            status=cast(Any, status), rows_checked=rows,
            rows_with_errors=len({i.row for i in errors if i.row is not None}),
            error_count=len(errors), warning_count=len(issues) - len(errors), issues=issues,
            truncated=False,
        )  # fmt: skip

    # --- lookups -------------------------------------------------------------------------------

    def _dv_find(self, project: str, ref: str) -> views.DerivedView:
        known = self._dv_derived.get(project, {})
        found = known.get(ref) or next((d for d in known.values() if d.key == ref), None)
        if found is None:
            raise DerivedNotFoundError(f"no derived document {ref!r} in scope 'project:{project}'")
        return found

    def _dv_project_of(self, scope: str) -> str:
        return scope.removeprefix("project:")

    def _dv_store(self, derived: views.DerivedView) -> None:
        self._dv_derived[self._dv_project_of(derived.scope)][derived.id] = derived

    # --- reads ---------------------------------------------------------------------------------

    def list_derived_documents(
        self,
        project: str,
        *,
        state: str | None = None,
        document: str | None = None,
        schema: str | None = None,
        include_void: bool = False,
        limit: int = 200,
    ) -> list[views.DerivedSummary]:
        self.calls.append("list_derived_documents")  # type: ignore[attr-defined]
        found = [
            views.DerivedSummary.model_validate(d.model_dump(exclude={"contents", "active_job"}))
            for d in self._dv_derived.get(project, {}).values()
            if (state is None or d.state == state)
            and (document is None or d.source_document_number == document)
            and (schema is None or d.schema_code == schema)
            and (include_void or d.state != "Void")
        ]
        return found[:limit]

    def get_derived_document(self, project: str, ref: str) -> views.DerivedView:
        self.calls.append("get_derived_document")  # type: ignore[attr-defined]
        return self._dv_find(project, ref)

    def list_processing_jobs(
        self,
        project: str,
        *,
        state: str | None = None,
        derived: str | None = None,
        limit: int = 200,
    ) -> list[views.JobView]:
        self.calls.append("list_processing_jobs")  # type: ignore[attr-defined]
        derived_id = self._dv_find(project, derived).id if derived is not None else None
        jobs = [
            j
            for j in reversed(list(self._dv_jobs.get(project, {}).values()))
            if (state is None or j.state == state)
            and (derived_id is None or j.derived_id == derived_id)
        ]
        return jobs[:limit]

    def get_processing_job(self, project: str, job_id: str) -> views.JobView:
        self.calls.append("get_processing_job")  # type: ignore[attr-defined]
        job = self._dv_jobs.get(project, {}).get(job_id)
        if job is None:
            raise JobNotFoundError(f"no job {job_id!r} in scope 'project:{project}'")
        return job

    def _dv_rev(self, derived: views.DerivedView, content_rev: int | None) -> int:
        rev = derived.content_rev if content_rev is None else content_rev
        if rev < 1:
            raise DerivedStateError(f"{derived.key} has no extracted data yet")
        return rev

    def get_derived_rows(
        self,
        project: str,
        ref: str,
        *,
        content_rev: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> views.RowsPage:
        self.calls.append("get_derived_rows")  # type: ignore[attr-defined]
        derived = self._dv_find(project, ref)
        rev = self._dv_rev(derived, content_rev)
        page = self._dv_pages.get((derived.id, rev))
        if page is None:
            raise DerivedStateError(f"{derived.key} has no content revision {rev}")
        start = max(offset, 0)
        return page.model_copy(
            update={"offset": start, "rows": page.rows[start : start + max(limit, 1)]}
        )

    def get_derived_report(
        self, project: str, ref: str, *, content_rev: int | None = None
    ) -> ValidationReport:
        self.calls.append("get_derived_report")  # type: ignore[attr-defined]
        derived = self._dv_find(project, ref)
        rev = self._dv_rev(derived, content_rev)
        report = self._dv_reports.get((derived.id, rev))
        if report is None:
            raise DerivedStateError(f"{derived.key} revision {rev} has not been validated")
        return report

    def get_derived_diff(
        self,
        project: str,
        ref: str,
        *,
        against: str = "previous_pass",
        content_rev: int | None = None,
    ) -> DerivedDiff:
        self.calls.append("get_derived_diff")  # type: ignore[attr-defined]
        derived = self._dv_find(project, ref)
        found = self._derivation_diffs.get(derived.id)
        if found is None:
            raise DerivedStateError(f"{derived.key}: there is no earlier data to compare with")
        return found

    def get_publish_preview(
        self, project: str, ref: str, *, target: str | None = None
    ) -> PublishPlan:
        self.calls.append("get_publish_preview")  # type: ignore[attr-defined]
        derived = self._dv_find(project, ref)
        found = self._dv_plans.get(derived.id)
        if found is None:
            raise DerivedStateError(f"{derived.key} is {derived.state}: nothing to publish")
        return found

    def get_compensation_preview(self, project: str, ref: str) -> CompensationPlan:
        self.calls.append("get_compensation_preview")  # type: ignore[attr-defined]
        derived = self._dv_find(project, ref)
        found = self._dv_compensations.get(derived.id)
        if found is not None:
            return found
        return CompensationPlan(
            derived_id=derived.id,
            derived_key=derived.key,
            import_correlation_id=None,
            items=[],
            problems=[f"{derived.key} is {derived.state}: there is no publication to roll back"],
            can_compensate=False,
        )

    # --- commands ------------------------------------------------------------------------------

    def _dv_done(self, stream_id: str, key: str | None = None, version: int = 4) -> CommandResult:
        return CommandResult(stream_id=stream_id, key=key, version=version, events=[])

    def open_derived_document(self, cmd: OpenDerivedDocument) -> CommandResult:
        self.calls.append("open_derived_document")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        project = self._dv_project_of(cmd.scope)
        number = cmd.revision_id.removeprefix("REV-").rsplit("-", 1)[0]
        derived = self._add_derived(project, number, "Pending", rev=0, errors=None, rows=None)
        return self._dv_done(derived.id, derived.key, 2)

    def start_extraction(self, cmd: StartExtraction) -> CommandResult:
        self.calls.append("start_extraction")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        project = self._dv_project_of(cmd.scope)
        derived = self._dv_find(project, cmd.derived_id or "")
        if derived.state == "Processing":
            raise DerivedStateError(f"{derived.key} is being processed; wait or cancel the job")
        job = self._add_job(project, derived.id, derived.key, "queued")
        self._dv_store(derived.model_copy(update={"state": "Processing", "active_job": job}))
        return self._dv_done(job.id, job.key)

    def validate_derived(self, cmd: ValidateDerived) -> CommandResult:
        self.calls.append("validate_derived")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        project = self._dv_project_of(cmd.scope)
        derived = self._dv_find(project, cmd.derived_id)
        self._dv_rev(derived, cmd.content_rev)
        job = self._add_job(project, derived.id, derived.key, "queued")
        self._dv_store(derived.model_copy(update={"state": "Processing", "active_job": job}))
        return self._dv_done(job.id, job.key)

    def cancel_job(self, cmd: CancelJob) -> CommandResult:
        self.calls.append("cancel_job")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        project = self._dv_project_of(cmd.scope)
        job = self.get_processing_job(project, cmd.job_id)
        if job.state != "queued":
            raise JobStateError(f"job {job.key} is {job.state}; only a queued job can be cancelled")
        self._dv_jobs[project][job.id] = job.model_copy(update={"state": "cancelled"})
        derived = self._dv_find(project, job.derived_id)
        back = "Valid" if derived.validation_status == "valid" else "Pending"
        self._dv_store(derived.model_copy(update={"state": back, "active_job": None}))
        return self._dv_done(job.id, job.key)

    def void_derived_document(self, cmd: VoidDerivedDocument) -> CommandResult:
        self.calls.append("void_derived_document")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        if not (self.is_admin or self.is_controller):  # type: ignore[attr-defined]
            raise ForbiddenError("this action needs the document_controller or admin role")
        derived = self._dv_find(self._dv_project_of(cmd.scope), cmd.stream_id)
        if derived.state in ("Processing", "Published"):
            raise DerivedStateError(f"{derived.key} is {derived.state}: it cannot be voided")
        self._dv_store(derived.model_copy(update={"state": "Void"}))
        return self._dv_done(derived.id, derived.key)

    def _dv_publish(self, cmd: PublishDerivedTags | PublishDerivedDocuments) -> CommandResult:
        project = self._dv_project_of(cmd.scope)
        derived = self._dv_find(project, cmd.derived_id)
        plan = self._dv_plans.get(derived.id)
        if derived.state != "Valid" or plan is None:
            raise PublishRefusedError(f"{derived.key} is {derived.state}", [])
        if cmd.expected_content_rev != derived.content_rev:
            raise PublishRefusedError(
                f"{derived.key} has a newer pass than {cmd.expected_content_rev}", []
            )
        if plan.needs_skip_existing and not cmd.skip_existing:
            raise PublishRefusedError("rows exist already; say skip_existing", [])
        created = plan.counts["create"]
        correlation = self._dv_id("COR")
        self._dv_store(
            derived.model_copy(
                update={
                    "state": "Published",
                    "published_rev": derived.content_rev,
                    "published_correlation_id": correlation,
                    "published_count": created,
                    "published_at": "2026-10-02T10:00:00Z",
                }
            )  # fmt: skip
        )
        self._dv_compensations[derived.id] = CompensationPlan(
            derived_id=derived.id, derived_key=derived.key, import_correlation_id=correlation,
            items=[
                CompensationItem(
                    record_id=f"REC{n}", key=row.key, record_type="engineering.Tag", state="Active",
                    action="delete_tag", reversible=True,
                )
                for n, row in enumerate((r for r in plan.rows if r.action == "create"), start=1)
            ],
            problems=[], can_compensate=True,
        )  # fmt: skip
        return self._dv_done(derived.id, derived.key, 5)

    def publish_derived_tags(self, cmd: PublishDerivedTags) -> CommandResult:
        self.calls.append("publish_derived_tags")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        if not self.is_admin:
            raise ForbiddenError("this action needs the admin role")
        return self._dv_publish(cmd)

    def publish_derived_documents(self, cmd: PublishDerivedDocuments) -> CommandResult:
        self.calls.append("publish_derived_documents")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        if not (self.is_admin or self.is_controller):  # type: ignore[attr-defined]
            raise ForbiddenError("this action needs the document_controller or admin role")
        return self._dv_publish(cmd)

    def compensate_publication(self, cmd: CompensatePublication) -> CommandResult:
        self.calls.append("compensate_publication")  # type: ignore[attr-defined]
        self.derivation_commands.append(cmd)
        if not self.is_admin:
            raise ForbiddenError("this action needs the admin role")
        derived = self._dv_find(self._dv_project_of(cmd.scope), cmd.derived_id)
        plan = self._dv_compensations.get(derived.id)
        if derived.state != "Published" or plan is None:
            raise DerivedStateError(
                f"{derived.key} is {derived.state}: no publication to roll back"
            )
        self._dv_store(
            derived.model_copy(
                update={
                    "state": "Valid",
                    "published_rev": None,
                    "published_correlation_id": None,
                    "published_count": None,
                }
            )  # fmt: skip
        )
        del self._dv_compensations[derived.id]
        return self._dv_done(derived.id, derived.key, 6)
