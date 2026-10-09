"""WorkflowProjector: ``Workflow.Transitioned`` into the record row and ``cur_workflow_state``.

Updates ``status``, ``version``, ``last_seq``, ``updated_at``, ``conformance`` and
``effective_schema_hash`` of ``cur_core_record`` (the transition is an event on the record's own
stream), and upserts the record's ``cur_workflow_state`` row (``entered_at`` is the transition's
time). Deterministic: depends only on the event. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc

TRANSITIONED = "Workflow.Transitioned"

_RECORD_SQL = text(
    "UPDATE cur_core_record SET status = :status, version = :version, last_seq = :last_seq, "
    "updated_at = :stamp, conformance = COALESCE(:conformance, conformance), "
    "effective_schema_hash = COALESCE(:hash, effective_schema_hash) WHERE id = :id"
)
_STATE_UPDATE_SQL = text(
    "UPDATE cur_workflow_state SET scope = :scope, workflow = :workflow, "
    "workflow_version = :workflow_version, state = :state, entered_at = :stamp, "
    "transition = :transition, transitioned_by = :actor, last_seq = :last_seq "
    "WHERE record_id = :id"
)
_STATE_INSERT_SQL = text(
    "INSERT INTO cur_workflow_state (record_id, scope, workflow, workflow_version, state, "
    "entered_at, transition, transitioned_by, last_seq) VALUES (:id, :scope, :workflow, "
    ":workflow_version, :state, :stamp, :transition, :actor, :last_seq)"
)


class WorkflowProjector:
    name = "workflow"
    handles = frozenset({TRANSITIONED})

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_workflow_state", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        updated = conn.execute(
            _RECORD_SQL,
            {
                "id": event.stream_id,
                "status": payload["to_state"],
                "version": event.stream_version,
                "last_seq": event.seq,
                "stamp": stamp,
                "conformance": payload.get("conformance"),
                "hash": payload.get("effective_schema_hash"),
            },
        )
        if updated.rowcount == 0:
            raise LookupError(f"no cur_core_record row for stream {event.stream_id}")
        params = {
            "id": event.stream_id,
            "scope": event.scope,
            "workflow": payload["workflow"],
            "workflow_version": payload["workflow_version"],
            "state": payload["to_state"],
            "stamp": stamp,
            "transition": payload["transition"],
            "actor": event.actor,
            "last_seq": event.seq,
        }
        if conn.execute(_STATE_UPDATE_SQL, params).rowcount == 0:
            conn.execute(_STATE_INSERT_SQL, params)

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_workflow_state"))
