"""InspectionProjector: ``Inspection.Planned`` and the events after it.

``Record.Created`` makes the envelope row (``RecordProjector``); ``Inspection.Planned`` follows in
the same append and makes this module's row. The workflow state is the envelope ``status``.
``punch_count`` is set from the ``punch_item_ids`` the result names.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_quality.names import (
    INSPECTION_CANCELLED,
    INSPECTION_EVENTS,
    INSPECTION_PLANNED,
    INSPECTION_RESULT_RECORDED,
    INSPECTION_SCHEDULED,
    INSPECTION_TABLE,
    INSPECTION_VERIFIED,
    INSPECTION_VIEW,
)
from tl_mod_quality.projectors._common import ddl_for, require_row, touch_record
from tl_mod_quality.projectors.checklist import dump_json

_INSERT = text(
    f"INSERT INTO {INSPECTION_TABLE} (id, scope, subject_id, for_iwp_id, point, area, "
    "planned_on, reinspection_of_id, punch_count, last_seq) VALUES (:id, :scope, :subject_id, "
    ":for_iwp_id, :point, :area, :planned_on, :reinspection_of_id, 0, :last_seq)"
)
_SCHEDULE = text(
    f"UPDATE {INSPECTION_TABLE} SET checklist_id = :checklist_id, "
    "checklist_version = :checklist_version, scheduled_for = :scheduled_for, "
    "inspector = :inspector, last_seq = :last_seq WHERE id = :id"
)
_RECORD = text(
    f"UPDATE {INSPECTION_TABLE} SET answers_json = :answers_json, result = :result, "
    "done_at = :done_at, note = :note, recorded_by = :recorded_by, punch_count = :punch_count, "
    "last_seq = :last_seq WHERE id = :id"
)
_VERIFY = text(
    f"UPDATE {INSPECTION_TABLE} SET verified_by = :by, verified_on = :on, last_seq = :last_seq "
    "WHERE id = :id"
)
_CANCEL = text(
    f"UPDATE {INSPECTION_TABLE} SET cancel_reason = :reason, last_seq = :last_seq WHERE id = :id"
)


class InspectionProjector:
    name = "quality_inspection"
    handles = INSPECTION_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(INSPECTION_TABLE, dialect) + ddl_for(INSPECTION_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == INSPECTION_PLANNED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "subject_id": payload.get("subject_id"),
                    "for_iwp_id": payload.get("for_iwp_id"),
                    "point": payload.get("point"),
                    "area": payload.get("area"),
                    "planned_on": payload.get("planned_on"),
                    "reinspection_of_id": payload.get("reinspection_of_id"),
                    "last_seq": event.seq,
                },
            )
        else:
            done = self._update(conn, event, kind, payload)
            require_row(done, INSPECTION_TABLE, event)
        touch_record(conn, event)

    @staticmethod
    def _update(conn: Connection, event: Event, kind: str, payload: dict[str, Any]) -> int:
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        if kind == INSPECTION_SCHEDULED:
            params: dict[str, Any] = {
                "checklist_id": payload["checklist_id"],
                "checklist_version": payload["checklist_version"],
                "scheduled_for": payload["scheduled_for"],
                "inspector": payload["inspector"],
            }
            return conn.execute(_SCHEDULE, {**base, **params}).rowcount
        if kind == INSPECTION_RESULT_RECORDED:
            params = {
                "answers_json": dump_json(payload.get("answers") or []),
                "result": payload["result"],
                "done_at": payload["done_at"],
                "note": payload.get("note"),
                "recorded_by": event.actor,
                "punch_count": len(payload.get("punch_item_ids") or []),
            }
            return conn.execute(_RECORD, {**base, **params}).rowcount
        if kind == INSPECTION_VERIFIED:
            params = {"by": event.actor, "on": payload["verified_on"]}
            return conn.execute(_VERIFY, {**base, **params}).rowcount
        if kind == INSPECTION_CANCELLED:
            return conn.execute(_CANCEL, {**base, "reason": payload["reason"]}).rowcount
        raise ValueError(f"InspectionProjector cannot apply event type: {kind}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {INSPECTION_TABLE}"))
