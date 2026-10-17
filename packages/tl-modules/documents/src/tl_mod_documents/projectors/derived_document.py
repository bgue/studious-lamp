"""DerivedDocumentProjector: the ``DerivedDocument.*`` events into two tables.

``DerivedDocument.Defined`` inserts the derived document; ``ContentRecorded`` adds a row to
``cur_documents_derived_content`` (one per extractor pass) and moves the derived document to that
content revision; ``Validated`` completes the content row and, when it is the latest revision, the
derived document's validation columns; ``Published`` and ``PublicationCompensated`` set and clear
the publication in force. The workflow state is the envelope ``status`` (core workflow projector).
Deterministic: the rows depend only on the events of the stream. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_documents.names import (
    DERIVED_COMPENSATED,
    DERIVED_CONTENT_RECORDED,
    DERIVED_CONTENT_TABLE,
    DERIVED_DEFINED,
    DERIVED_DOCUMENT_TABLE,
    DERIVED_DOCUMENT_VIEW,
    DERIVED_PUBLISHED,
    DERIVED_VALIDATED,
)
from tl_mod_documents.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {DERIVED_DOCUMENT_TABLE} (id, scope, source_document_id, source_revision_id, "
    "source_document_number, source_revision_code, source_ref, schema_id, schema_code, "
    "schema_version, method, previous_derived_id, last_seq) VALUES (:id, :scope, "
    ":source_document_id, :source_revision_id, :source_document_number, :source_revision_code, "
    ":source_ref, :schema_id, :schema_code, :schema_version, :method, :previous_derived_id, "
    ":last_seq)"
)
_CONTENT_INSERT_SQL = text(
    f"INSERT INTO {DERIVED_CONTENT_TABLE} (content_id, scope, derived_id, content_rev, job_id, "
    "source_kind, source_file_id, extractor, extractor_version, extraction_status, "
    "result_file_id, result_sha256, row_count, column_count, problem_count, file_metadata_json, "
    "extractor_notes_json, created_at, last_seq) VALUES (:content_id, :scope, :derived_id, "
    ":content_rev, :job_id, :source_kind, :source_file_id, :extractor, :extractor_version, "
    ":extraction_status, :result_file_id, :result_sha256, :row_count, :column_count, "
    ":problem_count, :file_metadata_json, :extractor_notes_json, :created_at, :last_seq)"
)
_CONTENT_DOCUMENT_SQL = text(
    f"UPDATE {DERIVED_DOCUMENT_TABLE} SET content_rev = :content_rev, method = :method, "
    "validation_status = 'none', error_count = NULL, row_count = :row_count, "
    "last_job_id = COALESCE(:job_id, last_job_id), last_seq = :last_seq WHERE id = :id"
)
_VALIDATED_CONTENT_SQL = text(
    f"UPDATE {DERIVED_CONTENT_TABLE} SET schema_id = :schema_id, schema_version = :schema_version, "
    "validation_status = :status, error_count = :errors, warning_count = :warnings, "
    "report_file_id = :report_file_id, report_sha256 = :report_sha256, last_seq = :last_seq "
    "WHERE derived_id = :id AND content_rev = :content_rev"
)
_VALIDATED_DOCUMENT_SQL = text(
    f"UPDATE {DERIVED_DOCUMENT_TABLE} SET schema_id = :schema_id, schema_code = :schema_code, "
    "schema_version = :schema_version, validation_status = :status, error_count = :errors, "
    "last_seq = :last_seq WHERE id = :id AND content_rev = :content_rev"
)
_BUMP_SQL = text(f"UPDATE {DERIVED_DOCUMENT_TABLE} SET last_seq = :last_seq WHERE id = :id")
_PUBLISHED_DOCUMENT_SQL = text(
    f"UPDATE {DERIVED_DOCUMENT_TABLE} SET published_rev = :content_rev, "
    "published_correlation_id = :correlation, published_at = :at, published_count = :count, "
    "last_seq = :last_seq WHERE id = :id"
)
_COMPENSATED_DOCUMENT_SQL = text(
    f"UPDATE {DERIVED_DOCUMENT_TABLE} SET published_rev = NULL, published_correlation_id = NULL, "
    "published_at = NULL, published_count = NULL, last_seq = :last_seq WHERE id = :id"
)
_PUBLISHED_CONTENT_SQL = text(
    f"UPDATE {DERIVED_CONTENT_TABLE} SET published = :published, last_seq = :last_seq "
    "WHERE derived_id = :id AND content_rev = :content_rev"
)


def content_id(derived_id: str, content_rev: int) -> str:
    """``<derived id>:<revision, four digits>``, the key of a content row."""
    return f"{derived_id}:{content_rev:04d}"


def _optional_json(value: Any) -> str | None:
    return None if value is None else json_text(value)


class DerivedDocumentProjector:
    name = "documents_derived_document"
    handles = frozenset(
        {
            DERIVED_DEFINED,
            DERIVED_CONTENT_RECORDED,
            DERIVED_VALIDATED,
            DERIVED_PUBLISHED,
            DERIVED_COMPENSATED,
        }
    )

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(DERIVED_DOCUMENT_TABLE, dialect)
            + ddl_for(DERIVED_CONTENT_TABLE, dialect)
            + ddl_for(DERIVED_DOCUMENT_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == DERIVED_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "source_document_id": payload["source_document_id"],
                    "source_revision_id": payload["source_revision_id"],
                    "source_document_number": payload["source_document_number"],
                    "source_revision_code": payload["source_revision_code"],
                    "source_ref": payload["source_ref"],
                    "schema_id": payload["schema_id"],
                    "schema_code": payload["schema_code"],
                    "schema_version": payload["schema_version"],
                    "method": payload["method"],
                    "previous_derived_id": payload.get("previous_derived_id"),
                    "last_seq": event.seq,
                },
            )
        elif kind == DERIVED_CONTENT_RECORDED:
            self._content_recorded(conn, event, payload)
        elif kind == DERIVED_VALIDATED:
            self._validated(conn, event, payload)
        elif kind == DERIVED_PUBLISHED:
            rev = int(payload["content_rev"])
            self._require(
                conn.execute(
                    _PUBLISHED_DOCUMENT_SQL,
                    {
                        "id": event.stream_id,
                        "content_rev": rev,
                        "correlation": payload["import_correlation_id"],
                        "at": iso_utc(event.recorded_at),
                        "count": int(payload["created_count"]),
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
            conn.execute(
                _PUBLISHED_CONTENT_SQL,
                {
                    "id": event.stream_id,
                    "content_rev": rev,
                    "published": True,
                    "last_seq": event.seq,
                },
            )
        elif kind == DERIVED_COMPENSATED:
            self._require(
                conn.execute(
                    _COMPENSATED_DOCUMENT_SQL, {"id": event.stream_id, "last_seq": event.seq}
                ).rowcount,
                event,
            )
            conn.execute(
                _PUBLISHED_CONTENT_SQL,
                {
                    "id": event.stream_id,
                    "content_rev": int(payload["content_rev"]),
                    "published": False,
                    "last_seq": event.seq,
                },
            )
        else:
            raise ValueError(f"DerivedDocumentProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def _content_recorded(self, conn: Connection, event: Event, payload: dict[str, Any]) -> None:
        rev = int(payload["content_rev"])
        conn.execute(
            _CONTENT_INSERT_SQL,
            {
                "content_id": content_id(event.stream_id, rev),
                "scope": event.scope,
                "derived_id": event.stream_id,
                "content_rev": rev,
                "job_id": payload.get("job_id"),
                "source_kind": payload["source_kind"],
                "source_file_id": payload["source_file_id"],
                "extractor": payload["extractor"],
                "extractor_version": payload["extractor_version"],
                "extraction_status": payload["extraction_status"],
                "result_file_id": payload.get("result_file_id"),
                "result_sha256": payload.get("result_sha256"),
                "row_count": int(payload["row_count"]),
                "column_count": int(payload["column_count"]),
                "problem_count": int(payload["problem_count"]),
                "file_metadata_json": _optional_json(payload.get("file_metadata")),
                "extractor_notes_json": _optional_json(payload.get("extractor_notes")),
                "created_at": iso_utc(event.recorded_at),
                "last_seq": event.seq,
            },
        )
        self._require(
            conn.execute(
                _CONTENT_DOCUMENT_SQL,
                {
                    "id": event.stream_id,
                    "content_rev": rev,
                    "method": payload["method"],
                    "row_count": int(payload["row_count"]),
                    "job_id": payload.get("job_id"),
                    "last_seq": event.seq,
                },
            ).rowcount,
            event,
        )

    def _validated(self, conn: Connection, event: Event, payload: dict[str, Any]) -> None:
        params = {
            "id": event.stream_id,
            "content_rev": int(payload["content_rev"]),
            "schema_id": payload["schema_id"],
            "schema_code": payload["schema_code"],
            "schema_version": payload["schema_version"],
            "status": payload["validation_status"],
            "errors": int(payload["error_count"]),
            "warnings": int(payload["warning_count"]),
            "report_file_id": payload.get("report_file_id"),
            "report_sha256": payload.get("report_sha256"),
            "last_seq": event.seq,
        }
        self._require(conn.execute(_VALIDATED_CONTENT_SQL, params).rowcount, event)
        # The derived document shows the latest content revision; an older one leaves it alone.
        if conn.execute(_VALIDATED_DOCUMENT_SQL, params).rowcount == 0:
            conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {DERIVED_DOCUMENT_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {DERIVED_CONTENT_TABLE}"))
        conn.execute(text(f"DELETE FROM {DERIVED_DOCUMENT_TABLE}"))
