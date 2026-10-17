"""ProcessingJobProjector: the ``ProcessingJob.*`` events into ``cur_documents_processing_job``.

``Defined`` inserts the job as queued; ``Started`` records the claim (attempt, worker, time);
``Succeeded`` ends it; ``Failed`` ends it for good when ``final`` is set and otherwise puts it back
to queued; ``Cancelled`` ends a queued job. The claim queue itself (``job_queue``) is operational
and is not touched here. Deterministic. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_documents.names import (
    JOB_CANCELLED,
    JOB_CANCELLED_STATE,
    JOB_DEFINED,
    JOB_FAILED,
    JOB_FAILED_STATE,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_STARTED,
    JOB_SUCCEEDED,
    JOB_SUCCEEDED_STATE,
    PROCESSING_JOB_TABLE,
    PROCESSING_JOB_VIEW,
)
from tl_mod_documents.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {PROCESSING_JOB_TABLE} (id, scope, kind, derived_id, derived_key, source_ref, "
    "source_file_id, extractor, options_json, schema_id, requested_by, state, attempt, "
    "max_attempts, created_seq, last_seq) VALUES (:id, :scope, :kind, :derived_id, :derived_key, "
    ":source_ref, :source_file_id, :extractor, :options_json, :schema_id, :requested_by, :state, "
    "0, :max_attempts, :last_seq, :last_seq)"
)
_STARTED_SQL = text(
    f"UPDATE {PROCESSING_JOB_TABLE} SET state = :state, attempt = :attempt, worker = :worker, "
    "started_at = :at, finished_at = NULL, last_seq = :last_seq WHERE id = :id"
)
_SUCCEEDED_SQL = text(
    f"UPDATE {PROCESSING_JOB_TABLE} SET state = :state, finished_at = :at, result_json = :result, "
    "error_code = NULL, error_message = NULL, last_seq = :last_seq WHERE id = :id"
)
_FAILED_SQL = text(
    f"UPDATE {PROCESSING_JOB_TABLE} SET state = :state, finished_at = :finished, "
    "error_code = :code, error_message = :message, last_seq = :last_seq WHERE id = :id"
)
_CANCELLED_SQL = text(
    f"UPDATE {PROCESSING_JOB_TABLE} SET state = :state, finished_at = :at, last_seq = :last_seq "
    "WHERE id = :id"
)


class ProcessingJobProjector:
    name = "documents_processing_job"
    handles = frozenset({JOB_DEFINED, JOB_STARTED, JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELLED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(PROCESSING_JOB_TABLE, dialect) + ddl_for(PROCESSING_JOB_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        at = iso_utc(event.recorded_at)
        found = 1
        if event.event_type == JOB_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "kind": payload["kind"],
                    "derived_id": payload["derived_id"],
                    "derived_key": payload["derived_key"],
                    "source_ref": payload["source_ref"],
                    "source_file_id": payload.get("source_file_id"),
                    "extractor": payload.get("extractor"),
                    "options_json": json_text(payload.get("options") or {}),
                    "schema_id": payload["schema_id"],
                    "requested_by": payload["requested_by"],
                    "state": JOB_QUEUED,
                    "max_attempts": int(payload["max_attempts"]),
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == JOB_STARTED:
            found = conn.execute(
                _STARTED_SQL,
                {
                    "id": event.stream_id,
                    "state": JOB_RUNNING,
                    "attempt": int(payload["attempt"]),
                    "worker": payload["worker"],
                    "at": at,
                    "last_seq": event.seq,
                },
            ).rowcount
        elif event.event_type == JOB_SUCCEEDED:
            result = payload.get("result")
            found = conn.execute(
                _SUCCEEDED_SQL,
                {
                    "id": event.stream_id,
                    "state": JOB_SUCCEEDED_STATE,
                    "at": at,
                    "result": None if result is None else json_text(result),
                    "last_seq": event.seq,
                },
            ).rowcount
        elif event.event_type == JOB_FAILED:
            final = bool(payload["final"])
            found = conn.execute(
                _FAILED_SQL,
                {
                    "id": event.stream_id,
                    "state": JOB_FAILED_STATE if final else JOB_QUEUED,
                    "finished": at if final else None,
                    "code": payload["error_code"],
                    "message": payload["error_message"],
                    "last_seq": event.seq,
                },
            ).rowcount
        elif event.event_type == JOB_CANCELLED:
            found = conn.execute(
                _CANCELLED_SQL,
                {
                    "id": event.stream_id,
                    "state": JOB_CANCELLED_STATE,
                    "at": at,
                    "last_seq": event.seq,
                },
            ).rowcount
        else:
            raise ValueError(f"ProcessingJobProjector cannot apply event type: {event.event_type}")
        if found == 0:
            raise LookupError(f"no {PROCESSING_JOB_TABLE} row for stream {event.stream_id}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {PROCESSING_JOB_TABLE}"))
