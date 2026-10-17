"""The derivation projectors: document schemas, derived documents with content revisions, jobs.

Each event type into its table, a second database replayed to the same rows, and the envelope row
following every event (P1-I3 T01).
"""

from __future__ import annotations

from typing import Any

import pytest
from docworld import Events, apply, as_json, install, table_rows
from sqlalchemy import Engine, text
from tl_core.projection.defaults import default_registry

SCH = "S1"
DD = "DD1"
JOB = "J1"
DOC = "D1"
REV = "R1"


def journal(events: Events) -> list[Any]:
    """A schema, a derived document with two passes (the second valid), a publication and its
    compensation, and a job with a failed first attempt."""
    out = [
        events.created(SCH, "documents.DocumentSchema", "instrument-index@1.0.0", title="Index"),
        events.make(
            "DocumentSchema.Defined",
            {
                "code": "instrument-index",
                "semver": "1.0.0",
                "ordinal": 1,
                "target_kind": "tags",
                "key_column": "tag",
                "json_schema": {"type": "object", "properties": {"tag": {"type": "string"}}},
                "sample": [{"tag": "47-FV-1001"}],
                "mapping": None,
                "doc_types": ["IDX"],
                "content_hash": "ab" * 32,
            },
            stream_id=SCH,
            stream_type="documents.DocumentSchema",
            scope="company",
        ),
        events.created(DD, "documents.DerivedDocument", "ISD-001@A/instrument-index"),
        events.make(
            "DerivedDocument.Defined",
            {
                "source_document_id": DOC,
                "source_revision_id": REV,
                "source_document_number": "ISD-001",
                "source_revision_code": "A",
                "source_ref": "src.doc.ISD-001@A",
                "schema_id": SCH,
                "schema_code": "instrument-index",
                "schema_version": "1.0.0",
                "method": "automated",
                "previous_derived_id": None,
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
        events.created(JOB, "documents.ProcessingJob", "JOB-J1"),
        events.make(
            "ProcessingJob.Defined",
            {
                "kind": "extract",
                "derived_id": DD,
                "derived_key": "ISD-001@A/instrument-index",
                "source_ref": "src.doc.ISD-001@A",
                "source_file_id": "F1",
                "extractor": None,
                "options": {"sheet": "Index"},
                "schema_id": SCH,
                "requested_by": "user:demo",
                "max_attempts": 3,
            },
            stream_id=JOB,
            stream_type="documents.ProcessingJob",
        ),
        events.make(
            "ProcessingJob.Started",
            {"attempt": 1, "worker": "w1", "lease_until": "2026-10-17T10:05:00.000000Z"},
            stream_id=JOB,
            stream_type="documents.ProcessingJob",
        ),
        events.make(
            "ProcessingJob.Failed",
            {
                "attempt": 1,
                "error_code": "source_not_available",
                "error_message": "in quarantine",
                "final": False,
                "retry_at": "2026-10-17T10:01:00.000000Z",
            },
            stream_id=JOB,
            stream_type="documents.ProcessingJob",
        ),
        events.make(
            "ProcessingJob.Started",
            {"attempt": 2, "worker": "w2", "lease_until": "2026-10-17T10:09:00.000000Z"},
            stream_id=JOB,
            stream_type="documents.ProcessingJob",
        ),
        events.make(
            "DerivedDocument.ContentRecorded",
            {
                "content_rev": 1,
                "job_id": JOB,
                "source_kind": "upload",
                "source_file_id": "F1",
                "extractor": "tabular",
                "extractor_version": "1",
                "extraction_status": "ok",
                "result_file_id": "X1",
                "result_sha256": "cd" * 32,
                "row_count": 40,
                "column_count": 5,
                "problem_count": 0,
                "file_metadata": {"sha256": "ef" * 32, "size": 900},
                "extractor_notes": [],
                "method": "hybrid",
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
        events.make(
            "DerivedDocument.Validated",
            {
                "content_rev": 1,
                "schema_id": SCH,
                "schema_code": "instrument-index",
                "schema_version": "1.0.0",
                "validation_status": "invalid",
                "error_count": 1,
                "warning_count": 0,
                "report_file_id": "RP1",
                "report_sha256": "01" * 32,
                "job_id": JOB,
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
        events.make(
            "ProcessingJob.Succeeded",
            {"attempt": 2, "result": {"content_rev": 1, "validation_status": "invalid"}},
            stream_id=JOB,
            stream_type="documents.ProcessingJob",
        ),
        events.make(
            "DerivedDocument.ContentRecorded",
            {
                "content_rev": 2,
                "job_id": None,
                "source_kind": "upload",
                "source_file_id": "F2",
                "extractor": "tabular",
                "extractor_version": "1",
                "extraction_status": "ok",
                "result_file_id": "X2",
                "result_sha256": "ce" * 32,
                "row_count": 40,
                "column_count": 5,
                "problem_count": 0,
                "extractor_notes": [],
                "method": "hybrid",
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
        events.make(
            "DerivedDocument.Validated",
            {
                "content_rev": 2,
                "schema_id": SCH,
                "schema_code": "instrument-index",
                "schema_version": "1.0.0",
                "validation_status": "valid",
                "error_count": 0,
                "warning_count": 2,
                "report_file_id": "RP2",
                "report_sha256": "02" * 32,
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
        events.make(
            "DerivedDocument.Published",
            {
                "content_rev": 2,
                "import_correlation_id": "IMP1",
                "target_kind": "tags",
                "created_count": 40,
                "mapping_hash": "03" * 32,
                "result_sha256": "ce" * 32,
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
    ]
    return out


COMPENSATION = (
    "DerivedDocument.PublicationCompensated",
    {
        "content_rev": 2,
        "import_correlation_id": "IMP1",
        "compensation_correlation_id": "CMP1",
        "reversed_count": 40,
        "reason": "wrong revision",
    },
)

TABLES = {
    "cur_documents_document_schema": "id",
    "cur_documents_derived_document": "id",
    "cur_documents_derived_content": "content_id",
    "cur_documents_processing_job": "id",
}


def snapshot(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    return {t: table_rows(engine, t, order) for t, order in TABLES.items()}


def test_the_journal_projects_and_a_second_database_gets_the_same_rows(
    engine: Engine, new_engine: Any, dialect: str
) -> None:
    events = journal(Events())
    apply(engine, *events)
    first = snapshot(engine)
    other = new_engine()
    install(other, dialect)
    apply(other, *events)
    assert snapshot(other) == first
    other.dispose()


def test_a_schema_version_keeps_its_json_and_is_active_until_retired(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events))
    (row,) = table_rows(engine, "cur_documents_document_schema")
    assert row["code"] == "instrument-index" and row["semver"] == "1.0.0" and row["ordinal"] == 1
    assert row["scope"] == "company" and row["target_kind"] == "tags"
    assert as_json(row["json_schema_json"])["properties"] == {"tag": {"type": "string"}}
    assert as_json(row["sample_json"]) == [{"tag": "47-FV-1001"}]
    assert row["mapping_json"] is None and as_json(row["doc_types_json"]) == ["IDX"]
    assert bool(row["is_active"]) is True
    apply(
        engine,
        events.make(
            "DocumentSchema.Retired",
            {"reason": "Replaced by 1.1.0"},
            stream_id=SCH,
            stream_type="documents.DocumentSchema",
            scope="company",
        ),
    )
    (row,) = table_rows(engine, "cur_documents_document_schema")
    assert bool(row["is_active"]) is False and row["retired_reason"] == "Replaced by 1.1.0"


def test_each_pass_is_a_content_row_and_the_document_follows_the_latest(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    (doc,) = table_rows(engine, "cur_documents_derived_document")
    assert doc["content_rev"] == 2 and doc["validation_status"] == "valid"
    assert doc["error_count"] == 0 and doc["row_count"] == 40 and doc["method"] == "hybrid"
    assert doc["schema_code"] == "instrument-index" and doc["source_ref"] == "src.doc.ISD-001@A"
    assert doc["last_job_id"] == JOB  # the second pass carried none and kept the first
    first, second = table_rows(engine, "cur_documents_derived_content", "content_rev")
    assert first["content_id"] == f"{DD}:0001" and second["content_id"] == f"{DD}:0002"
    assert first["validation_status"] == "invalid" and first["error_count"] == 1
    assert first["report_file_id"] == "RP1" and first["job_id"] == JOB
    assert as_json(first["file_metadata_json"]) == {"sha256": "ef" * 32, "size": 900}
    assert second["validation_status"] == "valid" and second["warning_count"] == 2
    assert second["file_metadata_json"] is None and as_json(second["extractor_notes_json"]) == []


def test_validating_an_older_revision_leaves_the_document_on_the_latest(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events))
    apply(
        engine,
        events.make(
            "DerivedDocument.Validated",
            {
                "content_rev": 1,
                "schema_id": SCH,
                "schema_code": "instrument-index",
                "schema_version": "1.1.0",
                "validation_status": "valid",
                "error_count": 0,
                "warning_count": 0,
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
    )
    (doc,) = table_rows(engine, "cur_documents_derived_document")
    assert doc["schema_version"] == "1.0.0" and doc["validation_status"] == "valid"
    first, _ = table_rows(engine, "cur_documents_derived_content", "content_rev")
    assert first["validation_status"] == "valid" and first["schema_version"] == "1.1.0"


def test_a_new_content_revision_resets_the_validation_of_the_document(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events)[:11])  # up to the first Validated
    (doc,) = table_rows(engine, "cur_documents_derived_document")
    assert doc["validation_status"] == "invalid" and doc["error_count"] == 1
    apply(
        engine,
        events.make(
            "DerivedDocument.ContentRecorded",
            {
                "content_rev": 2,
                "source_kind": "upload",
                "source_file_id": "F2",
                "extractor": "tabular",
                "extractor_version": "1",
                "extraction_status": "ok",
                "row_count": 3,
                "column_count": 2,
                "problem_count": 0,
                "method": "manual",
            },
            stream_id=DD,
            stream_type="documents.DerivedDocument",
        ),
    )
    (doc,) = table_rows(engine, "cur_documents_derived_document")
    assert doc["validation_status"] == "none" and doc["error_count"] is None
    assert doc["row_count"] == 3 and doc["method"] == "manual"


def test_a_publication_is_in_force_until_it_is_compensated(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events))
    (doc,) = table_rows(engine, "cur_documents_derived_document")
    assert doc["published_rev"] == 2 and doc["published_correlation_id"] == "IMP1"
    assert doc["published_count"] == 40 and doc["published_at"] is not None
    first, second = table_rows(engine, "cur_documents_derived_content", "content_rev")
    assert not first["published"] and bool(second["published"])
    apply(
        engine,
        events.make(
            COMPENSATION[0], COMPENSATION[1], stream_id=DD, stream_type="documents.DerivedDocument"
        ),
    )
    (doc,) = table_rows(engine, "cur_documents_derived_document")
    assert doc["published_rev"] is None and doc["published_correlation_id"] is None
    assert doc["published_count"] is None and doc["published_at"] is None
    assert doc["content_rev"] == 2
    _, second = table_rows(engine, "cur_documents_derived_content", "content_rev")
    assert not second["published"]


def test_a_job_walks_queued_running_queued_running_succeeded(engine: Engine) -> None:
    events = Events()
    prefix = journal(events)
    apply(engine, *prefix[:6])  # schema, derived document, job defined
    (job,) = table_rows(engine, "cur_documents_processing_job")
    assert job["state"] == "queued" and job["attempt"] == 0 and job["max_attempts"] == 3
    assert job["requested_by"] == "user:demo" and as_json(job["options_json"]) == {"sheet": "Index"}
    apply(engine, prefix[6])  # Started attempt 1
    (job,) = table_rows(engine, "cur_documents_processing_job")
    assert job["state"] == "running" and job["attempt"] == 1 and job["worker"] == "w1"
    apply(engine, prefix[7])  # Failed, not final
    (job,) = table_rows(engine, "cur_documents_processing_job")
    assert job["state"] == "queued" and job["error_code"] == "source_not_available"
    assert job["finished_at"] is None
    apply(engine, prefix[8])  # Started attempt 2
    (job,) = table_rows(engine, "cur_documents_processing_job")
    assert job["state"] == "running" and job["attempt"] == 2 and job["worker"] == "w2"
    apply(engine, *prefix[9:12])  # content, validated, succeeded
    (job,) = table_rows(engine, "cur_documents_processing_job")
    assert job["state"] == "succeeded" and job["error_code"] is None
    assert job["finished_at"] is not None
    assert as_json(job["result_json"])["validation_status"] == "invalid"


def test_a_final_failure_ends_the_job(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events)[:6])
    apply(
        engine,
        events.make(
            "ProcessingJob.Failed",
            {
                "attempt": 3,
                "error_code": "lease_expired",
                "error_message": "no attempt left",
                "final": True,
            },
            stream_id=JOB,
            stream_type="documents.ProcessingJob",
        ),
    )
    (job,) = table_rows(engine, "cur_documents_processing_job")
    assert job["state"] == "failed" and job["finished_at"] is not None
    assert job["error_code"] == "lease_expired"


def test_a_cancelled_job_is_ended(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events)[:6])
    apply(
        engine,
        events.make(
            "ProcessingJob.Cancelled",
            {"reason": "wrong file"},
            stream_id=JOB,
            stream_type="documents.ProcessingJob",
        ),
    )
    (job,) = table_rows(engine, "cur_documents_processing_job")
    assert job["state"] == "cancelled" and job["finished_at"] is not None


def test_every_event_moves_the_envelope_row(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events))
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT version, last_seq FROM cur_core_record WHERE id = :i"), {"i": DD}
        ).one()
    assert row.version == events.versions[DD] and row.last_seq > 0


def test_the_flat_views_join_the_envelope_to_the_typed_columns(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    with engine.connect() as conn:
        schema = conn.execute(
            text("SELECT key, title, record_type, code, semver FROM v_documents_document_schema")
        ).one()
        derived = conn.execute(
            text(
                "SELECT key, record_type, source_ref, content_rev, validation_status "
                "FROM v_documents_derived_document"
            )
        ).one()
        job = conn.execute(
            text("SELECT key, record_type, kind, state FROM v_documents_processing_job")
        ).one()
    assert tuple(schema) == (
        "instrument-index@1.0.0",
        "Index",
        "documents.DocumentSchema",
        "instrument-index",
        "1.0.0",
    )
    assert tuple(derived) == (
        "ISD-001@A/instrument-index",
        "documents.DerivedDocument",
        "src.doc.ISD-001@A",
        2,
        "valid",
    )
    assert tuple(job) == ("JOB-J1", "documents.ProcessingJob", "extract", "succeeded")


def test_reset_empties_the_derivation_tables_but_not_the_queue(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job_queue (job_id, kind, scope, state, run_after, enqueued_at) "
                "VALUES ('J1', 'extract', 'project:P123', 'queued', 'a', 'a')"
            )
        )
        for projector in default_registry().all():
            if projector.name.startswith("documents_") or projector.name == "job_queue_state":
                projector.reset(conn)
    assert all(not rows for rows in snapshot(engine).values())
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM job_queue")).scalar_one() == 1


def test_an_event_without_its_record_is_an_error_not_a_silent_gap(engine: Engine) -> None:
    events = Events()
    stray = events.make(
        "ProcessingJob.Started",
        {"attempt": 1, "worker": "w", "lease_until": "2026-10-17T10:05:00.000000Z"},
        stream_id="NOPE",
        stream_type="documents.ProcessingJob",
    )
    with pytest.raises(LookupError):
        apply(engine, stray)
