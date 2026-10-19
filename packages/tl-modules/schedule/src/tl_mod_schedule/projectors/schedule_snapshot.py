"""SnapshotProjector: the ``ScheduleSnapshot.*`` events into ``cur_schedule_schedule_snapshot``.

``Defined`` inserts the snapshot; ``Queued`` fixes its file; ``BuildStarted`` and ``BuildFailed``
count the attempts; ``Built`` and ``Rejected`` record the outcome of the check; ``MadeCurrent``
stamps the publication. The workflow state is the envelope ``status`` (core workflow projector).
Deterministic: the row depends only on the events of the stream. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_schedule.names import (
    BUILD_FAILED,
    BUILD_STARTED,
    SNAPSHOT_BUILT,
    SNAPSHOT_DEFINED,
    SNAPSHOT_MADE_CURRENT,
    SNAPSHOT_QUEUED,
    SNAPSHOT_REJECTED,
    SNAPSHOT_TABLE,
    SNAPSHOT_VIEW,
)
from tl_mod_schedule.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {SNAPSHOT_TABLE} (id, scope, schedule_id, schedule_code, number, "
    "p6_project_option, attempts, last_seq) VALUES (:id, :scope, :schedule_id, :schedule_code, "
    ":number, :p6_project_option, 0, :last_seq)"
)
_QUEUED_SQL = text(
    f"UPDATE {SNAPSHOT_TABLE} SET source_file_id = :source_file_id, source_name = :source_name, "
    "source_sha256 = :source_sha256, source_size = :source_size, requested_by = :requested_by, "
    "last_error = NULL, last_seq = :last_seq WHERE id = :id"
)
_STARTED_SQL = text(
    f"UPDATE {SNAPSHOT_TABLE} SET attempts = :attempt, last_seq = :last_seq WHERE id = :id"
)
_FAILED_SQL = text(
    f"UPDATE {SNAPSHOT_TABLE} SET last_error = :error, last_seq = :last_seq WHERE id = :id"
)
_BUILT_SQL = text(
    f"UPDATE {SNAPSHOT_TABLE} SET data_date = :data_date, p6_version = :p6_version, "
    "p6_project = :p6_project, activity_count = :activities, relationship_count = :relationships, "
    "wbs_count = :wbs, calendar_count = :calendars, code_count = :codes, udf_count = :udfs, "
    "error_count = 0, warning_count = :warnings, report_file_id = :report_file_id, "
    "raw_file_id = :raw_file_id, typed_sha256 = :typed_sha256, raw_sha256 = :raw_sha256, "
    "built_at = :built_at, last_error = NULL, last_seq = :last_seq WHERE id = :id"
)
_REJECTED_SQL = text(
    f"UPDATE {SNAPSHOT_TABLE} SET error_count = :errors, warning_count = :warnings, "
    "report_file_id = :report_file_id, last_error = :code, last_seq = :last_seq WHERE id = :id"
)
_CURRENT_SQL = text(
    f"UPDATE {SNAPSHOT_TABLE} SET published_at = :published_at, last_seq = :last_seq WHERE id = :id"
)


class SnapshotProjector:
    name = "schedule_schedule_snapshot"
    handles = frozenset(
        {
            SNAPSHOT_DEFINED,
            SNAPSHOT_QUEUED,
            BUILD_STARTED,
            BUILD_FAILED,
            SNAPSHOT_BUILT,
            SNAPSHOT_REJECTED,
            SNAPSHOT_MADE_CURRENT,
        }
    )

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(SNAPSHOT_TABLE, dialect) + ddl_for(SNAPSHOT_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        stamp = iso_utc(event.recorded_at)
        if kind == SNAPSHOT_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "schedule_id": payload["schedule_id"],
                    "schedule_code": payload["schedule_code"],
                    "number": int(payload["number"]),
                    "p6_project_option": payload.get("p6_project_option"),
                    "last_seq": event.seq,
                },
            )
        else:
            params: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
            if kind == SNAPSHOT_QUEUED:
                statement = _QUEUED_SQL
                params.update(
                    source_file_id=payload["source_file_id"],
                    source_name=payload["source_name"],
                    source_sha256=payload["source_sha256"],
                    source_size=int(payload["source_size"]),
                    requested_by=payload["requested_by"],
                )
            elif kind == BUILD_STARTED:
                statement = _STARTED_SQL
                params.update(attempt=int(payload["attempt"]))
            elif kind == BUILD_FAILED:
                statement = _FAILED_SQL
                params.update(error=payload["error_code"])
            elif kind == SNAPSHOT_BUILT:
                statement = _BUILT_SQL
                counts: dict[str, int] = payload["counts"]
                params.update(
                    data_date=payload["data_date"],
                    p6_version=payload["p6_version"],
                    p6_project=payload["p6_project"],
                    activities=int(counts.get("activities", 0)),
                    relationships=int(counts.get("relationships", 0)),
                    wbs=int(counts.get("wbs", 0)),
                    calendars=int(counts.get("calendars", 0)),
                    codes=int(counts.get("codes", 0)),
                    udfs=int(counts.get("udfs", 0)),
                    warnings=int(payload["warning_count"]),
                    report_file_id=payload["report_file_id"],
                    raw_file_id=payload["raw_file_id"],
                    typed_sha256=payload["typed_sha256"],
                    raw_sha256=payload["raw_sha256"],
                    built_at=stamp,
                )
            elif kind == SNAPSHOT_REJECTED:
                statement = _REJECTED_SQL
                codes: list[str] = payload["first_codes"]
                params.update(
                    errors=int(payload["error_count"]),
                    warnings=int(payload["warning_count"]),
                    report_file_id=payload["report_file_id"],
                    code=codes[0] if codes else payload["outcome"],
                )
            elif kind == SNAPSHOT_MADE_CURRENT:
                statement = _CURRENT_SQL
                params.update(published_at=stamp)
            else:
                raise ValueError(f"SnapshotProjector cannot apply event type: {kind}")
            if conn.execute(statement, params).rowcount == 0:
                raise LookupError(f"no {SNAPSHOT_TABLE} row for stream {event.stream_id}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {SNAPSHOT_TABLE}"))
