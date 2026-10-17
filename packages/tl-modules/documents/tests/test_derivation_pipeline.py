"""The pipeline end to end: open, extract, validate, fix, validate again, cancel, time out (S4).

The extractors run in a child process (`tl_core.derivation.isolated`) from the factory
`tl_core.derivation.testing:make_extractors`; the parent registry is the same set, so the early
check at `StartExtraction` sees them.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.derivation.types import ExtractionResult
from tl_mod_documents.derivation.derived import (
    CancelJob,
    OpenDerivedDocument,
    ValidateDerived,
    VoidDerivedDocument,
    handle_cancel_job,
    handle_open_derived_document,
    handle_validate_derived,
    handle_void_derived_document,
)
from tl_mod_documents.derivation.jobs import reconcile_orphans
from tl_mod_documents.derivation.store import ResultFiles, use_files
from tl_mod_documents.derivation.validation import ValidationReport
from tl_mod_documents.errors import (
    DerivedStateError,
    InvalidDocumentSchemaError,
    InvalidSourceError,
)
from tl_mod_documents.testing import index_csv

GOOD = [
    ("47-FV-1001", "Feed", "CV", "4"),
    ("47-FV-1002", "Return", "HV", "6"),
    ("47-HV-2001", "Vent", "PSV", "2"),
]
BAD = [*GOOD[:2], ("47-HV-2001", "Vent", "XX", "2")]  # an unknown type on row 3


@pytest.fixture(autouse=True)
def extractors(world: World) -> Iterator[None]:
    with use_extractors(make_extractors()), use_files(world.files):
        yield


@pytest.fixture
def ready(world: World) -> World:
    """ISD-001 revision A with a PDF, the schema registered, nothing extracted yet."""
    world.register("ISD-001", doc_type="IDX")
    world.create_revision("ISD-001")
    world.attach("ISD-001", "A")
    world.register_schema()
    return world


def report_of(world: World, content_rev: int) -> ValidationReport:
    derived_id = world.scalar("SELECT id FROM cur_documents_derived_document")
    content = [c for c in world.contents(derived_id) if c.content_rev == content_rev][0]
    assert content.report_file_id is not None
    with open_uow(world.db, readonly=True) as uow:
        data = ResultFiles(world.files).read(uow, BASE["scope"], content.report_file_id)
    return ValidationReport.model_validate_json(data)


def start(world: World, **fields: Any) -> str:
    return world.start_extraction(**fields).stream_id


def test_a_pdf_is_read_for_metadata_and_nothing_else(ready: World) -> None:
    rev = ready.revision("ISD-001", "A")
    job_id = start(ready, revision_id=rev.id, schema_code="instrument-index")
    derived = ready.derived_row(ready.jobs()[0].derived_id)
    assert derived.key == "ISD-001@A/instrument-index" and derived.state == "Processing"
    assert derived.source_ref == "src.doc.ISD-001@A" and derived.method == "automated"
    (result,) = ready.run_jobs()
    assert (result.job_id, result.outcome) == (job_id, "done")
    derived = ready.derived_row(derived.id)
    assert derived.state == "Pending" and derived.content_rev == 1
    assert derived.validation_status == "none" and derived.row_count == 0
    (content,) = ready.contents(derived.id)
    assert (content.extractor, content.extraction_status) == ("pdfstub", "metadata_only")
    assert content.source_kind == "rendition" and content.row_count == 0
    assert content.file_metadata is not None and content.file_metadata["size"] > 0
    assert any("ADR-0008" in note for note in content.extractor_notes)
    assert content.validation_status == "none" and content.report_file_id is None
    job = ready.jobs()[0]
    assert (job.state, job.attempt) == ("succeeded", 1)
    assert job.result is not None and job.result["extraction_status"] == "metadata_only"


def test_the_whole_story_pdf_then_a_bad_csv_then_the_fixed_one(ready: World) -> None:
    rev = ready.revision("ISD-001", "A")
    start(ready, revision_id=rev.id, schema_code="instrument-index")
    ready.run_jobs()
    derived_id = ready.jobs()[0].derived_id

    ready.upload_content(derived_id, index_csv(BAD))
    start(ready, derived_id=derived_id)  # the newest content file is the default source
    ready.run_jobs()
    derived = ready.derived_row(derived_id)
    assert derived.state == "Invalid" and derived.content_rev == 2
    assert derived.validation_status == "invalid" and derived.error_count == 1
    assert derived.method == "hybrid"
    report = report_of(ready, 2)
    assert report.status == "invalid" and report.rows_checked == 3
    (issue,) = report.issues
    assert (issue.row, issue.column, issue.code, issue.value) == (3, "type", "enum", "XX")

    ready.upload_content(derived_id, index_csv(GOOD), name="index-fixed.csv")
    start(ready, derived_id=derived_id)
    ready.run_jobs()
    derived = ready.derived_row(derived_id)
    assert derived.state == "Valid" and derived.content_rev == 3
    assert derived.validation_status == "valid" and derived.row_count == 3
    first, second, third = ready.contents(derived_id)
    assert [c.validation_status for c in (first, second, third)] == ["none", "invalid", "valid"]
    assert [c.source_kind for c in (first, second, third)] == ["rendition", "upload", "upload"]
    assert third.schema_version == "1.0.0" and third.warning_count == 0

    # the stored rows are the extractor's result, byte for byte what the ledger hashes
    assert third.result_file_id is not None
    with open_uow(ready.db, readonly=True) as uow:
        stored = ResultFiles(ready.files).read_result(
            uow, BASE["scope"], third.result_file_id, third.result_sha256
        )
    assert isinstance(stored, ExtractionResult) and stored.columns == [
        "tag",
        "service",
        "type",
        "size_in",
    ]
    assert [r["tag"] for r in stored.rows] == [g[0] for g in GOOD]
    assert all(j.state == "succeeded" for j in ready.jobs())


def test_a_job_leaves_the_event_trail_of_an_attempt(ready: World) -> None:
    rev = ready.revision("ISD-001", "A")
    start(ready, revision_id=rev.id, schema_code="instrument-index")
    ready.run_jobs()
    job = ready.jobs()[0]
    events = ready.rows(
        "SELECT event_type, actor FROM events WHERE stream_id = :s ORDER BY stream_version",
        s=job.id,
    )
    assert [e["event_type"] for e in events] == [
        "Record.Created",
        "ProcessingJob.Defined",
        "ProcessingJob.Started",
        "ProcessingJob.Succeeded",
    ]
    assert events[0]["actor"] == "user:u" and events[2]["actor"] == "svc:derivation"
    assert ready.scalar("SELECT COUNT(*) FROM job_queue WHERE state = 'done'") == 1


def test_only_one_job_at_a_time_and_only_in_a_state_that_takes_one(ready: World) -> None:
    rev = ready.revision("ISD-001", "A")
    start(ready, revision_id=rev.id, schema_code="instrument-index")
    derived_id = ready.jobs()[0].derived_id
    with pytest.raises(DerivedStateError, match="Processing"):
        start(ready, derived_id=derived_id)
    with open_uow(ready.db) as uow, pytest.raises(DerivedStateError):
        handle_void_derived_document(
            uow, VoidDerivedDocument(**BASE, stream_id=derived_id, reason="no")
        )


def test_the_source_must_be_something_the_derived_document_may_read(ready: World) -> None:
    rev = ready.revision("ISD-001", "A")
    ready.register("ISD-002")
    ready.create_revision("ISD-002")
    ready.attach("ISD-002", "A")
    other = ready.revision("ISD-002", "A")
    derived = ready.open_derived("ISD-001", "A")
    foreign = ready.rows(
        "SELECT id FROM cur_documents_rendition WHERE revision_id = :r", r=other.id
    )[0]
    with pytest.raises(InvalidSourceError, match="is not a rendition of"):
        start(ready, derived_id=derived.id, rendition_id=foreign["id"])
    with pytest.raises(InvalidSourceError, match="is not in scope"):
        start(ready, derived_id=derived.id, file_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6ZZ")
    with pytest.raises(InvalidSourceError, match="no extractor named"):
        start(ready, derived_id=derived.id, extractor="nope")
    ready.issue("ISD-001", "A", "IFR")
    ready.create_revision("ISD-001")  # revision B: nothing attached
    b = ready.revision("ISD-001", "B")
    with pytest.raises(InvalidSourceError, match="has no file to read"):
        start(ready, revision_id=b.id, schema_code="instrument-index")
    assert rev.id != b.id


def test_no_extractor_accepting_the_file_is_refused_at_the_start(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, b"%PDF", name="x.bin", content_type="text/plain")
    with pytest.raises(InvalidSourceError, match="no extractor accepts"):
        start(ready, derived_id=derived.id)


def test_a_schema_for_other_document_types_is_refused(ready: World) -> None:
    ready.register_schema(code="line-list", doc_types=["LST"])
    rev = ready.revision("ISD-001", "A")
    with pytest.raises(InvalidDocumentSchemaError, match="applies to document types LST"):
        with open_uow(ready.db) as uow:
            handle_open_derived_document(
                uow, OpenDerivedDocument(**BASE, revision_id=rev.id, schema_code="line-list")
            )


def test_a_stuck_extractor_fails_the_job_for_good_and_frees_the_derived_document(
    ready: World,
) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, b"a,b\n1,2\n", name="stuck.slow")
    job_id = start(ready, derived_id=derived.id, extractor="slow", options={"seconds": 30})
    results = ready.run_jobs(timeout_s=2)
    assert [r.outcome for r in results] == ["final"]  # a timeout is not retried
    job = [j for j in ready.jobs() if j.id == job_id][0]
    assert (job.state, job.attempt, job.error_code) == ("failed", 1, "extraction_limit")
    assert job.error_message == ("the extraction used more time or memory than the limit allows")
    after = ready.derived_row(derived.id)
    assert after.state == "Pending" and after.content_rev == 0  # nothing was recorded
    assert ready.scalar("SELECT state FROM job_queue WHERE job_id = :j", j=job_id) == "failed"
    start(ready, derived_id=derived.id)  # and a new job can be queued


@pytest.mark.parametrize(
    ("extractor", "filename", "options"),
    [
        ("slow", "a.slow", {"seconds": 30}),
        ("dying", "a.die", {}),
        ("greedy", "a.greedy", {}),
        ("spin", "a.spin", {}),
        ("oversized", "a.big", {}),
    ],
)
def test_every_breach_of_the_envelope_fails_the_job_for_good_and_the_worker_goes_on(
    ready: World, extractor: str, filename: str, options: dict[str, Any]
) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, b"a,b\n1,2\n", name=filename)
    bad = start(ready, derived_id=derived.id, extractor=extractor, options=options)
    assert [r.outcome for r in ready.run_jobs(timeout_s=2, memory_limit_mb=512)] == ["final"]
    job = [j for j in ready.jobs() if j.id == bad][0]
    wanted = "contract_violation" if extractor == "oversized" else "extraction_limit"
    assert (job.state, job.attempt, job.error_code) == ("failed", 1, wanted)
    assert "Traceback" not in (job.error_message or "") and "/" not in (job.error_message or "")
    after = ready.derived_row(derived.id)
    assert after.state == "Pending" and after.content_rev == 0  # nothing was recorded
    # the same worker process goes on: the next job runs and succeeds
    ready.upload_content(derived.id, index_csv(GOOD), name="good.csv")
    good = start(ready, derived_id=derived.id)
    assert [r.outcome for r in ready.run_jobs(timeout_s=30, memory_limit_mb=512)] == ["done"]
    assert [j for j in ready.jobs() if j.id == good][0].state == "succeeded"
    assert ready.derived_row(derived.id).state == "Valid"


def test_a_file_the_extractor_cannot_read_is_a_pass_with_a_report_not_a_failed_job(
    ready: World,
) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, b"\xff\xfe\x00bad", name="latin.csv")
    start(ready, derived_id=derived.id)
    ready.run_jobs()
    after = ready.derived_row(derived.id)
    assert after.state == "Invalid" and after.content_rev == 1
    report = report_of(ready, 1)
    assert [i.code for i in report.issues if i.level == "error"][:1] == ["not_utf8"]
    assert ready.jobs()[0].state == "succeeded"


def test_a_cancelled_job_is_never_run_and_the_document_goes_back(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, index_csv(GOOD))
    job_id = start(ready, derived_id=derived.id)
    with open_uow(ready.db) as uow:
        handle_cancel_job(uow, CancelJob(**BASE, job_id=job_id, reason="wrong file"))
    assert ready.run_jobs() == []
    assert ready.jobs()[0].state == "cancelled"
    assert ready.derived_row(derived.id).state == "Pending"
    with open_uow(ready.db) as uow, pytest.raises(Exception, match="cancelled"):
        handle_cancel_job(uow, CancelJob(**BASE, job_id=job_id))


def test_stored_rows_can_be_checked_again_against_a_newer_schema(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, index_csv(GOOD))
    start(ready, derived_id=derived.id)
    ready.run_jobs()
    assert ready.derived_row(derived.id).state == "Valid"
    stricter = json.loads(json.dumps(ready_schema()))
    stricter["properties"]["size_in"]["minimum"] = 3
    ready.register_schema(semver="1.1.0", json_schema=stricter)
    with open_uow(ready.db) as uow:
        made = handle_validate_derived(
            uow, ValidateDerived(**BASE, derived_id=derived.id, schema_semver="1.1.0")
        )
    assert ready.derived_row(derived.id).state == "Processing"
    ready.run_jobs()
    after = ready.derived_row(derived.id)
    assert after.state == "Invalid" and after.schema_version == "1.1.0" and after.error_count == 1
    (content,) = ready.contents(derived.id)  # the same pass, judged again
    assert content.content_rev == 1 and content.schema_version == "1.1.0"
    assert ready.jobs()[0].id == made.stream_id and ready.jobs()[0].kind == "validate"


def ready_schema() -> dict[str, Any]:
    from tl_mod_documents.testing import INDEX_SCHEMA

    return INDEX_SCHEMA


def test_validating_needs_stored_rows(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    with open_uow(ready.db) as uow, pytest.raises(InvalidSourceError, match="no stored rows"):
        handle_validate_derived(uow, ValidateDerived(**BASE, derived_id=derived.id))


def test_a_derived_document_can_be_voided_while_nothing_runs(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    with open_uow(ready.db) as uow:
        handle_void_derived_document(
            uow, VoidDerivedDocument(**BASE, stream_id=derived.id, reason="opened by mistake")
        )
    gone = ready.derived_row(derived.id)
    assert gone.state == "Void" and gone.voided
    with pytest.raises(DerivedStateError):
        start(ready, derived_id=derived.id)


def test_a_second_derived_document_follows_the_previous_revision(ready: World) -> None:
    first = ready.open_derived("ISD-001", "A")
    ready.issue("ISD-001", "A", "IFR")
    ready.create_revision("ISD-001")
    ready.attach("ISD-001", "B")
    second = ready.open_derived("ISD-001", "B")
    assert second.key == "ISD-001@B/instrument-index" and second.source_ref == "src.doc.ISD-001@B"
    assert second.previous_derived_id == first.id
    assert first.previous_derived_id is None


def test_opening_twice_gives_the_same_derived_document(ready: World) -> None:
    assert ready.open_derived("ISD-001", "A").id == ready.open_derived("ISD-001", "A").id
    assert len(ready.rows("SELECT id FROM cur_documents_derived_document")) == 1


def test_orphan_jobs_are_queued_again_after_a_restore(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, index_csv(GOOD))
    job_id = start(ready, derived_id=derived.id)
    with open_uow(ready.db) as uow:  # the queue was lost, the ledger was not
        uow.conn().exec_driver_sql("DELETE FROM job_queue")
    with open_uow(ready.db) as uow:
        assert reconcile_orphans(uow.conn()) == 1
    with open_uow(ready.db) as uow:
        assert reconcile_orphans(uow.conn()) == 0
    results = ready.run_jobs()
    assert [(r.job_id, r.outcome) for r in results] == [(job_id, "done")]
    assert ready.derived_row(derived.id).state == "Valid"


def test_a_worker_killed_mid_run_does_not_lose_the_job(ready: World) -> None:
    from datetime import timedelta

    from tl_adapters.queue import job_queue_for
    from tl_core.util import utcnow

    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, index_csv(GOOD))
    job_id = start(ready, derived_id=derived.id)
    with open_uow(ready.db) as uow:  # a worker claims it and dies
        claim = job_queue_for(uow.conn()).claim(uow.conn(), owner="dead", now=utcnow(), lease_s=1)
    assert claim is not None and claim.job_id == job_id

    class Later:
        def __call__(self) -> Any:
            return utcnow() + timedelta(seconds=10)

    results = ready.run_jobs(worker="alive", clock=Later())
    assert [(r.outcome, r.attempt) for r in results] == [("done", 2)]
    assert ready.derived_row(derived.id).state == "Valid"
    assert ready.jobs()[0].attempt == 2
