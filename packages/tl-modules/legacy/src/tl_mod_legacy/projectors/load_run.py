"""LoadRunProjector: the load run events into ``cur_legacy_load_run``. Deterministic."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_legacy.names import (
    RUN_BRONZED,
    RUN_COMPENSATED,
    RUN_EXTRACTED,
    RUN_FAILED,
    RUN_LOADED,
    RUN_OPENED,
    RUN_PLANNED,
    RUN_PROFILED,
    RUN_RECONCILED,
    RUN_TABLE,
    RUN_VIEW,
    RUN_VOIDED,
)
from tl_mod_legacy.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {RUN_TABLE} (id, scope, source_system, source_table, run_number, loader, "
    "source_name, source_sha256, source_size, opened_by, last_seq) VALUES (:id, :scope, "
    ":source_system, :source_table, :run_number, :loader, :source_name, :source_sha256, "
    ":source_size, :opened_by, :last_seq)"
)


def _update(assignments: str) -> Any:
    return text(f"UPDATE {RUN_TABLE} SET {assignments}, last_seq = :last_seq WHERE id = :id")


#: event type to (statement, column to payload field); a payload field of ``None`` binds NULL.
_STATEMENTS: dict[str, tuple[Any, dict[str, str | None]]] = {
    RUN_EXTRACTED: (
        _update(
            "row_count = :row_count, column_count = :column_count, "
            "extracted_file_id = :extracted_file_id, extracted_sha256 = :extracted_sha256, "
            "last_error = NULL"
        ),
        {
            "row_count": "row_count",
            "column_count": "column_count",
            "extracted_file_id": "extracted_file_id",
            "extracted_sha256": "extracted_sha256",
        },
    ),
    RUN_PROFILED: (
        _update(
            "profile_file_id = :profile_file_id, profile_sha256 = :profile_sha256, "
            "last_error = NULL"
        ),
        {"profile_file_id": "profile_file_id", "profile_sha256": "profile_sha256"},
    ),
    RUN_BRONZED: (
        _update("bronze_rows = :bronze_rows, last_error = NULL"),
        {"bronze_rows": "bronze_rows"},
    ),
    RUN_PLANNED: (
        _update(
            "mapping_name = :mapping_name, mapping_sha256 = :mapping_sha256, "
            "plan_new = :plan_new, plan_existing = :plan_existing, plan_invalid = :plan_invalid, "
            "last_error = NULL"
        ),
        {
            "mapping_name": "mapping_name",
            "mapping_sha256": "mapping_sha256",
            "plan_new": "plan_new",
            "plan_existing": "plan_existing",
            "plan_invalid": "plan_invalid",
        },
    ),
    RUN_RECONCILED: (
        _update(
            "report_file_id = :report_file_id, report_sha256 = :report_sha256, "
            "report_document_id = :report_document_id, mismatches = :mismatches, last_error = NULL"
        ),
        {
            "report_file_id": "report_file_id",
            "report_sha256": "report_sha256",
            "report_document_id": "report_document_id",
            "mismatches": "mismatches",
        },
    ),
    RUN_FAILED: (
        _update("last_error = :last_error"),
        {"last_error": "message"},
    ),
    RUN_COMPENSATED: (_update("last_error = NULL"), {}),
    RUN_VOIDED: (_update("last_error = NULL"), {}),
}
HANDLED = frozenset({RUN_OPENED, RUN_LOADED, *_STATEMENTS})


class LoadRunProjector:
    name = "legacy_load_run"
    handles = HANDLED

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(RUN_TABLE, dialect) + ddl_for(RUN_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        kind = event.event_type
        if kind not in HANDLED:
            raise ValueError(f"LoadRunProjector cannot apply event type: {kind}")
        payload: dict[str, Any] = event.payload
        if kind == RUN_OPENED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "source_system": payload["source_system"],
                    "source_table": payload["source_table"],
                    "run_number": int(payload["run_number"]),
                    "loader": payload["loader"],
                    "source_name": payload.get("source_name"),
                    "source_sha256": payload.get("source_sha256"),
                    "source_size": payload.get("source_size"),
                    "opened_by": payload["opened_by"],
                    "last_seq": event.seq,
                },
            )
        elif kind == RUN_LOADED:
            conn.execute(
                _update(
                    "loaded_count = :loaded_count, record_ids = :record_ids, "
                    "correlation_id = :correlation_id, last_error = NULL"
                ),
                {
                    "id": event.stream_id,
                    "last_seq": event.seq,
                    "loaded_count": int(payload["loaded_count"]),
                    "record_ids": json_text(list(payload["record_ids"])),
                    "correlation_id": payload["correlation_id"],
                },
            )
        else:
            statement, binds = _STATEMENTS[kind]
            params: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
            for column, field in binds.items():
                params[column] = payload.get(field) if field is not None else None
            conn.execute(statement, params)
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {RUN_TABLE}"))
