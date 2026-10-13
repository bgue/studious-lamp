"""ReviewCycleProjector: the ``ReviewCycle.*`` events into the review cycle tables.

``ReviewCycle.Defined`` inserts the cycle (open) and one ``cur_documents_reviewer`` row per
reviewer; ``ReviewCycle.OutcomeRecorded`` fills in that reviewer's answer; ``ReviewCycle.Closed``
closes the cycle with its overall outcome. Deterministic. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_documents.names import (
    REVIEW_CLOSED,
    REVIEW_CYCLE_TABLE,
    REVIEW_CYCLE_VIEW,
    REVIEW_DEFINED,
    REVIEW_OUTCOME,
    REVIEWER_TABLE,
)
from tl_mod_documents.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {REVIEW_CYCLE_TABLE} (id, scope, revision_id, document_id, round, state, "
    "due_date, opened_on, last_seq) VALUES (:id, :scope, :revision_id, :document_id, :round, "
    ":state, :due_date, :opened_on, :last_seq)"
)
_REVIEWER_SQL = text(
    f"INSERT INTO {REVIEWER_TABLE} (reviewer_id, scope, review_cycle_id, revision_id, document_id, "
    "reviewer, due_date, last_seq) VALUES (:reviewer_id, :scope, :cycle, :revision_id, "
    ":document_id, :reviewer, :due_date, :last_seq)"
)
_OUTCOME_SQL = text(
    f"UPDATE {REVIEWER_TABLE} SET outcome = :outcome, comment = :comment, "
    "responded_on = :responded_on, last_seq = :last_seq "
    "WHERE review_cycle_id = :cycle AND reviewer = :reviewer"
)
_CLOSED_SQL = text(
    f"UPDATE {REVIEW_CYCLE_TABLE} SET state = :state, outcome = :outcome, closed_on = :closed_on, "
    "last_seq = :last_seq WHERE id = :id"
)
_BUMP_SQL = text(f"UPDATE {REVIEW_CYCLE_TABLE} SET last_seq = :last_seq WHERE id = :id")


class ReviewCycleProjector:
    name = "documents_review_cycle"
    handles = frozenset({REVIEW_DEFINED, REVIEW_OUTCOME, REVIEW_CLOSED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(REVIEW_CYCLE_TABLE, dialect)
            + ddl_for(REVIEWER_TABLE, dialect)
            + ddl_for(REVIEW_CYCLE_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == REVIEW_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "revision_id": payload["revision_id"],
                    "document_id": payload["document_id"],
                    "round": int(payload["round"]),
                    "state": "open",
                    "due_date": payload.get("due_date"),
                    "opened_on": payload["opened_on"],
                    "last_seq": event.seq,
                },
            )
            for position, entry in enumerate(payload.get("reviewers") or [], start=1):
                conn.execute(
                    _REVIEWER_SQL,
                    {
                        "reviewer_id": f"{event.stream_id}:{position:03d}",
                        "scope": event.scope,
                        "cycle": event.stream_id,
                        "revision_id": payload["revision_id"],
                        "document_id": payload["document_id"],
                        "reviewer": entry["reviewer"],
                        "due_date": entry.get("due_date") or payload.get("due_date"),
                        "last_seq": event.seq,
                    },
                )
        elif event.event_type == REVIEW_OUTCOME:
            found = conn.execute(
                _OUTCOME_SQL,
                {
                    "cycle": event.stream_id,
                    "reviewer": payload["reviewer"],
                    "outcome": payload["outcome"],
                    "comment": payload.get("comment"),
                    "responded_on": payload["responded_on"],
                    "last_seq": event.seq,
                },
            ).rowcount
            if found == 0:
                raise LookupError(f"no reviewer {payload['reviewer']!r} on {event.stream_id}")
            conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq})
        elif event.event_type == REVIEW_CLOSED:
            found = conn.execute(
                _CLOSED_SQL,
                {
                    "id": event.stream_id,
                    "state": "closed",
                    "outcome": payload["outcome"],
                    "closed_on": payload["closed_on"],
                    "last_seq": event.seq,
                },
            ).rowcount
            if found == 0:
                raise LookupError(f"no {REVIEW_CYCLE_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"ReviewCycleProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {REVIEWER_TABLE}"))
        conn.execute(text(f"DELETE FROM {REVIEW_CYCLE_TABLE}"))
